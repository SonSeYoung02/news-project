from typing import Optional
from pydantic import BaseModel


class Article(BaseModel):
    id: int
    url: str
    source: str
    title: str
    content: Optional[str] = None
    published_at: Optional[str] = None
    crawled_at: Optional[str] = None
    summary: Optional[str] = None
    major_category: Optional[str] = None
    sub_category: Optional[str] = None
    tags: list[str] = []
    original_title: Optional[str] = None
    original_content: Optional[str] = None
    translated_title: Optional[str] = None
    translated_content: Optional[str] = None
    translation_status: Optional[str] = "pending"


class ArticleListResponse(BaseModel):
    total: int
    page: int
    size: int
    articles: list[Article]
