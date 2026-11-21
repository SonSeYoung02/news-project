from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """HTTPException으로 반환하는 FastAPI 기본 오류 응답 형식."""

    detail: str = Field(description="오류 설명 메시지", examples=["Article not found"])
