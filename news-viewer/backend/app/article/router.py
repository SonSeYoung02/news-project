from typing import Optional

from fastapi import APIRouter, Query
from fastapi import Path as ApiPath

from app.article import service
from app.article.schemas import Article, ArticleListResponse
from app.common.config import (
    MAX_FILTER_LENGTH,
    MAX_PAGE,
    MAX_SEARCH_QUERY_LENGTH,
    SQLITE_MAX_INT64,
    SQLITE_MIN_INT64,
)
from app.common.schemas import ErrorResponse

router = APIRouter()


@router.get(
    "/articles",
    response_model=ArticleListResponse,
    summary="기사 목록 조회",
    description="크롤링된 뉴스 기사 목록을 페이지네이션으로 반환합니다. 카테고리·출처·키워드로 필터링할 수 있습니다. 번역 완료 기사는 한국어 번역문을 우선 제공합니다.",
    tags=["articles"],
)
def get_articles(
    page: int = Query(1, ge=1, le=MAX_PAGE, description=f"페이지 번호 (1~{MAX_PAGE})"),
    size: int = Query(20, ge=1, le=100, description="페이지당 기사 수 (최대 100)"),
    category: Optional[str] = Query(
        None, max_length=MAX_FILTER_LENGTH, description="대분류 일치 필터 (예: AI, IT, 경제, 국제)"
    ),
    source: Optional[str] = Query(
        None, max_length=MAX_FILTER_LENGTH, description="출처 문자열 일치 필터 (예: 네이버뉴스, Google News, dev.to)"
    ),
    q: Optional[str] = Query(
        None,
        max_length=MAX_SEARCH_QUERY_LENGTH,
        description="부분 일치 검색어. 원문 제목·본문, 요약, completed 번역 제목·본문을 검색",
    ),
):
    return service.list_articles(page=page, size=size, category=category, source=source, q=q)


@router.get(
    "/articles/{article_id}",
    response_model=Article,
    summary="기사 상세 조회",
    description="article_id로 단일 기사의 전체 정보를 반환합니다. 번역 완료 기사는 한국어 번역문을 우선 제공하며, 미번역 시 원문을 반환합니다. 존재하지 않으면 404를 반환합니다.",
    tags=["articles"],
    responses={404: {"model": ErrorResponse, "description": "해당 ID의 기사가 없음 (detail: Article not found)"}},
)
def get_article(
    article_id: int = ApiPath(
        ...,
        ge=SQLITE_MIN_INT64,
        le=SQLITE_MAX_INT64,
        description="조회할 기사 ID (SQLite 64비트 정수 범위)",
    ),
):
    return service.get_article_by_id(article_id)
