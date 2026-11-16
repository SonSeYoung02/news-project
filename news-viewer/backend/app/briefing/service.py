from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from app.briefing import repository
from app.briefing.cache import BriefingCandidateTuple, get_or_compute_briefing
from app.common.config import BRIEFING_MAX_ARTICLES
from app.common.runtime import resolve_main_attr

SELECTION_METHOD_DESCRIPTION = "주제·출처 다양성, 최신순을 반영한 규칙 기반 선정"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _article_time(value: Optional[str]) -> Optional[datetime]:
    if not value or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    if result.tzinfo is None:
        # 크롤러의 datetime.now()로 저장된 시각은 한국 로컬 시각이다.
        result = result.replace(tzinfo=timezone(timedelta(hours=9)))
    try:
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _compact_briefing_candidates(
    candidates: list[BriefingCandidateTuple],
    limit: int = BRIEFING_MAX_ARTICLES,
) -> list[BriefingCandidateTuple]:
    """선정 우선순위 4개 버킷을 보존하며 후보 풀을 상수 크기로 압축한다."""
    if len(candidates) <= limit:
        return candidates

    ordered = sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)
    kept: list[BriefingCandidateTuple] = []
    kept_ids: set[int] = set()

    def admit(item: BriefingCandidateTuple) -> None:
        aid = item[1]
        if aid not in kept_ids:
            kept_ids.add(aid)
            kept.append(item)

    # 1. (False, False) 버킷: 전체 상위 limit건
    for item in ordered[:limit]:
        admit(item)

    # 2. (False, True) 버킷: 출처별 최상위 1건씩 최대 limit개 출처
    seen_sources: set[str] = set()
    for item in ordered:
        source = item[2]
        if source not in seen_sources:
            seen_sources.add(source)
            admit(item)
            if len(seen_sources) >= limit:
                break

    # 3. (True, False) 버킷: 비어 있지 않은 주제별 최상위 1건씩 최대 limit개 주제
    seen_topics: set[str] = set()
    for item in ordered:
        topic = item[3]
        if topic and topic not in seen_topics:
            seen_topics.add(topic)
            admit(item)
            if len(seen_topics) >= limit:
                break

    # 4. (True, True) 버킷: 각 주제·출처 최대 limit건, 전체 최대 2*(limit-1)*limit + 1건
    max_tt = 2 * (limit - 1) * limit + 1
    tt_count = 0
    seen_pairs: set[tuple[str, str]] = set()
    topic_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for item in ordered:
        topic = item[3]
        if not topic:
            continue
        source = item[2]
        pair = (topic, source)
        if pair in seen_pairs:
            continue
        if topic_counts.get(topic, 0) >= limit or source_counts.get(source, 0) >= limit:
            continue
        seen_pairs.add(pair)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        admit(item)
        tt_count += 1
        if tt_count >= max_tt:
            break

    return kept


def _select_briefing_ids(
    candidates: list[BriefingCandidateTuple],
    limit: int = BRIEFING_MAX_ARTICLES,
) -> list[int]:
    remaining = list(candidates)
    selected_ids: list[int] = []
    sources: set[str] = set()
    topics: set[str] = set()
    while remaining and len(selected_ids) < limit:
        chosen = max(
            remaining,
            key=lambda item: (
                bool(item[3]) and item[3] not in topics,
                item[2] not in sources,
                item[0],
                item[1],
            ),
        )
        remaining.remove(chosen)
        selected_ids.append(chosen[1])
        sources.add(chosen[2])
        topics.add(chosen[3])
    return selected_ids


def _compute_briefing(now: datetime) -> dict:
    start = now - timedelta(hours=24)
    selected = repository.fetch_and_select_briefing_articles(
        window_start=start,
        window_end=now,
        parse_time_fn=_article_time,
        compact_fn=_compact_briefing_candidates,
        select_ids_fn=_select_briefing_ids,
    )
    return {
        "generated_at": now.isoformat(),
        "window_start": start.isoformat(),
        "window_end": now.isoformat(),
        "selection_method": SELECTION_METHOD_DESCRIPTION,
        "articles": selected,
    }


def get_briefing_data() -> dict:
    utc_now_fn = resolve_main_attr("_utc_now", _utc_now)
    compute_fn = resolve_main_attr("_compute_briefing", _compute_briefing)
    now = utc_now_fn()
    return get_or_compute_briefing(now, compute_fn)
