from datetime import datetime
from typing import Callable

from app.briefing.cache import BriefingCandidateTuple
from app.common.config import (
    BRIEFING_COMPACT_THRESHOLD,
    BRIEFING_SCAN_BATCH_SIZE,
)
from app.common.database import (
    _article_select_fields,
    _has_translations_table,
    get_connection,
    map_row_to_dict,
)


def fetch_and_select_briefing_articles(
    window_start: datetime,
    window_end: datetime,
    parse_time_fn: Callable,
    compact_fn: Callable,
    select_ids_fn: Callable,
) -> list[dict]:
    """단일 DB 연결 내에서 24시간 내 AI 후보를 스트리밍 스캔·압축하고 선정된 기사 상세를 조회한다."""
    pool: list[BriefingCandidateTuple] = []

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT a.id, a.source, a.published_at, a.crawled_at, a.sub_category
            FROM articles a
            WHERE a.major_category = ?
            """,
            ("AI",),
        )
        try:
            while True:
                batch = cursor.fetchmany(BRIEFING_SCAN_BATCH_SIZE)
                if not batch:
                    break
                for row in batch:
                    published = parse_time_fn(row["published_at"]) or parse_time_fn(
                        row["crawled_at"]
                    )
                    if published is None or not (window_start <= published <= window_end):
                        continue
                    topic = (row["sub_category"] or "").strip()
                    pool.append((published, row["id"], row["source"], topic))
                if len(pool) >= BRIEFING_COMPACT_THRESHOLD:
                    pool = compact_fn(pool)
        finally:
            cursor.close()

        selected_ids = select_ids_fn(pool)
        if not selected_ids:
            return []

        has_trans = _has_translations_table(conn)
        placeholders = ", ".join("?" for _ in selected_ids)
        trans_join = (
            """
            LEFT JOIN article_translations at
                ON at.article_id = a.id
                AND at.content_hash = compute_content_hash(a.title, a.content)
            """
            if has_trans
            else ""
        )
        select_fields = _article_select_fields(has_trans=has_trans, use_analysis=False)
        rows = conn.execute(
            f"""
            SELECT
                {select_fields}
            FROM articles a
            {trans_join}
            WHERE a.id IN ({placeholders})
            """,
            selected_ids,
        ).fetchall()
        by_id = {row["id"]: map_row_to_dict(row) for row in rows}
        return [by_id[aid] for aid in selected_ids if aid in by_id]
