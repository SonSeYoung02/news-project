from pydantic import BaseModel, Field

from app.article.schemas import Article


class BriefingResponse(BaseModel):
    """오늘의 AI 브리핑 응답."""

    generated_at: str = Field(description="브리핑 계산 시각 (UTC ISO 8601)")
    window_start: str = Field(description="대상 구간 시작 (generated_at - 24시간, UTC ISO 8601)")
    window_end: str = Field(description="대상 구간 끝 (generated_at, UTC ISO 8601)")
    selection_method: str = Field(description="선정 방식 설명")
    articles: list[Article] = Field(description="선정된 기사 목록 (최대 5건, 선정 순서). 대상이 없으면 빈 배열")
