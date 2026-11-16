from pydantic import BaseModel

from app.article.schemas import Article


class BriefingResponse(BaseModel):
    generated_at: str
    window_start: str
    window_end: str
    selection_method: str
    articles: list[Article]
