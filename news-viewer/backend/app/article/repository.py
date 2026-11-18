from typing import Optional

from app.common.database import (
    _article_select_fields,
    _has_translations_table,
    get_connection,
    map_row_to_dict,
)


def _escape_like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_paginated(
    page: int,
    size: int,
    offset: int,
    category: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
) -> tuple[int, list[dict]]:
    with get_connection() as conn:
        has_trans = _has_translations_table(conn)

        conditions = []
        params: list = []

        if category:
            conditions.append("COALESCE(aa.major_category, a.major_category) = ?")
            params.append(category)
        if source:
            conditions.append("a.source = ?")
            params.append(source)
        if q:
            like_pattern = _escape_like_pattern(q)
            if has_trans:
                conditions.append(
                    """(
                        a.title LIKE ? ESCAPE '\\'
                        OR (at.status = 'completed' AND at.translated_title LIKE ? ESCAPE '\\')
                        OR a.content LIKE ? ESCAPE '\\'
                        OR (at.status = 'completed' AND at.translated_content LIKE ? ESCAPE '\\')
                        OR COALESCE(aa.summary, a.summary) LIKE ? ESCAPE '\\'
                    )"""
                )
                params.extend([like_pattern] * 5)
            else:
                conditions.append(
                    "(a.title LIKE ? ESCAPE '\\' OR a.content LIKE ? ESCAPE '\\' OR COALESCE(aa.summary, a.summary) LIKE ? ESCAPE '\\')"
                )
                params.extend([like_pattern] * 3)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        trans_join = (
            """
            LEFT JOIN article_translations at
                ON at.article_id = a.id
                AND at.content_hash = compute_content_hash(a.title, a.content)
            """
            if has_trans
            else ""
        )
        base_query = f"""
            FROM articles a
            LEFT JOIN article_analysis aa ON aa.article_id = a.id
            {trans_join}
            {where}
        """
        select_fields = _article_select_fields(has_trans=has_trans, use_analysis=True)

        total = conn.execute(f"SELECT COUNT(*) {base_query}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT
                {select_fields}
            {base_query}
            ORDER BY a.crawled_at DESC, a.id DESC LIMIT ? OFFSET ?
            """,
            params + [size, offset],
        ).fetchall()

    return total, [map_row_to_dict(r) for r in rows]


def find_by_id(article_id: int) -> Optional[dict]:
    with get_connection() as conn:
        has_trans = _has_translations_table(conn)
        trans_join = (
            """
            LEFT JOIN article_translations at
                ON at.article_id = a.id
                AND at.content_hash = compute_content_hash(a.title, a.content)
            """
            if has_trans
            else ""
        )
        select_fields = _article_select_fields(has_trans=has_trans, use_analysis=True)
        row = conn.execute(
            f"""
            SELECT
                {select_fields}
            FROM articles a
            LEFT JOIN article_analysis aa ON aa.article_id = a.id
            {trans_join}
            WHERE a.id = ?
            """,
            (article_id,),
        ).fetchone()

    if not row:
        return None
    return map_row_to_dict(row)
