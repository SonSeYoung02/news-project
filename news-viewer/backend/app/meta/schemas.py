from pydantic import BaseModel


class CategoryCount(BaseModel):
    major_category: str
    count: int


class SourceCount(BaseModel):
    source: str
    count: int
