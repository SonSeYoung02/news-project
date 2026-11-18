from unittest.mock import patch

import db
import main
from translation import batcher
from translation.batch_translator import DailyQuotaExceeded, PermanentApiError
from translation.rate_limiter import CutoffController, RateLimiter


def english_articles(n):
    return [
        {
            "url": f"https://example.com/en-{i}",
            "source": "devto",
            "title": f"Title {i}",
            "content": f"Content {i}",
            "published_at": f"2026-11-12T00:0{i}:00Z",
            "crawled_at": "2026-11-12T01:00:00",
        }
        for i in range(n)
    ]


def test_full_pipeline_run_integration(temp_db, mock_call_gemini_batch):
    """전체 파이프라인 실행 시 영어 기사만 번역 완료 처리하고 한국어 기사·공유 락을 정상 처리한다."""
    articles = [
        {
            "url": "https://example.com/int-en",
            "source": "devto",
            "title": "Quantum AI Breakthrough",
            "content": "Quantum computing is revolutionizing AI algorithms.",
            "published_at": "2026-11-12T00:00:00Z",
            "crawled_at": "2026-11-12T01:00:00",
            "major_category": "AI",
            "tags": ["AI"],
        },
        {
            "url": "https://example.com/int-ko",
            "source": "네이버뉴스",
            "title": "국내 반도체 생산 확대",
            "content": "국내 주요 기업들이 투자를 확대한다.",
            "published_at": "2026-11-12T00:10:00+09:00",
            "crawled_at": "2026-11-12T01:00:00",
            "major_category": "IT",
            "tags": ["반도체"],
        },
    ]

    rate_limiter = RateLimiter(daily_limit=10, request_interval=0.01)
    cutoff_controller = CutoffController()

    result = main.run_pipeline(
        sample_articles=articles,
        rate_limiter=rate_limiter,
        cutoff_controller=cutoff_controller,
    )

    assert result["status"] == "completed"
    assert result["saved"] == 2
    assert result["translated"] == 1
    assert result["pending_translation"] == 0
    assert mock_call_gemini_batch.call_count == 1

    # 1. 영어 기사: 번역 레코드 completed 확인
    en_id = db.get_article_id_by_url("https://example.com/int-en")
    en_hash = db.compute_content_hash(
        "Quantum AI Breakthrough",
        "Quantum computing is revolutionizing AI algorithms.",
    )
    en_trans = db.get_or_create_translation(en_id, en_hash)
    assert en_trans["status"] == "completed"
    assert en_trans["translated_title"] == "한국어 제목"

    # 2. 한국어 기사: 번역 레코드 없음 확인
    ko_id = db.get_article_id_by_url("https://example.com/int-ko")
    with db._connect() as conn:
        row_trans = conn.execute(
            "SELECT * FROM article_translations WHERE article_id = ?", (ko_id,)
        ).fetchone()
        assert row_trans is None

    # 3. 락 해제 확인
    with db._connect() as conn:
        lock = conn.execute(
            "SELECT * FROM crawl_locks WHERE name = 'nightly_crawl'"
        ).fetchone()
        assert lock is None


def test_pipeline_stops_gracefully_on_cutoff(temp_db, mock_call_gemini_batch):
    """마감 시간에 도달하면 Gemini 호출 없이 남은 기사를 보류하고 stopped_cutoff로 종료한다."""
    articles = [
        {
            "url": "https://example.com/cutoff-en-1",
            "source": "devto",
            "title": "Title 1",
            "content": "Content 1",
            "published_at": "2026-11-12T00:00:00Z",
            "crawled_at": "2026-11-12T01:00:00",
        },
        {
            "url": "https://example.com/cutoff-en-2",
            "source": "google_news",
            "title": "Title 2",
            "content": "Content 2",
            "published_at": "2026-11-12T00:05:00Z",
            "crawled_at": "2026-11-12T01:00:00",
        },
    ]

    class ImmediateCutoff:
        def can_request(self, now_dt=None):
            return False

    result = main.run_pipeline(
        sample_articles=articles,
        rate_limiter=RateLimiter(daily_limit=10, request_interval=0.01),
        cutoff_controller=ImmediateCutoff(),
    )

    assert result["status"] == "stopped_cutoff"
    assert result["translated"] == 0
    assert result["pending_translation"] == 2
    assert mock_call_gemini_batch.call_count == 0


def test_pipeline_stops_on_daily_quota_without_failures(temp_db, mock_call_gemini_batch):
    """일일 무료 한도(429) 초과 시 기사를 실패로 기록하지 않고 보류한 채 중단한다."""
    mock_call_gemini_batch.side_effect = DailyQuotaExceeded("quota")
    result = main.run_pipeline(
        sample_articles=english_articles(3),
        rate_limiter=RateLimiter(daily_limit=10, request_interval=0.01),
        cutoff_controller=CutoffController(),
    )
    assert result["status"] == "stopped_daily_quota"
    assert result["failed_translation"] == 0
    assert result["translated"] == 0
    assert result["pending_translation"] == 3
    with db._connect() as conn:
        failed = conn.execute(
            "SELECT COUNT(*) FROM article_translations WHERE status = 'failed'"
        ).fetchone()[0]
    assert failed == 0


def test_pipeline_stops_after_two_permanent_errors(temp_db, mock_call_gemini_batch):
    """영구 오류가 연속 2회 발생하면 이후 묶음은 실행하지 않고 중단한다."""
    mock_call_gemini_batch.side_effect = PermanentApiError("bad request")
    original = batcher.build_batches
    with patch(
        "translation.batcher.build_batches",
        side_effect=lambda q, **kw: original(q, max_articles=1),
    ):
        result = main.run_pipeline(
            sample_articles=english_articles(3),
            rate_limiter=RateLimiter(daily_limit=10, request_interval=0.01),
            cutoff_controller=CutoffController(),
        )
    assert mock_call_gemini_batch.call_count == 2
    assert result["status"] == "stopped_permanent_error"
    assert result["failed_translation"] == 2
    assert result["pending_translation"] == 1
