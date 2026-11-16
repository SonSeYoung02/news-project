import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
import main


def _fake_gemini(batch, model=None):
    return json.dumps(
        [
            {"id": j["article_id"], "title": "한국어 제목", "content": "한국어 번역 본문 " * 40}
            for j in batch
        ],
        ensure_ascii=False,
    )


class TestSharedCrawlLock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = os.path.join(self.temp_dir.name, "news.db")
        self.lock_path = os.path.join(self.temp_dir.name, "locks", "crawl.lock")
        self._prev_db = os.environ.get("DB_PATH")
        self._prev_lock = os.environ.get("CRAWL_LOCK_PATH")
        os.environ["DB_PATH"] = self.temp_db_path
        os.environ["CRAWL_LOCK_PATH"] = self.lock_path
        db.init_db()

    def tearDown(self):
        if self._prev_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self._prev_db

        if self._prev_lock is None:
            os.environ.pop("CRAWL_LOCK_PATH", None)
        else:
            os.environ["CRAWL_LOCK_PATH"] = self._prev_lock

        self.temp_dir.cleanup()

    def _spawn_lock_holder(self):
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
            [sys.executable, "-c", script, self.lock_path],
            cwd=str(Path(__file__).parent),
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
            self.fail(f"holder failed to lock (ready={ready!r}): {err}")
        return proc

    def _probe_lock_in_subprocess(self) -> bool:
        script = "\n".join([
            "import sys",
            "from crawl_lock import SharedCrawlLock",
            "lock = SharedCrawlLock(sys.argv[1])",
            "acquired = lock.acquire()",
            "if acquired:",
            "    lock.release()",
            "sys.exit(0 if acquired else 2)",
        ])
        res = subprocess.run(
            [sys.executable, "-c", script, self.lock_path],
            cwd=str(Path(__file__).parent),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return True
        if res.returncode == 2:
            return False
        raise AssertionError(f"probe error rc={res.returncode}: {res.stderr}")

    def test_acquire_release_preserves_inode_without_deletion(self):
        from crawl_lock import SharedCrawlLock

        lock = SharedCrawlLock(self.lock_path)
        self.assertTrue(lock.acquire())
        self.assertTrue(os.path.exists(self.lock_path))
        ino_held = os.stat(self.lock_path).st_ino

        self.assertFalse(self._probe_lock_in_subprocess())

        lock.release()
        self.assertTrue(os.path.exists(self.lock_path), "잠금 파일은 해제 후에도 삭제되면 안 된다")
        self.assertEqual(os.stat(self.lock_path).st_ino, ino_held, "잠금 파일 inode는 유지되어야 한다")
        self.assertTrue(self._probe_lock_in_subprocess())

    def test_auto_release_on_abrupt_process_kill(self):
        from crawl_lock import SharedCrawlLock

        holder = self._spawn_lock_holder()
        try:
            ino_before = os.stat(self.lock_path).st_ino
            self.assertFalse(self._probe_lock_in_subprocess())

            # 정상 종료가 아닌 강제 종료(SIGKILL/TerminateProcess) 후 OS가 즉시 잠금을 해제해야 한다.
            holder.kill()
            holder.wait(timeout=10)

            lock = SharedCrawlLock(self.lock_path)
            self.assertTrue(lock.acquire(), "프로세스 강제 종료 후 잠금이 자동 해제되어야 한다")
            self.assertEqual(os.stat(self.lock_path).st_ino, ino_before)
            lock.release()
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=5)
            holder.stdin.close()
            holder.stdout.close()
            holder.stderr.close()

    def test_run_pipeline_skips_when_shared_lock_held_by_another_process(self):
        holder = self._spawn_lock_holder()
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
            self.assertEqual(result["status"], "already_running")
            self.assertEqual(result["saved"], 0)
            self.assertEqual(mock_call.call_count, 0)
            self.assertIsNone(db.get_article_id_by_url("https://example.com/blocked"))
        finally:
            holder.stdin.write("\n")
            holder.stdin.flush()
            holder.wait(timeout=10)
            holder.stdin.close()
            holder.stdout.close()
            holder.stderr.close()

    def test_run_pipeline_holds_shared_lock_across_crawl_translation_and_db_save(self):
        from translation.rate_limiter import CutoffController, RateLimiter

        observed = {}
        orig_crawl = main.crawl_and_save_articles

        def wrapped_crawl(*args, **kwargs):
            observed["during_crawl_free"] = self._probe_lock_in_subprocess()
            return orig_crawl(*args, **kwargs)

        def wrapped_gemini(batch, model=None):
            observed["during_translation_free"] = self._probe_lock_in_subprocess()
            return _fake_gemini(batch, model=model)

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

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["translated"], 1)
        self.assertFalse(observed.get("during_crawl_free", True), "수집 중에는 공유 락이 점유되어 있어야 한다")
        self.assertFalse(observed.get("during_translation_free", True), "번역 및 DB 저장 중에는 공유 락이 점유되어 있어야 한다")
        self.assertTrue(self._probe_lock_in_subprocess(), "파이프라인 종료 후 공유 락이 해제되어야 한다")

    def test_run_pipeline_releases_shared_lock_on_exception(self):
        with patch("main.crawl_and_save_articles", side_effect=RuntimeError("boom")):
            result = main.run_pipeline(sample_articles=[])

        self.assertEqual(result["status"], "failed")
        self.assertTrue(self._probe_lock_in_subprocess(), "예외 발생 후에도 공유 락이 해제되어야 한다")

    def test_default_lock_path_derived_from_db_path_when_env_unset(self):
        from crawl_lock import get_crawl_lock_path

        os.environ.pop("CRAWL_LOCK_PATH", None)
        path = get_crawl_lock_path()
        self.assertEqual(path.parent, Path(self.temp_db_path).parent)
        self.assertNotEqual(str(path), self.temp_db_path)


if __name__ == "__main__":
    unittest.main()
