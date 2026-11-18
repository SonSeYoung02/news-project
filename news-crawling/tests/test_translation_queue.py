import db
from translation.queue import (
    get_pending_translation_queue,
    is_korean_text,
    is_translatable_source,
)


def test_is_translatable_source():
    """한국어 출처와 레거시 한국어 출처는 제외하고 영어 출처만 번역 대상으로 판별한다."""
    assert not is_translatable_source("네이버뉴스")
    assert not is_translatable_source("GeekNews")
    assert not is_translatable_source("naver")
    assert not is_translatable_source("geeknews")
    assert is_translatable_source("Google News")
    assert is_translatable_source("devto")
    assert is_translatable_source("google_news")
    assert is_translatable_source("reddit_ai")
    assert is_translatable_source("github_trending")
    assert is_translatable_source("huggingface")
    assert is_translatable_source("arxiv")


def test_queue_ordering_and_filtering(temp_db):
    """대기열은 한국어·완료 기사를 제외하고 당일 신규 기사를 이전 잔여 기사보다 앞에 정렬한다."""
    db.save_article({
        "url": "https://example.com/old-en",
        "source": "devto",
        "title": "Old English Article",
        "content": "Content of old article",
        "published_at": "2026-11-12T00:30:00Z",
        "crawled_at": "2026-11-11T01:00:00",
    })
    old_id = db.get_article_id_by_url("https://example.com/old-en")

    db.save_article({
        "url": "https://example.com/ko",
        "source": "네이버뉴스",
        "title": "네이버 한국어 기사",
        "content": "한국어 내용",
        "published_at": "2026-11-12T00:40:00+09:00",
        "crawled_at": "2026-11-12T01:00:00",
    })
    ko_id = db.get_article_id_by_url("https://example.com/ko")

    db.save_article({
        "url": "https://example.com/new-en-1",
        "source": "github_trending",
        "title": "New Article A",
        "content": "Content A",
        "published_at": "2026-11-12T00:10:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    })
    new_a_id = db.get_article_id_by_url("https://example.com/new-en-1")

    db.save_article({
        "url": "https://example.com/new-en-2",
        "source": "huggingface",
        "title": "New Article B",
        "content": "Content B",
        "published_at": "2026-11-12T00:20:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    })
    new_b_id = db.get_article_id_by_url("https://example.com/new-en-2")

    db.save_article({
        "url": "https://example.com/completed-en",
        "source": "arxiv",
        "title": "Completed Article",
        "content": "Content Completed",
        "published_at": "2026-11-12T00:25:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    })
    comp_id = db.get_article_id_by_url("https://example.com/completed-en")
    comp_hash = db.compute_content_hash("Completed Article", "Content Completed")
    db.get_or_create_translation(comp_id, comp_hash)
    db.complete_article_translation(
        comp_id, comp_hash, "완료된 제목", "완료된 본문", "gemini-2.5-flash"
    )

    new_ids = {new_a_id, new_b_id, comp_id, ko_id}

    queue = get_pending_translation_queue(new_ids)

    queued_ids = [job["article_id"] for job in queue]
    assert ko_id not in queued_ids
    assert comp_id not in queued_ids

    expected_ids = [new_b_id, new_a_id, old_id]
    assert queued_ids == expected_ids

    assert queue[0]["is_new_in_run"]
    assert queue[1]["is_new_in_run"]
    assert not queue[2]["is_new_in_run"]


def test_queue_excludes_naver_articles(temp_db):
    """네이버뉴스 출처 기사는 번역 대기열에 포함되지 않아야 한다."""
    db.save_article({
        "url": "https://example.com/naver-1",
        "source": "네이버뉴스",
        "title": "네이버 IT 신규 기사",
        "content": "네이버 IT 뉴스 본문 내용입니다.",
        "published_at": "2026-11-12T00:50:00+09:00",
        "crawled_at": "2026-11-12T01:00:00",
    })
    naver_id = db.get_article_id_by_url("https://example.com/naver-1")
    queue = get_pending_translation_queue({naver_id})
    queued_ids = [job["article_id"] for job in queue]
    assert naver_id not in queued_ids


def test_is_korean_text():
    """한글 비율이 임계값 이상인 텍스트만 한국어 기사로 판별한다."""
    assert is_korean_text("삼성전자 실적 발표", "삼성전자가 3분기 실적을 발표했다.")
    assert not is_korean_text("OpenAI releases GPT", "OpenAI announced a new model today.")
    assert not is_korean_text(
        "Seoul AI summit", "Leaders met in 서울 to discuss AI policy and safety."
    )
    assert not is_korean_text("", "")


def test_queue_excludes_korean_content_from_english_source(temp_db):
    """영어 출처라도 본문이 한국어면 번역 대기열에서 제외된다."""
    db.save_article({
        "url": "https://example.com/gn-ko",
        "source": "Google News",
        "title": "삼성전자 실적 발표",
        "content": "삼성전자가 3분기 실적을 발표했다.",
        "published_at": "2026-11-12T00:50:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    })
    ko_id = db.get_article_id_by_url("https://example.com/gn-ko")
    db.save_article({
        "url": "https://example.com/gn-en",
        "source": "Google News",
        "title": "OpenAI releases GPT",
        "content": "OpenAI announced a new model today.",
        "published_at": "2026-11-12T00:55:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    })
    en_id = db.get_article_id_by_url("https://example.com/gn-en")
    queue = get_pending_translation_queue(set())
    queued_ids = [job["article_id"] for job in queue]
    assert queued_ids == [en_id]
    assert ko_id not in queued_ids
