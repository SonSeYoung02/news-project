import db


def test_init_db_creates_all_tables(temp_db):
    """DB 초기화 시 기사·분석·번역·청크·쿼터·락 테이블이 모두 생성된다."""
    with db._connect() as conn:
        tables = [row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    assert "articles" in tables
    assert "article_analysis" in tables
    assert "article_translations" in tables
    assert "translation_chunks" in tables
    assert "translation_quota" in tables
    assert "crawl_locks" in tables


def test_compute_content_hash():
    """동일 제목·본문은 같은 64자리 SHA-256 해시를 만들고 내용이 바뀌면 해시도 달라진다."""
    h1 = db.compute_content_hash("Title 1", "Content 1")
    h2 = db.compute_content_hash("Title 1", "Content 1")
    h3 = db.compute_content_hash("Title 1", "Changed Content")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_translation_lifecycle_and_chunks(temp_db):
    """기사 저장부터 청크 번역 저장 및 전체 번역 완료 상태 전이까지 일관되게 기록된다."""
    article = {
        "url": "https://example.com/ai-1",
        "source": "devto",
        "title": "AI Revolution",
        "content": "Paragraph 1\n\nParagraph 2",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T01:00:00",
    }
    assert db.save_article(article)
    article_id = db.get_article_id_by_url(article["url"])
    assert article_id is not None

    content_hash = db.compute_content_hash(article["title"], article["content"])

    trans = db.get_or_create_translation(article_id, content_hash)
    assert trans["status"] == "pending"
    assert trans["content_hash"] == content_hash

    db.save_translation_chunk(
        article_id=article_id,
        content_hash=content_hash,
        chunk_index=0,
        total_chunks=2,
        original_chunk="Paragraph 1",
        translated_chunk="문단 1",
        status="completed",
    )
    db.save_translation_chunk(
        article_id=article_id,
        content_hash=content_hash,
        chunk_index=1,
        total_chunks=2,
        original_chunk="Paragraph 2",
        translated_chunk=None,
        status="pending",
    )

    chunks = db.get_translation_chunks(article_id, content_hash)
    assert len(chunks) == 2
    assert chunks[0]["status"] == "completed"
    assert chunks[0]["translated_chunk"] == "문단 1"
    assert chunks[1]["status"] == "pending"
    assert chunks[1]["translated_chunk"] is None

    db.save_translation_chunk(
        article_id=article_id,
        content_hash=content_hash,
        chunk_index=1,
        total_chunks=2,
        original_chunk="Paragraph 2",
        translated_chunk="문단 2",
        status="completed",
    )
    chunks = db.get_translation_chunks(article_id, content_hash)
    assert all(c["status"] == "completed" for c in chunks)

    ok = db.complete_article_translation(
        article_id=article_id,
        content_hash=content_hash,
        translated_title="AI 혁명",
        translated_content="문단 1\n\n문단 2",
        model="gemini-2.5-flash",
    )
    assert ok

    trans_after = db.get_or_create_translation(article_id, content_hash)
    assert trans_after["status"] == "completed"
    assert trans_after["translated_title"] == "AI 혁명"
    assert trans_after["translated_content"] == "문단 1\n\n문단 2"
    assert trans_after["model"] == "gemini-2.5-flash"
    assert trans_after["completed_at"] is not None


def test_daily_quota_persistence(temp_db):
    """일일 API 요청 수와 토큰 사용량이 누적 합산되어 DB에 영속화된다."""
    date_str = "2026-11-12"
    q0 = db.get_daily_quota(date_str)
    assert q0["request_count"] == 0
    assert q0["token_count"] == 0

    q1 = db.increment_daily_quota(date_str, requests=5, tokens=1200)
    assert q1["request_count"] == 5
    assert q1["token_count"] == 1200

    q2 = db.increment_daily_quota(date_str, requests=3, tokens=800)
    assert q2["request_count"] == 8
    assert q2["token_count"] == 2000

    q_check = db.get_daily_quota(date_str)
    assert q_check["request_count"] == 8
    assert q_check["token_count"] == 2000


def test_crawl_lock_mutual_exclusion(temp_db):
    """DB 기반 크롤 락은 중복 획득을 차단하고 해제 후 다시 획득을 허용한다."""
    lock_name = "test_nightly_crawl"
    assert db.acquire_crawl_lock(name=lock_name, timeout_minutes=60)
    assert not db.acquire_crawl_lock(name=lock_name, timeout_minutes=60)
    assert db.release_crawl_lock(name=lock_name)
    assert db.acquire_crawl_lock(name=lock_name, timeout_minutes=60)
    db.release_crawl_lock(name=lock_name)


def test_refresh_article_from_source(temp_db):
    """기존 기사를 동일 URL로 갱신하면 제목과 본문이 최신 값으로 덮어써진다."""
    article = {
        "url": "https://example.com/refresh-1",
        "source": "google_news",
        "title": "Original Title",
        "content": "Original Content",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T01:00:00",
        "major_category": "AI",
        "tags": ["AI"],
    }
    db.save_article(article)

    updated_article = {
        "url": "https://example.com/refresh-1",
        "source": "google_news",
        "title": "Updated Title",
        "content": "Updated Content",
        "published_at": "2026-11-12T00:00:00Z",
        "crawled_at": "2026-11-12T02:00:00",
        "major_category": "AI",
        "tags": ["AI", "Tech"],
    }
    refreshed = db.refresh_article_from_source(updated_article)
    assert refreshed

    fetched = db.get_article_by_url(article["url"])
    assert fetched["title"] == "Updated Title"
    assert fetched["content"] == "Updated Content"
