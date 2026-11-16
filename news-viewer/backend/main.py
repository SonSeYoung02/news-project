"""FastAPI 애플리케이션 엔트리포인트 및 하위 호환 파사드 모듈."""

from pathlib import Path

from app import create_app
from app.article.repository import _escape_like_pattern
from app.article.router import get_article, get_articles
from app.article.schemas import Article, ArticleListResponse
from app.article.service import _reject_nul_byte
from app.briefing.cache import (
    _BriefingCacheEntry,
    _BriefingInFlight,
    _briefing_cache,
    _briefing_cache_lock,
    _briefing_inflight,
    _clear_briefing_cache,
    _clone_briefing_response,
    _get_db_cache_key_and_fingerprint,
    _is_cache_entry_fresh,
)
from app.briefing.router import get_briefing
from app.briefing.schemas import BriefingResponse
from app.briefing.service import (
    _article_time,
    _compact_briefing_candidates,
    _compute_briefing,
    _select_briefing_ids,
    _utc_now,
)
from app.common.config import (
    BRIEFING_CACHE_MAX_ENTRIES,
    BRIEFING_CACHE_TTL_SECONDS,
    BRIEFING_COMPACT_THRESHOLD,
    BRIEFING_INFLIGHT_WAIT_TIMEOUT_SECONDS,
    BRIEFING_MAX_ARTICLES,
    BRIEFING_SCAN_BATCH_SIZE,
    DB_PATH,
    DEFAULT_DB_PATH,
    KOREAN_SOURCES,
    MAX_FILTER_LENGTH,
    MAX_OFFSET,
    MAX_PAGE,
    MAX_SEARCH_QUERY_LENGTH,
    SQLITE_MAX_INT64,
    SQLITE_MIN_INT64,
    _KOREAN_SOURCES_SQL,
)
from app.common.database import (
    _article_select_fields,
    _connect,
    _get_active_db_path,
    _has_translations_table,
    _row_to_dict,
    compute_content_hash,
)
from app.meta.router import get_categories, get_sources
from app.meta.schemas import CategoryCount, SourceCount
from app.status.router import index

app = create_app()

__all__ = [
    "Path",
    "app",
    "create_app",
    "DEFAULT_DB_PATH",
    "DB_PATH",
    "SQLITE_MIN_INT64",
    "SQLITE_MAX_INT64",
    "MAX_PAGE",
    "MAX_OFFSET",
    "MAX_SEARCH_QUERY_LENGTH",
    "MAX_FILTER_LENGTH",
    "BRIEFING_MAX_ARTICLES",
    "BRIEFING_SCAN_BATCH_SIZE",
    "BRIEFING_COMPACT_THRESHOLD",
    "BRIEFING_CACHE_TTL_SECONDS",
    "BRIEFING_CACHE_MAX_ENTRIES",
    "BRIEFING_INFLIGHT_WAIT_TIMEOUT_SECONDS",
    "KOREAN_SOURCES",
    "_KOREAN_SOURCES_SQL",
    "Article",
    "ArticleListResponse",
    "BriefingResponse",
    "CategoryCount",
    "SourceCount",
    "compute_content_hash",
    "_utc_now",
    "_article_time",
    "_escape_like_pattern",
    "_compact_briefing_candidates",
    "_select_briefing_ids",
    "_get_active_db_path",
    "_connect",
    "_has_translations_table",
    "_row_to_dict",
    "_article_select_fields",
    "_BriefingCacheEntry",
    "_BriefingInFlight",
    "_briefing_cache_lock",
    "_briefing_cache",
    "_briefing_inflight",
    "_clear_briefing_cache",
    "_clone_briefing_response",
    "_get_db_cache_key_and_fingerprint",
    "_is_cache_entry_fresh",
    "_compute_briefing",
    "_reject_nul_byte",
    "index",
    "get_articles",
    "get_article",
    "get_briefing",
    "get_categories",
    "get_sources",
]
