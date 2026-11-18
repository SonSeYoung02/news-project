"""app.article.repository SQLite 조회·COALESCE·번역 폴백·파라미터 바인딩 의도 기반 테스트."""

import pytest

from app.article import repository
from app.common.database import compute_content_hash


def test_coalesce_prioritizes_article_analysis_and_falls_back_per_column(seed_db):
    """article_analysis 값이 있으면 우선하고, 없거나 컬럼이 NULL이면 articles 기본값으로 폴백한다."""
    # 1. 전체 분석 보강 기사
    seed_db.article(
        article_id=1,
        title="기사 1",
        crawled_at="2026-11-10T12:03:00",
        summary="기본 요약 1",
        major_category="IT",
        sub_category="일반",
        tags='["기본태그"]',
    )
    seed_db.analysis(
        article_id=1,
        summary="보강 요약 1",
        major_category="AI",
        sub_category="LLM",
        tags='["AI", "에이전트"]',
    )

    # 2. 일부 컬럼만 보강된 기사 (summary만 존재, 나머지 NULL → articles 기본값 유지)
    seed_db.article(
        article_id=2,
        title="기사 2",
        crawled_at="2026-11-10T12:02:00",
        summary="기본 요약 2",
        major_category="경제",
        sub_category="거시",
        tags='["금리"]',
    )
    seed_db.analysis(
        article_id=2,
        summary="보강 요약 2",
        major_category=None,
        sub_category=None,
        tags=None,
    )

    # 3. 분석 행이 전혀 없는 기사
    seed_db.article(
        article_id=3,
        title="기사 3",
        crawled_at="2026-11-10T12:01:00",
        summary="기본 요약 3",
        major_category="과학",
        sub_category="우주",
        tags='["로켓"]',
    )

    total, rows = repository.find_paginated(page=1, size=10, offset=0)
    assert total == 3
    by_id = {row["id"]: row for row in rows}

    assert by_id[1]["summary"] == "보강 요약 1"
    assert by_id[1]["major_category"] == "AI"
    assert by_id[1]["sub_category"] == "LLM"
    assert by_id[1]["tags"] == ["AI", "에이전트"]

    assert by_id[2]["summary"] == "보강 요약 2"
    assert by_id[2]["major_category"] == "경제"
    assert by_id[2]["sub_category"] == "거시"
    assert by_id[2]["tags"] == ["금리"]

    assert by_id[3]["summary"] == "기본 요약 3"
    assert by_id[3]["major_category"] == "과학"
    assert by_id[3]["sub_category"] == "우주"
    assert by_id[3]["tags"] == ["로켓"]

    detail1 = repository.find_by_id(1)
    assert detail1 is not None
    assert detail1["summary"] == "보강 요약 1"
    assert detail1["major_category"] == "AI"


def test_coalesce_applies_to_category_filter_and_summary_search(seed_db):
    """카테고리 필터와 요약 검색은 원문 기본값이 아니라 COALESCE 병합 결과를 기준으로 동작한다."""
    seed_db.article(
        article_id=10,
        title="중립 제목",
        content="중립 본문",
        summary="폐기된원문요약",
        major_category="IT",
    )
    seed_db.analysis(
        article_id=10,
        summary="신규보강요약",
        major_category="AI",
    )

    assert repository.find_paginated(page=1, size=10, offset=0, category="AI")[0] == 1
    assert repository.find_paginated(page=1, size=10, offset=0, category="IT")[0] == 0
    assert repository.find_paginated(page=1, size=10, offset=0, q="신규보강요약")[0] == 1
    assert repository.find_paginated(page=1, size=10, offset=0, q="폐기된원문요약")[0] == 0


def test_completed_translation_with_matching_hash_prioritizes_korean(seed_db):
    """status='completed'이고 원문 해시가 일치하면(공백 정규화 포함) 한국어 번역 제목·본문을 우선 반환한다."""
    raw_title = "  Agentic Coding Workflow  "
    raw_content = "\nMulti-step verification improves quality.\t"
    normalized_hash = compute_content_hash(raw_title.strip(), raw_content.strip())

    seed_db.article(
        article_id=1,
        source="devto",
        title=raw_title,
        content=raw_content,
    )
    seed_db.translation(
        article_id=1,
        content_hash=normalized_hash,
        translated_title="에이전트 코딩 워크플로",
        translated_content="다단계 검증이 품질을 높입니다.",
        status="completed",
    )

    total, rows = repository.find_paginated(page=1, size=10, offset=0)
    assert total == 1
    for item in (rows[0], repository.find_by_id(1)):
        assert item is not None
        assert item["title"] == "에이전트 코딩 워크플로"
        assert item["content"] == "다단계 검증이 품질을 높입니다."
        assert item["original_title"] == raw_title
        assert item["original_content"] == raw_content
        assert item["translated_title"] == "에이전트 코딩 워크플로"
        assert item["translated_content"] == "다단계 검증이 품질을 높입니다."
        assert item["translation_status"] == "completed"


def test_translation_hash_mismatch_falls_back_to_original(seed_db):
    """번역 status='completed'라도 원문 해시가 다르면 구번역을 무시하고 원문으로 폴백한다."""
    stale_hash = compute_content_hash("Old English Title", "Old English Content")
    seed_db.article(
        article_id=1,
        source="devto",
        title="Updated English Title",
        content="Updated English Content",
    )
    seed_db.translation(
        article_id=1,
        content_hash=stale_hash,
        translated_title="오래된 한국어 제목",
        translated_content="오래된 한국어 본문",
        status="completed",
    )

    _, rows = repository.find_paginated(page=1, size=10, offset=0)
    detail = repository.find_by_id(1)

    for item in (rows[0], detail):
        assert item is not None
        assert item["title"] == "Updated English Title"
        assert item["content"] == "Updated English Content"
        assert item["translated_title"] is None
        assert item["translated_content"] is None
        assert item["translation_status"] == "pending"


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_incomplete_translation_status_falls_back_and_is_excluded_from_search(seed_db, status):
    """해시가 일치하더라도 번역 status가 completed가 아니면 원문으로 폴백하고 번역문 검색 대상에서 제외된다."""
    title = "English Source Title"
    content = "English Source Content"
    content_hash = compute_content_hash(title, content)

    seed_db.article(
        article_id=1,
        source="huggingface",
        title=title,
        content=content,
    )
    seed_db.translation(
        article_id=1,
        content_hash=content_hash,
        translated_title="미완료임시제목",
        translated_content="미완료임시본문",
        status=status,
    )

    detail = repository.find_by_id(1)
    assert detail is not None
    assert detail["title"] == title
    assert detail["content"] == content
    assert detail["translated_title"] is None
    assert detail["translated_content"] is None
    assert detail["translation_status"] == status

    # 미완료 번역문 키워드로는 검색되지 않아야 한다.
    assert repository.find_paginated(page=1, size=10, offset=0, q="미완료임시제목")[0] == 0
    assert repository.find_paginated(page=1, size=10, offset=0, q="미완료임시본문")[0] == 0


def test_completed_translation_with_empty_title_falls_back_to_original_title(seed_db):
    """번역 완료 행에서 translated_title이 빈 문자열이면 제목만 원문으로 폴백하고 본문은 번역을 사용한다."""
    title = "Original Title Kept"
    content = "Original Content"
    seed_db.article(article_id=1, source="devto", title=title, content=content)
    seed_db.translation(
        article_id=1,
        content_hash=compute_content_hash(title, content),
        translated_title="",
        translated_content="번역된 본문만 존재",
        status="completed",
    )

    detail = repository.find_by_id(1)
    assert detail is not None
    assert detail["title"] == title
    assert detail["content"] == "번역된 본문만 존재"
    assert detail["translation_status"] == "completed"


def test_multiple_translation_hashes_join_only_current_original_hash(seed_db):
    """동일 기사에 구버전·현버전 해시 번역 행이 함께 있어도 중복 행 없이 현재 원문 해시만 조인한다."""
    seed_db.article(
        article_id=1,
        source="devto",
        title="Current Title",
        content="Current Content",
    )
    seed_db.translation(
        article_id=1,
        content_hash=compute_content_hash("Old Title", "Old Content"),
        translated_title="구버전 번역",
        translated_content="구버전 본문",
        status="completed",
    )
    seed_db.translation(
        article_id=1,
        content_hash=compute_content_hash("Current Title", "Current Content"),
        translated_title=None,
        translated_content=None,
        status="pending",
    )

    total, rows = repository.find_paginated(page=1, size=10, offset=0)
    assert total == 1
    assert len(rows) == 1
    assert rows[0]["title"] == "Current Title"
    assert rows[0]["translation_status"] == "pending"


def test_repository_works_without_article_translations_table(seed_legacy_db):
    """article_translations 테이블이 없는 구형 DB에서도 기사 목록·상세 조회가 원문 폴백으로 동작한다."""
    seed_legacy_db.article(
        article_id=1,
        source="devto",
        title="English Legacy",
        crawled_at="2026-11-10T10:00:00",
    )
    seed_legacy_db.article(
        article_id=2,
        source="네이버뉴스",
        title="한국어 레거시",
        crawled_at="2026-11-10T10:01:00",
    )

    total, rows = repository.find_paginated(page=1, size=10, offset=0)
    assert total == 2
    by_id = {row["id"]: row for row in rows}
    assert by_id[1]["translation_status"] == "pending"
    assert by_id[2]["translation_status"] == "not_needed"
    assert repository.find_by_id(1)["title"] == "English Legacy"


def test_escape_like_pattern_escapes_wildcards_and_backslash():
    """LIKE 패턴 이스케이프 함수는 백슬래시·%·_ 를 이스케이프하고 양끝에 %를 붙인다."""
    assert repository._escape_like_pattern("100% ai_v2\\path") == "%100\\% ai\\_v2\\\\path%"


def test_special_characters_in_q_category_source_match_literals_without_sql_error(seed_db):
    """따옴표·%·_·백슬래시 특수문자를 포함한 검색어와 필터가 SQL 바인딩으로 오류 없이 리터럴 일치한다."""
    seed_db.article(
        article_id=1,
        source="dev_to's",
        major_category="AI's & \"ML\"",
        title="O'Reilly's Guide on 50% Growth",
        content='New "AI" model_v2 and dir\\name release',
        summary="핵심 50% 지표",
        crawled_at="2026-11-10T12:01:00",
    )
    # % 와 _ 가 와일드카드로 오작동하는지 검증할 대조군 기사
    seed_db.article(
        article_id=2,
        source="devxto's",
        major_category="AI's & \"ML\"",
        title="500 Growth Overview",
        content="modelxv2 comparison",
        summary="일반 지표",
        crawled_at="2026-11-10T12:00:00",
    )

    for term in ("O'Reilly", '"AI"', "50%", "model_v2", "dir\\name"):
        total, rows = repository.find_paginated(page=1, size=10, offset=0, q=term)
        assert total == 1, f"term={term!r} failed"
        assert [row["id"] for row in rows] == [1]

    # category / source 필터에도 따옴표와 특수문자가 안전하게 바인딩된다.
    total_cat_src, filtered = repository.find_paginated(
        page=1,
        size=10,
        offset=0,
        category="AI's & \"ML\"",
        source="dev_to's",
    )
    assert total_cat_src == 1
    assert [row["id"] for row in filtered] == [1]


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "'; DROP TABLE articles; --",
        "' UNION SELECT 1,2,3 --",
        "\" OR \"\"=\"",
    ],
)
def test_sql_injection_payloads_are_safely_bound_without_leaking_or_dropping(seed_db, payload):
    """SQL 인젝션 문자열이 q·category·source에 들어와도 바인딩으로 무력화되어 데이터를 유출·훼손하지 않는다."""
    seed_db.article(article_id=1, title="정상 기사 1", major_category="AI", source="devto")
    seed_db.article(article_id=2, title="정상 기사 2", major_category="IT", source="네이버뉴스")

    assert repository.find_paginated(page=1, size=10, offset=0, q=payload) == (0, [])
    assert repository.find_paginated(page=1, size=10, offset=0, category=payload) == (0, [])
    assert repository.find_paginated(page=1, size=10, offset=0, source=payload) == (0, [])
    assert seed_db.count_articles() == 2
