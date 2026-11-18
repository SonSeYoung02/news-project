import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import db
import main
from crawl_lock import SharedCrawlLock, get_crawl_lock_path
from translation.rate_limiter import CutoffController, RateLimiter

_CRAWLER_ROOT = Path(__file__).resolve().parent.parent


def _spawn_lock_holder(lock_path: Path) -> subprocess.Popen:
    script = (
        "import sys, time; "
        "from crawl_lock import SharedCrawlLock; "
        "lock = SharedCrawlLock(sys.argv[1]); "
        "assert lock.acquire(), 'expected lock acquire'; "
        "print('LOCKED', flush=True); "
        "sys.stdin.readline(); "
        "lock.release()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        cwd=str(_CRAWLER_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready = proc.stdout.readline().strip()
    if ready != "LOCKED":
        err = proc.stderr.read()
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail(f"holder failed to lock (ready={ready!r}): {err}")
    return proc


def _probe_lock_in_subprocess(lock_path: Path) -> bool:
    script = "\n".join(
        [
            "import sys",
            "from crawl_lock import SharedCrawlLock",
            "lock = SharedCrawlLock(sys.argv[1])",
            "acquired = lock.acquire()",
            "if acquired:",
            "    lock.release()",
            "sys.exit(0 if acquired else 2)",
        ]
    )
    res = subprocess.run(
        [sys.executable, "-c", script, str(lock_path)],
        cwd=str(_CRAWLER_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if res.returncode == 0:
        return True
    if res.returncode == 2:
        return False
    raise AssertionError(f"probe error rc={res.returncode}: {res.stderr}")


def test_acquire_release_preserves_inode_without_deletion(temp_crawl_lock):
    """공유 락 획득·해제 시 다른 프로세스의 동시 획득을 막고 파일과 inode는 삭제 없이 유지한다."""
    lock = SharedCrawlLock(temp_crawl_lock)
    assert lock.acquire()
    assert os.path.exists(temp_crawl_lock)
    ino_held = os.stat(temp_crawl_lock).st_ino

    assert not _probe_lock_in_subprocess(temp_crawl_lock)

    lock.release()
    assert os.path.exists(temp_crawl_lock), "잠금 파일은 해제 후에도 삭제되면 안 된다"
    assert os.stat(temp_crawl_lock).st_ino == ino_held, "잠금 파일 inode는 유지되어야 한다"
    assert _probe_lock_in_subprocess(temp_crawl_lock)


def test_auto_release_on_abrupt_process_kill(temp_crawl_lock):
    """락 보유 프로세스가 강제 종료되면 OS가 잠금을 즉시 해제해 다음 프로세스가 획득할 수 있다."""
    holder = _spawn_lock_holder(temp_crawl_lock)
    try:
        ino_before = os.stat(temp_crawl_lock).st_ino
        assert not _probe_lock_in_subprocess(temp_crawl_lock)

        # 정상 종료가 아닌 강제 종료(SIGKILL/TerminateProcess) 후 OS가 즉시 잠금을 해제해야 한다.
        holder.kill()
        holder.wait(timeout=10)

        lock = SharedCrawlLock(temp_crawl_lock)
        assert lock.acquire(), "프로세스 강제 종료 후 잠금이 자동 해제되어야 한다"
        assert os.stat(temp_crawl_lock).st_ino == ino_before
        lock.release()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)
        holder.stdin.close()
        holder.stdout.close()
        holder.stderr.close()


def test_run_pipeline_skips_when_shared_lock_held_by_another_process(temp_crawl_lock):
    """다른 프로세스가 공유 락을 점유 중이면 파이프라인은 수집·번역 없이 already_running으로 건너뛴다."""
    holder = _spawn_lock_holder(temp_crawl_lock)
    try:
        with patch("translation.batch_translator.call_gemini_batch") as mock_call:
            result = main.run_pipeline(
                sample_articles=[
                    {
                        "url": "https://example.com/blocked",
                        "source": "devto",
                        "title": "Blocked",
                        "content": "Should not run while locked",
                        "published_at": "2026-11-16T00:00:00Z",
                        "crawled_at": "2026-11-16T01:00:00",
                    }
                ]
            )
        assert result["status"] == "already_running"
        assert result["saved"] == 0
        assert mock_call.call_count == 0
        assert db.get_article_id_by_url("https://example.com/blocked") is None
    finally:
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=10)
        holder.stdin.close()
        holder.stdout.close()
        holder.stderr.close()


def test_run_pipeline_holds_shared_lock_across_crawl_translation_and_db_save(temp_crawl_lock, fake_gemini_batch):
    """파이프라인 실행 시 수집부터 번역·DB 저장까지 공유 락을 유지하고 종료 후 해제한다."""
    observed = {}
    orig_crawl = main.crawl_and_save_articles

    def wrapped_crawl(*args, **kwargs):
        observed["during_crawl_free"] = _probe_lock_in_subprocess(temp_crawl_lock)
        return orig_crawl(*args, **kwargs)

    def wrapped_gemini(batch, model=None):
        observed["during_translation_free"] = _probe_lock_in_subprocess(temp_crawl_lock)
        return fake_gemini_batch(batch, model=model)

    article = {
        "url": "https://example.com/protected-1",
        "source": "devto",
        "title": "Lock Coverage",
        "content": "Testing full pipeline flock coverage.",
        "published_at": "2026-11-16T00:00:00Z",
        "crawled_at": "2026-11-16T01:00:00",
    }

    with (
        patch("main.crawl_and_save_articles", side_effect=wrapped_crawl),
        patch("translation.batch_translator.call_gemini_batch", side_effect=wrapped_gemini),
    ):
        result = main.run_pipeline(
            sample_articles=[article],
            rate_limiter=RateLimiter(daily_limit=10, request_interval=0.01),
            cutoff_controller=CutoffController(),
        )

    assert result["status"] == "completed"
    assert result["saved"] == 1
    assert result["translated"] == 1
    assert not observed.get("during_crawl_free", True), "수집 중에는 공유 락이 점유되어 있어야 한다"
    assert not observed.get("during_translation_free", True), "번역 및 DB 저장 중에는 공유 락이 점유되어 있어야 한다"
    assert _probe_lock_in_subprocess(temp_crawl_lock), "파이프라인 종료 후 공유 락이 해제되어야 한다"


def test_run_pipeline_releases_shared_lock_on_exception(temp_crawl_lock):
    """수집 단계에서 예외가 발생해도 파이프라인이 공유 락을 반드시 해제한다."""
    with patch("main.crawl_and_save_articles", side_effect=RuntimeError("boom")):
        result = main.run_pipeline(sample_articles=[])

    assert result["status"] == "failed"
    assert _probe_lock_in_subprocess(temp_crawl_lock), "예외 발생 후에도 공유 락이 해제되어야 한다"


def test_default_lock_path_derived_from_db_path_when_env_unset(temp_db, monkeypatch):
    """CRAWL_LOCK_PATH가 비어 있으면 활성 DB 경로와 같은 디렉터리의 기본 락 파일 경로를 사용한다."""
    monkeypatch.delenv("CRAWL_LOCK_PATH", raising=False)
    path = get_crawl_lock_path()
    assert path.parent == temp_db.parent
    assert str(path) != str(temp_db)
