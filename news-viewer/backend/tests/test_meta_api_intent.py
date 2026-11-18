"""viewer-api 카테고리·출처 집계 메타 라우터 계약 의도 기반 테스트."""

import pytest

from app.meta.schemas import CategoryCount, SourceCount


def test_categories_ordered_by_count_desc(client, seed_db):
    """GET /categories는 대분류별 기사 수를 count 내림차순으로 반환한다."""
    # 삽입 순서는 경제(1) → IT(2) → AI(3) 이지만 응답은 count DESC 여야 한다.
    seed_db.article(major_category="경제")
    for _ in range(2):
        seed_db.article(major_category="IT")
    for _ in range(3):
        seed_db.article(major_category="AI")

    resp = client.get("/categories")
    assert resp.status_code == 200
    payload = resp.json()
    items = [CategoryCount.model_validate(item) for item in payload]

    assert [(item.major_category, item.count) for item in items] == [
        ("AI", 3),
        ("IT", 2),
        ("경제", 1),
    ]


def test_categories_use_analysis_coalesce_and_exclude_null(client, seed_db):
    """카테고리 집계는 article_analysis 대분류를 우선 반영하고 대분류가 NULL인 기사는 제외한다."""
    # articles.major_category='IT' 이지만 article_analysis가 'AI'로 보강된 기사 2건
    for idx in range(1, 3):
        aid = seed_db.article(article_id=idx, major_category="IT")
        seed_db.analysis(article_id=aid, major_category="AI")

    # articles.major_category만 'IT'인 기사 1건
    seed_db.article(article_id=3, major_category="IT")

    # 원문·분석 모두 대분류가 NULL인 기사 1건 → 집계에서 제외되어야 함
    aid_null = seed_db.article(article_id=4, major_category=None)
    seed_db.analysis(article_id=aid_null, major_category=None)

    resp = client.get("/categories")
    assert resp.status_code == 200
    assert resp.json() == [
        {"major_category": "AI", "count": 2},
        {"major_category": "IT", "count": 1},
    ]


def test_sources_ordered_by_count_desc(client, seed_db):
    """GET /sources는 출처별 기사 수를 count 내림차순으로 반환한다."""
    seed_db.article(source="techcrunch")
    for _ in range(2):
        seed_db.article(source="huggingface")
    for _ in range(3):
        seed_db.article(source="네이버뉴스")

    resp = client.get("/sources")
    assert resp.status_code == 200
    payload = resp.json()
    items = [SourceCount.model_validate(item) for item in payload]

    assert [(item.source, item.count) for item in items] == [
        ("네이버뉴스", 3),
        ("huggingface", 2),
        ("techcrunch", 1),
    ]


def test_categories_and_sources_empty_db_return_empty_lists(client):
    """기사가 없는 DB에서는 /categories와 /sources 모두 빈 배열을 반환한다."""
    assert client.get("/categories").json() == []
    assert client.get("/sources").json() == []


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/categories", "/sources"])
def test_meta_endpoints_reject_write_methods_with_405(client, method, path):
    """카테고리·출처 메타 엔드포인트도 읽기 전용이므로 쓰기 메서드를 405로 거부한다."""
    resp = client.request(method, path)
    assert resp.status_code == 405
