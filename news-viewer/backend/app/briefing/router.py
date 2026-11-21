from fastapi import APIRouter

from app.briefing import service
from app.briefing.schemas import BriefingResponse

router = APIRouter()


@router.get(
    "/briefing",
    response_model=BriefingResponse,
    summary="오늘의 AI 브리핑",
    description=(
        "최근 24시간 동안 수집/발행된 AI 기사 중 주제 및 출처 다양성을 고려한 핵심 브리핑 목록을 반환합니다. "
        "번역 완료 기사는 한국어 번역문을 우선 제공합니다. "
        "대상은 articles.major_category가 AI인 기사이며, 기사 시각은 published_at(파싱 불가 시 crawled_at)을 쓰고 "
        "시간대가 없는 값은 한국 시간으로 해석합니다. "
        "아직 고르지 않은 주제(sub_category) → 아직 고르지 않은 출처 → 최신순 → ID 큰 순으로 최대 5건을 고릅니다. "
        "결과는 DB 파일이 바뀌지 않는 동안 30초간 캐시됩니다."
    ),
    tags=["articles"],
)
def get_briefing():
    return service.get_briefing_data()
