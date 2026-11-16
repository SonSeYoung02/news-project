import os
from pathlib import Path

# backend/app/common/config.py 기준 프로젝트 루트의 news-crawling/news.db
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "news-crawling" / "news.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(DEFAULT_DB_PATH)))

# SQLite signed int64 및 요청 입력 보호 상한
SQLITE_MIN_INT64 = -(2**63)
SQLITE_MAX_INT64 = 2**63 - 1
MAX_PAGE = 10_000
MAX_OFFSET = 200_000
MAX_SEARCH_QUERY_LENGTH = 200
MAX_FILTER_LENGTH = 100

# /briefing 메모리 제한 스트리밍 및 TTL 캐시 설정
BRIEFING_MAX_ARTICLES = 5
BRIEFING_SCAN_BATCH_SIZE = 500
BRIEFING_COMPACT_THRESHOLD = 500
BRIEFING_CACHE_TTL_SECONDS = 30.0
BRIEFING_CACHE_MAX_ENTRIES = 16
BRIEFING_INFLIGHT_WAIT_TIMEOUT_SECONDS = 30.0

# 한국어 출처 목록 (번역이 불필요한 대상 판별에 사용)
KOREAN_SOURCES = ("네이버뉴스", "GeekNews", "naver", "geeknews")
_KOREAN_SOURCES_SQL = ", ".join(f"'{s}'" for s in KOREAN_SOURCES)
