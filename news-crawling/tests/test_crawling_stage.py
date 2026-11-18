import sys

import db
import main


def test_crawl_and_save_new_articles(temp_db):
    """신규 영어·한국어 기사를 수집하면 모두 DB에 저장되고 신규 ID 목록을 반환한다."""
    sample_articles = [
        {
            "url": "https://example.com/en-1",
            "source": "devto",
            "title": "Getting started with LLMs",
            "content": "LLMs are changing everything.",
            "published_at": "2026-11-12T00:00:00Z",
            "crawled_at": "2026-11-12T01:00:00",
            "major_category": "AI",
            "tags": ["AI", "LLM"],
        },
        {
            "url": "https://example.com/ko-1",
            "source": "네이버뉴스",
            "title": "인공지능 생태계 확장",
            "content": "국내 AI 생태계가 빠르게 확장 중이다.",
            "published_at": "2026-11-12T00:30:00+09:00",
            "crawled_at": "2026-11-12T01:00:00",
            "major_category": "AI",
            "tags": ["AI"],
        },
    ]
    saved, refreshed, failed, new_ids = main.crawl_and_save_articles(sample_articles)
    assert saved == 2
    assert refreshed == 0
    assert failed == 0
    assert len(new_ids) == 2

    row_en = db.get_article_by_url("https://example.com/en-1")
    assert row_en is not None
    assert row_en["title"] == "Getting started with LLMs"
    assert row_en["content"] == "LLMs are changing everything."

    row_ko = db.get_article_by_url("https://example.com/ko-1")
    assert row_ko is not None
    assert row_ko["title"] == "인공지능 생태계 확장"


def test_duplicate_article_refresh_preserves_count(temp_db):
    """동일 URL 기사를 다시 수집하면 신규 저장 없이 기존 레코드만 최신 정보로 갱신한다."""
    initial_article = {
        "url": "https://example.com/dup-1",
        "source": "google_news",
        "title": "Old Headline",
        "content": "Old Content",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    }
    main.crawl_and_save_articles([initial_article])

    updated_article = {
        "url": "https://example.com/dup-1",
        "source": "google_news",
        "title": "Breaking: New Headline",
        "content": "Full detailed content updated.",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T01:30:00",
    }
    saved, refreshed, failed, new_ids = main.crawl_and_save_articles([updated_article])
    assert saved == 0
    assert refreshed == 1
    assert failed == 0
    assert len(new_ids) == 0

    row = db.get_article_by_url("https://example.com/dup-1")
    assert row["title"] == "Breaking: New Headline"
    assert row["content"] == "Full detailed content updated."


def test_no_summarize_or_classify_during_crawling(temp_db):
    """수집 단계에서는 요약·분류용 llm 모듈을 로드하거나 호출하지 않는다."""
    sample = [{
        "url": "https://example.com/no-llm",
        "source": "huggingface",
        "title": "HF Daily Papers",
        "content": "New paper about transformers.",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    }]
    saved, refreshed, failed, new_ids = main.crawl_and_save_articles(sample)
    assert saved == 1
    # 요약·분류용 llm 모듈은 제거되었으며, 수집 단계에서 다시 불러오지 않아야 한다.
    assert "llm" not in sys.modules
    assert "llm.analyzer" not in sys.modules
