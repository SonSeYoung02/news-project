from typing import Optional

from pydantic import BaseModel, Field


class Article(BaseModel):
    """기사 응답 모델. `title`·`content`는 완료된 번역이 있으면 번역문, 없으면 원문이다."""

    id: int = Field(description="기사 ID")
    url: str = Field(description="원문 기사 URL")
    source: str = Field(
        description="출처 문자열 (예: 네이버뉴스, GeekNews, Google News, GitHub Trending, Hugging Face, arXiv, dev.to)"
    )
    title: str = Field(
        description="표시용 제목. 현재 원문 해시와 일치하는 completed 번역이 있으면 번역 제목, 없으면 원문 제목"
    )
    content: Optional[str] = Field(
        None, description="표시용 본문. 현재 원문 해시와 일치하는 completed 번역이 있으면 번역 본문, 없으면 원문 본문"
    )
    published_at: Optional[str] = Field(None, description="출처 게시 시각 (크롤러가 저장한 문자열 그대로)")
    crawled_at: Optional[str] = Field(None, description="최초 수집 시각 (크롤러가 저장한 문자열 그대로)")
    summary: Optional[str] = Field(None, description="요약. article_analysis 값 우선, 없으면 articles 값")
    major_category: Optional[str] = Field(None, description="대분류 (예: AI, IT, 경제, 국제)")
    sub_category: Optional[str] = Field(None, description="소분류. 브리핑 선정 시 주제 단위로 사용")
    tags: list[str] = Field([], description="태그 목록. 저장값이 배열이 아니거나 잘못되었으면 빈 배열")
    original_title: Optional[str] = Field(None, description="원문 제목")
    original_content: Optional[str] = Field(None, description="원문 본문")
    translated_title: Optional[str] = Field(
        None, description="번역 제목. translation_status가 completed일 때만 값이 있음"
    )
    translated_content: Optional[str] = Field(
        None, description="번역 본문. translation_status가 completed일 때만 값이 있음"
    )
    translation_status: Optional[str] = Field(
        "pending",
        description=(
            "번역 상태. completed(검증 통과 번역 있음), pending(대기 또는 번역 레코드 없는 영어 기사), "
            "failed(영구 오류 누적 3회 이상, 다음 실행에서 재시도 가능), "
            "not_needed(번역 레코드 없는 한국어 출처 기사)"
        ),
    )


class ArticleListResponse(BaseModel):
    """기사 목록 페이지 응답."""

    total: int = Field(description="필터·검색 조건에 맞는 전체 기사 수")
    page: int = Field(description="요청한 페이지 번호")
    size: int = Field(description="요청한 페이지 크기")
    articles: list[Article] = Field(description="해당 페이지의 기사 목록 (crawled_at 내림차순, id 내림차순)")
