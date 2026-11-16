from fastapi import APIRouter

from app.briefing import service
from app.briefing.schemas import BriefingResponse

router = APIRouter()


@router.get(
    "/briefing",
    response_model=BriefingResponse,
    summary="오늘의 AI 브리핑",
    description="최근 24시간 동안 수집/발행된 AI 기사 중 주제 및 출처 다양성을 고려한 핵심 브리핑 목록을 반환합니다. 번역 완료 기사는 한국어 번역문을 우선 제공합니다.",
    tags=["articles"],
)
def get_briefing():
    return service.get_briefing_data()
