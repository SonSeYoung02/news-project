from app.common.database import get_connection


def count_by_categories() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(aa.major_category, a.major_category) AS major_category,
                   COUNT(*) as count
            FROM articles a
            LEFT JOIN article_analysis aa ON aa.article_id = a.id
            WHERE COALESCE(aa.major_category, a.major_category) IS NOT NULL
            GROUP BY COALESCE(aa.major_category, a.major_category)
            ORDER BY count DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def count_by_sources() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC"
        ).fetchall()
    return [dict(r) for r in rows]
