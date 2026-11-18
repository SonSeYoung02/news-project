from typing import Optional

from fastapi import HTTPException

from app.article import repository
from app.common.config import MAX_OFFSET, MAX_PAGE


def _reject_nul_byte(value: Optional[str], field_name: str) -> None:
    if value is not None and "\x00" in value:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} contains an invalid NUL character",
        )


def validate_pagination(page: int, size: int) -> int:
    if page < 1 or page > MAX_PAGE:
        raise HTTPException(
            status_code=422,
            detail=f"page must be between 1 and {MAX_PAGE}",
        )
    if size < 1 or size > 100:
        raise HTTPException(
            status_code=422,
            detail="size must be between 1 and 100",
        )

    offset = (page - 1) * size
    if offset > MAX_OFFSET:
        raise HTTPException(
            status_code=422,
            detail=f"Calculated offset exceeds maximum allowed ({MAX_OFFSET})",
        )
    return offset


def list_articles(
    page: int = 1,
    size: int = 20,
    category: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
) -> dict:
    _reject_nul_byte(category, "category")
    _reject_nul_byte(source, "source")
    _reject_nul_byte(q, "q")
    offset = validate_pagination(page, size)

    total, articles = repository.find_paginated(
        page=page,
        size=size,
        offset=offset,
        category=category,
        source=source,
        q=q,
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "articles": articles,
    }


def get_article_by_id(article_id: int) -> dict:
    article = repository.find_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
