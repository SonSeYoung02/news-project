from fastapi import APIRouter

from app.meta import repository
from app.meta.schemas import CategoryCount, SourceCount

router = APIRouter()


@router.get(
    "/categories",
    response_model=list[CategoryCount],
    summary="카테고리 목록 조회",
    description="기사에 사용된 대분류 카테고리와 각 카테고리의 기사 수를 반환합니다.",
    tags=["meta"],
)
def get_categories():
    return repository.count_by_categories()


@router.get(
    "/sources",
    response_model=list[SourceCount],
    summary="출처 목록 조회",
    description="크롤링에 사용된 뉴스 출처와 각 출처의 기사 수를 반환합니다.",
    tags=["meta"],
)
def get_sources():
    return repository.count_by_sources()
