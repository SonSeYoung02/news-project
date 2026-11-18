"""app.article.service 순수 비즈니스 규칙 단위 테스트."""

from fastapi import HTTPException
import pytest

from app.article import service
from app.common.config import MAX_OFFSET, MAX_PAGE


@pytest.mark.parametrize(
    ("page", "size", "expected_offset"),
    [
        (1, 1, 0),
        (1, 20, 0),
        (3, 15, 30),
        (2001, 100, MAX_OFFSET),
        (MAX_PAGE, 1, MAX_PAGE - 1),
        (MAX_PAGE, 20, (MAX_PAGE - 1) * 20),
    ],
)
def test_validate_pagination_calculates_valid_offset(page, size, expected_offset):
    """유효한 page/size 입력은 SQL OFFSET((page - 1) * size)을 정확히 계산해 반환한다."""
    assert service.validate_pagination(page, size) == expected_offset


@pytest.mark.parametrize(
    ("page", "size", "expected_detail"),
    [
        (0, 20, f"page must be between 1 and {MAX_PAGE}"),
        (-1, 20, f"page must be between 1 and {MAX_PAGE}"),
        (MAX_PAGE + 1, 1, f"page must be between 1 and {MAX_PAGE}"),
        (1, 0, "size must be between 1 and 100"),
        (1, -5, "size must be between 1 and 100"),
        (1, 101, "size must be between 1 and 100"),
        (2002, 100, f"Calculated offset exceeds maximum allowed ({MAX_OFFSET})"),
        (MAX_PAGE, 21, f"Calculated offset exceeds maximum allowed ({MAX_OFFSET})"),
    ],
)
def test_validate_pagination_rejects_out_of_bounds_values(page, size, expected_detail):
    """page/size 범위나 계산된 offset 상한을 초과하면 서비스 계층에서 422 HTTPException을 발생시킨다."""
    with pytest.raises(HTTPException) as exc_info:
        service.validate_pagination(page, size)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == expected_detail


@pytest.mark.parametrize("valid_value", [None, "", "AI", "검색어 테스트"])
def test_reject_nul_byte_allows_safe_inputs(valid_value):
    """NUL 바이트가 없는 문자열이나 None은 검증을 그대로 통과한다."""
    service._reject_nul_byte(valid_value, "q")


@pytest.mark.parametrize("field_name", ["category", "source", "q"])
def test_reject_nul_byte_raises_422_with_field_name(field_name):
    """문자열에 NUL 바이트(\\x00)가 포함되면 필드명을 담은 422 HTTPException을 발생시킨다."""
    with pytest.raises(HTTPException) as exc_info:
        service._reject_nul_byte("bad\x00input", field_name)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == f"{field_name} contains an invalid NUL character"


def test_list_articles_delegates_computed_offset_and_formats_response(monkeypatch):
    """list_articles는 계산된 offset을 repository에 전달하고 total·page·size·articles 계약을 반환한다."""
    captured = {}

    def fake_find_paginated(*, page, size, offset, category, source, q):
        captured.update(
            {
                "page": page,
                "size": size,
                "offset": offset,
                "category": category,
                "source": source,
                "q": q,
            }
        )
        return 12, [{"id": 99, "title": "모의 기사"}]

    monkeypatch.setattr(service.repository, "find_paginated", fake_find_paginated)

    result = service.list_articles(
        page=3,
        size=10,
        category="AI",
        source="devto",
        q="LLM",
    )

    assert captured == {
        "page": 3,
        "size": 10,
        "offset": 20,
        "category": "AI",
        "source": "devto",
        "q": "LLM",
    }
    assert result == {
        "total": 12,
        "page": 3,
        "size": 10,
        "articles": [{"id": 99, "title": "모의 기사"}],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"q": "abc\x00"},
        {"category": "AI\x00"},
        {"source": "devto\x00"},
        {"page": 0, "size": 20},
        {"page": 1, "size": 101},
    ],
)
def test_list_articles_rejects_invalid_input_before_calling_repository(monkeypatch, kwargs):
    """NUL 바이트나 페이지 경계 위반 입력 시 repository를 호출하지 않고 즉시 422를 반환한다."""
    called = False

    def fail_if_called(**_):
        nonlocal called
        called = True
        return 0, []

    monkeypatch.setattr(service.repository, "find_paginated", fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        service.list_articles(**kwargs)

    assert exc_info.value.status_code == 422
    assert called is False


def test_get_article_by_id_returns_found_article_or_raises_404(monkeypatch):
    """단건 조회 시 repository 결과가 있으면 그대로 반환하고 없으면 404 'Article not found'를 발생시킨다."""
    monkeypatch.setattr(
        service.repository,
        "find_by_id",
        lambda article_id: {"id": article_id, "title": "존재 기사"} if article_id == 7 else None,
    )

    assert service.get_article_by_id(7) == {"id": 7, "title": "존재 기사"}

    with pytest.raises(HTTPException) as exc_info:
        service.get_article_by_id(404)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Article not found"
