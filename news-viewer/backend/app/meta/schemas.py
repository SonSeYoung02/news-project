from pydantic import BaseModel, Field


class CategoryCount(BaseModel):
    """대분류별 기사 수."""

    major_category: str = Field(description="대분류 (article_analysis 값 우선)")
    count: int = Field(description="기사 수")


class SourceCount(BaseModel):
    """출처별 기사 수."""

    source: str = Field(description="출처 문자열")
    count: int = Field(description="기사 수")
