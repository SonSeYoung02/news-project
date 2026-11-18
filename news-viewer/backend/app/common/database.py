import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.common.config import _KOREAN_SOURCES_SQL, DB_PATH
from app.common.runtime import resolve_main_attr


def compute_content_hash(title: str, content: str) -> str:
    """원문 제목과 본문의 해시를 생성하여 원문 변경 여부를 판별한다."""
    normalized = f"{(title or '').strip()}\n{(content or '').strip()}".encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _get_active_db_path() -> Path:
    active_db_path = resolve_main_attr("DB_PATH", DB_PATH)
    return Path(os.environ.get("DB_PATH", str(active_db_path)))


@contextmanager
def _connect():
    conn = sqlite3.connect(_get_active_db_path())
    conn.row_factory = sqlite3.Row
    hash_fn = resolve_main_attr("compute_content_hash", compute_content_hash)
    conn.create_function("compute_content_hash", 2, hash_fn)
    try:
        yield conn
    finally:
        conn.close()


def get_connection():
    """런타임에 패치 가능한 _connect 컨텍스트 매니저를 반환한다."""
    connect_fn = resolve_main_attr("_connect", _connect)
    return connect_fn()


def _has_translations_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='article_translations'"
    ).fetchone()
    return row is not None


def _row_to_dict(row) -> dict:
    d = dict(row)
    tags = d.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    if isinstance(tags, list):
        d["tags"] = [item for item in tags if isinstance(item, str)]
    else:
        d["tags"] = []
    return d


def map_row_to_dict(row) -> dict:
    """런타임에 패치 가능한 _row_to_dict 함수를 통해 Row를 dict로 변환한다."""
    mapper = resolve_main_attr("_row_to_dict", _row_to_dict)
    return mapper(row)


def _article_select_fields(has_trans: bool, use_analysis: bool) -> str:
    meta_fields = (
        """
        COALESCE(aa.summary, a.summary) AS summary,
        COALESCE(aa.major_category, a.major_category) AS major_category,
        COALESCE(aa.sub_category, a.sub_category) AS sub_category,
        COALESCE(aa.tags, a.tags) AS tags
        """
        if use_analysis
        else """
        a.summary AS summary,
        a.major_category AS major_category,
        a.sub_category AS sub_category,
        a.tags AS tags
        """
    )
    if has_trans:
        return f"""
            a.id, a.url, a.source,
            a.published_at, a.crawled_at,
            a.title AS original_title,
            a.content AS original_content,
            CASE
                WHEN at.status = 'completed' AND at.translated_title IS NOT NULL AND at.translated_title != ''
                THEN at.translated_title
                ELSE a.title
            END AS title,
            CASE
                WHEN at.status = 'completed' AND at.translated_content IS NOT NULL AND at.translated_content != ''
                THEN at.translated_content
                ELSE a.content
            END AS content,
            CASE
                WHEN at.status = 'completed' THEN at.translated_title
                ELSE NULL
            END AS translated_title,
            CASE
                WHEN at.status = 'completed' THEN at.translated_content
                ELSE NULL
            END AS translated_content,
            CASE
                WHEN at.status IS NOT NULL THEN at.status
                WHEN a.source IN ({_KOREAN_SOURCES_SQL}) THEN 'not_needed'
                ELSE 'pending'
            END AS translation_status,
            {meta_fields}
        """
    return f"""
        a.id, a.url, a.source,
        a.published_at, a.crawled_at,
        a.title AS original_title,
        a.content AS original_content,
        a.title AS title,
        a.content AS content,
        NULL AS translated_title,
        NULL AS translated_content,
        CASE
            WHEN a.source IN ({_KOREAN_SOURCES_SQL}) THEN 'not_needed'
            ELSE 'pending'
        END AS translation_status,
        {meta_fields}
    """
