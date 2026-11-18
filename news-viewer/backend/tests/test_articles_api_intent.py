"""viewer-api 기사 목록·상세 라우터 계약 의도 기반 테스트."""

import pytest

from app.article.schemas import Article, ArticleListResponse


def test_articles_sorted_by_latest_crawled_at_desc(client, seed_db):
    """기사 목록은 ID나 발행일 순서와 무관하게 최신 수집 시각(crawled_at) 내림차순으로 반환한다."""
    seed_db.article(
        article_id=1,
        title="가장 먼저 수집된 기사",
        published_at="2026-11-12T12:00:00Z",
        crawled_at="2026-11-10T09:00:00",
    )
    seed_db.article(
        article_id=2,
        title="가장 최근에 수집된 기사",
        published_at="2026-11-08T01:00:00Z",
        crawled_at="2026-11-12T15:30:00",
    )
    seed_db.article(
        article_id=3,
        title="중간 시점에 수집된 기사",
        published_at="2026-11-11T06:00:00Z",
        crawled_at="2026-11-11T10:00:00",
    )

    resp = client.get("/articles")
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["articles"]]
    assert ids == [2, 3, 1]


def test_articles_same_crawled_at_sorted_by_id_desc_and_stable_across_pages(client, seed_db):
    """crawled_at이 같은 기사가 id와 다른 순서로 삽입돼도 crawled_at DESC, id DESC로 정렬되고 페이지 경계에서 중복·누락이 없다."""
    same_crawled_at = "2026-11-10T11:00:00"
    seed_db.article(
        article_id=20,
        title="가장 먼저 수집된 기사",
        crawled_at="2026-11-10T10:00:00",
    )
    for aid in (3, 1, 6, 2, 5, 4):
        seed_db.article(
            article_id=aid,
            title=f"동일 수집 시각 기사 {aid}",
            crawled_at=same_crawled_at,
        )
    seed_db.article(
        article_id=10,
        title="가장 최근에 수집된 기사",
        crawled_at="2026-11-10T12:00:00",
    )

    expected_ids = [10, 6, 5, 4, 3, 2, 1, 20]

    full_resp = client.get("/articles", params={"page": 1, "size": 20})
    assert full_resp.status_code == 200
    full_body = full_resp.json()
    assert full_body["total"] == len(expected_ids)
    assert [item["id"] for item in full_body["articles"]] == expected_ids

    paged_ids = []
    for page in range(1, 5):
        resp = client.get("/articles", params={"page": page, "size": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(expected_ids)
        paged_ids.extend(item["id"] for item in body["articles"])

    assert paged_ids == expected_ids
    assert len(paged_ids) == len(set(paged_ids)) == len(expected_ids)


def test_articles_pagination_slices_and_preserves_total(client, seed_db):
    """페이지네이션 요청 시 page/size에 맞는 구간만 반환하고 전체 건수(total)를 유지한다."""
    for idx in range(1, 6):
        seed_db.article(
            article_id=idx,
            title=f"기사 {idx}",
            crawled_at=f"2026-11-10T10:0{idx}:00",
        )

    page1 = client.get("/articles", params={"page": 1, "size": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["total"] == 5
    assert body1["page"] == 1
    assert body1["size"] == 2
    assert [a["id"] for a in body1["articles"]] == [5, 4]

    page2 = client.get("/articles", params={"page": 2, "size": 2})
    assert page2.status_code == 200
    body2 = page2.json()
    assert body2["total"] == 5
    assert [a["id"] for a in body2["articles"]] == [3, 2]

    page4 = client.get("/articles", params={"page": 4, "size": 2})
    assert page4.status_code == 200
    body4 = page4.json()
    assert body4["total"] == 5
    assert body4["page"] == 4
    assert body4["size"] == 2
    assert body4["articles"] == []


def test_articles_empty_db_returns_empty_list_and_zero_total(client):
    """저장된 기사가 없으면 total=0과 빈 articles 배열을 반환한다."""
    resp = client.get("/articles")
    assert resp.status_code == 200
    assert resp.json() == {
        "total": 0,
        "page": 1,
        "size": 20,
        "articles": [],
    }


def test_articles_combined_category_source_and_q_filters(client, seed_db):
    """category·source·q 필터를 함께 전달하면 모든 조건을 동시에 만족하는 기사만 조회한다."""
    # 대상 1: raw category는 IT지만 article_analysis가 AI로 보강되었고 source/q 모두 일치
    target_id = seed_db.article(
        article_id=10,
        source="devto",
        title="에이전트 워크플로 설계",
        content="멀티 에이전트 오케스트레이션 사례",
        summary="기존 요약",
        major_category="IT",
        crawled_at="2026-11-10T12:00:00",
    )
    seed_db.analysis(
        article_id=target_id,
        summary="AI 에이전트 핵심 정리",
        major_category="AI",
        sub_category="Agents",
        tags='["에이전트"]',
    )

    # 제외 2: category/q 일치하지만 source 다름
    seed_db.article(
        article_id=11,
        source="huggingface",
        title="에이전트 모델 벤치마크",
        major_category="AI",
        crawled_at="2026-11-10T12:01:00",
    )
    # 제외 3: source/q 일치하지만 category 다름
    seed_db.article(
        article_id=12,
        source="devto",
        title="에이전트 인프라 운영",
        major_category="IT",
        crawled_at="2026-11-10T12:02:00",
    )
    # 제외 4: category/source 일치하지만 q 미포함
    seed_db.article(
        article_id=13,
        source="devto",
        title="트랜스포머 최적화",
        content="커널 튜닝 가이드",
        summary="GPU 메모리 절감",
        major_category="AI",
        crawled_at="2026-11-10T12:03:00",
    )

    resp = client.get(
        "/articles",
        params={"category": "AI", "source": "devto", "q": "에이전트"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [a["id"] for a in body["articles"]] == [10]


def test_articles_tags_deserialized_as_list(client, seed_db):
    """DB에 JSON 문자열·NULL·손상 문자열로 저장된 tags도 항상 배열(list)로 역직렬화한다."""
    seed_db.article(
        article_id=1,
        tags='["LLM", "한국어태그"]',
        crawled_at="2026-11-10T10:04:00",
    )
    seed_db.article(
        article_id=2,
        tags=None,
        crawled_at="2026-11-10T10:03:00",
    )
    seed_db.article(
        article_id=3,
        tags="[]",
        crawled_at="2026-11-10T10:02:00",
    )
    seed_db.article(
        article_id=4,
        tags="{not-valid-json",
        crawled_at="2026-11-10T10:01:00",
    )

    resp = client.get("/articles", params={"page": 1, "size": 10})
    assert resp.status_code == 200
    by_id = {item["id"]: item for item in resp.json()["articles"]}
    assert by_id[1]["tags"] == ["LLM", "한국어태그"]
    assert by_id[2]["tags"] == []
    assert by_id[3]["tags"] == []
    assert by_id[4]["tags"] == []
    assert all(isinstance(item["tags"], list) for item in by_id.values())


@pytest.mark.parametrize(
    ("raw_tags", "expected_tags"),
    [
        ("null", []),
        ("123", []),
        ("true", []),
        ('"text"', []),
        ("{}", []),
        ('["a", 1]', ["a"]),
        ('["a", null, {"k": "v"}, true, "b"]', ["a", "b"]),
    ],
)
def test_articles_non_array_or_mixed_tags_normalized_to_string_list(client, seed_db, raw_tags, expected_tags):
    """DB에 비배열 JSON이나 비문자열 요소가 섞인 tags가 저장되어도 목록·상세 API는 200과 문자열 배열만 반환한다."""
    seed_db.article(article_id=1, tags=raw_tags)

    list_resp = client.get("/articles")
    assert list_resp.status_code == 200
    items = list_resp.json()["articles"]
    assert len(items) == 1
    assert items[0]["tags"] == expected_tags
    assert all(isinstance(tag, str) for tag in items[0]["tags"])

    detail_resp = client.get("/articles/1")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["tags"] == expected_tags
    assert all(isinstance(tag, str) for tag in detail["tags"])


@pytest.mark.parametrize(
    ("analysis_tags", "expected_tags"),
    [
        ("null", []),
        ("{}", []),
        ('["분석태그", 42]', ["분석태그"]),
    ],
)
def test_article_analysis_non_array_tags_normalized_to_string_list(client, seed_db, analysis_tags, expected_tags):
    """article_analysis.tags에 비배열 JSON이나 비문자열 요소가 있어도 목록·상세 API는 200과 문자열 배열만 반환한다."""
    seed_db.article(article_id=1, tags='["원본태그"]')
    seed_db.analysis(article_id=1, tags=analysis_tags)

    list_resp = client.get("/articles")
    assert list_resp.status_code == 200
    assert list_resp.json()["articles"][0]["tags"] == expected_tags

    detail_resp = client.get("/articles/1")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["tags"] == expected_tags


def test_articles_list_response_matches_schema_contract(client, seed_db):
    """GET /articles 응답 구조와 각 원소의 필드 집합이 ArticleListResponse·Article 스키마와 정확히 일치한다."""
    seed_db.article(
        article_id=1,
        source="네이버뉴스",
        title="스키마 계약 검증 기사",
        content="본문 내용",
        summary="기사 요약",
        major_category="IT",
        sub_category="클라우드",
        tags='["클라우드"]',
    )

    resp = client.get("/articles")
    assert resp.status_code == 200
    payload = resp.json()

    assert set(payload.keys()) == set(ArticleListResponse.model_fields.keys())
    validated = ArticleListResponse.model_validate(payload)
    assert len(validated.articles) == 1
    assert set(payload["articles"][0].keys()) == set(Article.model_fields.keys())


def test_article_detail_returns_single_article_with_analysis_coalesce(client, seed_db):
    """존재하는 ID로 GET /articles/{id} 요청 시 article_analysis가 COALESCE 병합된 단일 Article을 반환한다."""
    seed_db.article(
        article_id=42,
        url="https://example.com/42",
        source="네이버뉴스",
        title="원본 제목",
        content="원본 본문",
        published_at="2026-11-10T01:00:00Z",
        crawled_at="2026-11-10T10:00:00",
        summary="기본 요약",
        major_category="IT",
        sub_category="일반",
        tags='["기본"]',
    )
    seed_db.analysis(
        article_id=42,
        summary="LLM 보강 요약",
        major_category="AI",
        sub_category="에이전트",
        tags='["AI", "LLM"]',
    )

    resp = client.get("/articles/42")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == set(Article.model_fields.keys())
    Article.model_validate(data)

    assert data["id"] == 42
    assert data["summary"] == "LLM 보강 요약"
    assert data["major_category"] == "AI"
    assert data["sub_category"] == "에이전트"
    assert data["tags"] == ["AI", "LLM"]
    assert data["translation_status"] == "not_needed"


@pytest.mark.parametrize("missing_id", [9999, -1])
def test_article_detail_missing_id_returns_404_with_expected_detail(client, missing_id):
    """존재하지 않는 article_id 요청 시 HTTP 404와 'Article not found' 상세 메시지를 반환한다."""
    resp = client.get(f"/articles/{missing_id}")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Article not found"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/articles", "/articles/1", "/briefing", "/"])
def test_write_methods_are_not_allowed_on_read_only_endpoints(client, seed_db, method, path):
    """모든 기사·브리핑·상태 엔드포인트는 읽기 전용이므로 쓰기 메서드 요청을 405로 거부한다."""
    seed_db.article(article_id=1)
    resp = client.request(method, path)
    assert resp.status_code == 405


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page": 10001},
        {"size": 0},
        {"size": -1},
        {"size": 101},
        {"page": 2002, "size": 100},
        {"page": "abc"},
        {"size": "xyz"},
    ],
)
def test_articles_invalid_page_and_size_bounds_return_422(client, params):
    """page/size가 0·음수·상한 초과·비정수이면 현재 FastAPI/서비스 검증 정책대로 422를 반환한다."""
    resp = client.get("/articles", params=params)
    assert resp.status_code == 422
    assert "detail" in resp.json()


@pytest.mark.parametrize("size", [1, 100])
def test_articles_valid_size_boundaries_return_200(client, seed_db, size):
    """허용된 size 최소(1)와 최대(100) 경계값은 정상(200) 처리된다."""
    seed_db.article(article_id=1, crawled_at="2026-11-10T10:00:00")
    seed_db.article(article_id=2, crawled_at="2026-11-10T10:01:00")

    resp = client.get("/articles", params={"page": 1, "size": size})
    assert resp.status_code == 200
    body = resp.json()
    assert body["size"] == size
    assert len(body["articles"]) == min(size, 2)
