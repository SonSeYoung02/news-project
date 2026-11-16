from dataclasses import dataclass
import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "news-crawling" / "news.db"
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

app = FastAPI(
    title="News Viewer API",
    description="뉴스 크롤링 데이터를 조회하는 REST API. 기사 목록·상세·카테고리·출처·오늘의 AI 브리핑 엔드포인트를 제공합니다.",
    version="1.0.0",
)


def compute_content_hash(title: str, content: str) -> str:
    """원문 제목과 본문의 해시를 생성하여 원문 변경 여부를 판별한다."""
    normalized = f"{(title or '').strip()}\n{(content or '').strip()}".encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class Article(BaseModel):
    id: int
    url: str
    source: str
    title: str
    content: Optional[str] = None
    published_at: Optional[str] = None
    crawled_at: Optional[str] = None
    summary: Optional[str] = None
    major_category: Optional[str] = None
    sub_category: Optional[str] = None
    tags: list[str] = []
    original_title: Optional[str] = None
    original_content: Optional[str] = None
    translated_title: Optional[str] = None
    translated_content: Optional[str] = None
    translation_status: Optional[str] = "pending"


class ArticleListResponse(BaseModel):
    total: int
    page: int
    size: int
    articles: list[Article]


class BriefingResponse(BaseModel):
    generated_at: str
    window_start: str
    window_end: str
    selection_method: str
    articles: list[Article]


class CategoryCount(BaseModel):
    major_category: str
    count: int


class SourceCount(BaseModel):
    source: str
    count: int

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>뉴스 뷰어 백엔드</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }
    .card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 48px 56px;
      text-align: center;
      max-width: 480px;
      width: 90%;
      box-shadow: 0 25px 50px rgba(0,0,0,0.4);
    }
    .dot {
      width: 14px; height: 14px;
      background: #22c55e;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
      50% { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
    }
    .status {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      color: #22c55e;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 24px;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #f1f5f9;
    }
    p {
      color: #94a3b8;
      font-size: 15px;
      margin-bottom: 32px;
    }
    .links {
      display: flex;
      gap: 12px;
      justify-content: center;
      flex-wrap: wrap;
    }
    a {
      display: inline-block;
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      text-decoration: none;
      transition: background 0.2s;
    }
    .btn-primary {
      background: #3b82f6;
      color: #fff;
    }
    .btn-primary:hover { background: #2563eb; }
    .btn-secondary {
      background: #334155;
      color: #cbd5e1;
    }
    .btn-secondary:hover { background: #475569; }
    .info {
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid #334155;
      font-size: 13px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="status"><span class="dot"></span>백엔드 실행중</div>
    <h1>뉴스 뷰어 API</h1>
    <p>FastAPI 서버가 정상적으로 동작하고 있습니다.</p>
    <div class="links">
      <a href="/docs" class="btn-primary">Swagger 문서</a>
      <a href="/redoc" class="btn-secondary">ReDoc 문서</a>
      <a href="/articles" class="btn-secondary">기사 목록 API</a>
    </div>
    <div class="info">http://localhost:8000</div>
  </div>
</body>
</html>
"""


def _get_active_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(DB_PATH)))


@contextmanager
def _connect():
    conn = sqlite3.connect(_get_active_db_path())
    conn.row_factory = sqlite3.Row
    conn.create_function("compute_content_hash", 2, compute_content_hash)
    try:
        yield conn
    finally:
        conn.close()


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
            d["tags"] = json.loads(tags)
        except Exception:
            d["tags"] = []
    elif tags is None:
        d["tags"] = []
    return d


def _reject_nul_byte(value: Optional[str], field_name: str) -> None:
    if value is not None and "\x00" in value:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} contains an invalid NUL character",
        )


def _escape_like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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


@app.get(
    "/articles",
    response_model=ArticleListResponse,
    summary="기사 목록 조회",
    description="크롤링된 뉴스 기사 목록을 페이지네이션으로 반환합니다. 카테고리·출처·키워드로 필터링할 수 있습니다. 번역 완료 기사는 한국어 번역문을 우선 제공합니다.",
    tags=["articles"],
)
def get_articles(
    page: int = Query(1, ge=1, le=MAX_PAGE, description=f"페이지 번호 (1~{MAX_PAGE})"),
    size: int = Query(20, ge=1, le=100, description="페이지당 기사 수 (최대 100)"),
    category: Optional[str] = Query(
        None, max_length=MAX_FILTER_LENGTH, description="대분류 필터 (예: IT/과학, 경제)"
    ),
    source: Optional[str] = Query(
        None, max_length=MAX_FILTER_LENGTH, description="출처 필터 (예: devto, google_news)"
    ),
    q: Optional[str] = Query(
        None, max_length=MAX_SEARCH_QUERY_LENGTH, description="원문/번역 제목, 본문 또는 요약 검색어"
    ),
):
    _reject_nul_byte(category, "category")
    _reject_nul_byte(source, "source")
    _reject_nul_byte(q, "q")

    if page < 1 or page > MAX_PAGE:
        raise HTTPException(
            status_code=422,
            detail=f"page must be between 1 and {MAX_PAGE}",
        )
    if size < 1 or size > 100:
        raise HTTPException(
            status_code=422,
            detail="size must be between 1 and 100",
        )

    offset = (page - 1) * size
    if offset > MAX_OFFSET:
        raise HTTPException(
            status_code=422,
            detail=f"Calculated offset exceeds maximum allowed ({MAX_OFFSET})",
        )

    with _connect() as conn:
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
            ORDER BY a.crawled_at DESC LIMIT ? OFFSET ?
            """,
            params + [size, offset],
        ).fetchall()

    return {
        "total": total,
        "page": page,
        "size": size,
        "articles": [_row_to_dict(r) for r in rows],
    }


@app.get(
    "/articles/{article_id}",
    response_model=Article,
    summary="기사 상세 조회",
    description="article_id로 단일 기사의 전체 정보를 반환합니다. 번역 완료 기사는 한국어 번역문을 우선 제공하며, 미번역 시 원문을 반환합니다. 존재하지 않으면 404를 반환합니다.",
    tags=["articles"],
)
def get_article(
    article_id: int = ApiPath(
        ...,
        ge=SQLITE_MIN_INT64,
        le=SQLITE_MAX_INT64,
        description="조회할 기사 ID (SQLite 64비트 정수 범위)",
    ),
):
    with _connect() as conn:
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
        raise HTTPException(status_code=404, detail="Article not found")
    return _row_to_dict(row)


@app.get(
    "/categories",
    response_model=list[CategoryCount],
    summary="카테고리 목록 조회",
    description="기사에 사용된 대분류 카테고리와 각 카테고리의 기사 수를 반환합니다.",
    tags=["meta"],
)
def get_categories():
    with _connect() as conn:
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


@app.get(
    "/sources",
    response_model=list[SourceCount],
    summary="출처 목록 조회",
    description="크롤링에 사용된 뉴스 출처와 각 출처의 기사 수를 반환합니다.",
    tags=["meta"],
)
def get_sources():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) as count FROM articles GROUP BY source ORDER BY count DESC"
        ).fetchall()
    return [dict(r) for r in rows]


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


@dataclass
class _BriefingCacheEntry:
    fingerprint: tuple
    computed_utc: datetime
    computed_monotonic: float
    response: dict


@dataclass
class _BriefingInFlight:
    event: threading.Event
    computed_utc: datetime
    result: Optional[dict] = None
    error: Optional[BaseException] = None


_briefing_cache_lock = threading.Lock()
_briefing_cache: dict[str, _BriefingCacheEntry] = {}
_briefing_inflight: dict[tuple[str, tuple], _BriefingInFlight] = {}


def _clear_briefing_cache() -> None:
    """테스트 등에서 브리핑 캐시를 초기화한다."""
    with _briefing_cache_lock:
        _briefing_cache.clear()


def _clone_briefing_response(payload: dict) -> dict:
    return {
        **payload,
        "articles": [
            {
                **article,
                "tags": list(article.get("tags") or []),
            }
            for article in payload["articles"]
        ],
    }


def _get_db_cache_key_and_fingerprint() -> tuple[str, Optional[tuple]]:
    db_path = _get_active_db_path()
    raw = str(db_path)
    if raw == ":memory:" or raw.startswith("file:"):
        return raw, None
    try:
        resolved = db_path.resolve()
        st = resolved.stat()
    except OSError:
        return raw, None

    # SQLite 파일 헤더 오프셋 24~27의 file change counter로 커밋 변경을 감지한다.
    change_counter: Optional[bytes] = None
    try:
        with resolved.open("rb") as fh:
            fh.seek(24)
            data = fh.read(4)
            if len(data) == 4:
                change_counter = data
    except OSError:
        pass

    # WAL 모드에서는 체크포인트 전까지 -wal 파일에만 기록되므로 함께 확인한다.
    wal_sig: Optional[tuple] = None
    wal_path = Path(f"{resolved}-wal")
    try:
        wst = wal_path.stat()
        with wal_path.open("rb") as wfh:
            wal_header = wfh.read(32)
        wal_sig = (wst.st_mtime_ns, wst.st_size, wal_header)
    except OSError:
        pass

    fingerprint = (st.st_ino, st.st_mtime_ns, st.st_size, change_counter, wal_sig)
    return str(resolved), fingerprint


def _compact_briefing_candidates(
    candidates: list[tuple[datetime, int, str, str]],
    limit: int = BRIEFING_MAX_ARTICLES,
) -> list[tuple[datetime, int, str, str]]:
    """선정 우선순위 4개 버킷을 보존하며 후보 풀을 상수 크기로 압축한다."""
    if len(candidates) <= limit:
        return candidates

    ordered = sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)
    kept: list[tuple[datetime, int, str, str]] = []
    kept_ids: set[int] = set()

    def admit(item: tuple[datetime, int, str, str]) -> None:
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
    candidates: list[tuple[datetime, int, str, str]],
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
    pool: list[tuple[datetime, int, str, str]] = []

    with _connect() as conn:
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
                    published = _article_time(row["published_at"]) or _article_time(row["crawled_at"])
                    if published is None or not (start <= published <= now):
                        continue
                    topic = (row["sub_category"] or "").strip()
                    pool.append((published, row["id"], row["source"], topic))
                if len(pool) >= BRIEFING_COMPACT_THRESHOLD:
                    pool = _compact_briefing_candidates(pool)
        finally:
            cursor.close()

        selected_ids = _select_briefing_ids(pool)
        if not selected_ids:
            selected = []
        else:
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
            by_id = {row["id"]: _row_to_dict(row) for row in rows}
            selected = [by_id[aid] for aid in selected_ids if aid in by_id]

    return {
        "generated_at": now.isoformat(),
        "window_start": start.isoformat(),
        "window_end": now.isoformat(),
        "selection_method": "주제·출처 다양성, 최신순을 반영한 규칙 기반 선정",
        "articles": selected,
    }


def _is_cache_entry_fresh(
    entry: _BriefingCacheEntry,
    fingerprint: tuple,
    now: datetime,
    monotonic_now: float,
) -> bool:
    if entry.fingerprint != fingerprint:
        return False
    monotonic_elapsed = monotonic_now - entry.computed_monotonic
    utc_elapsed = (now - entry.computed_utc).total_seconds()
    return (
        -1.0 <= monotonic_elapsed < BRIEFING_CACHE_TTL_SECONDS
        and -1.0 <= utc_elapsed < BRIEFING_CACHE_TTL_SECONDS
    )


@app.get(
    "/briefing",
    response_model=BriefingResponse,
    summary="오늘의 AI 브리핑",
    description="최근 24시간 동안 수집/발행된 AI 기사 중 주제 및 출처 다양성을 고려한 핵심 브리핑 목록을 반환합니다. 번역 완료 기사는 한국어 번역문을 우선 제공합니다.",
    tags=["articles"],
)
def get_briefing():
    now = _utc_now()
    monotonic_now = time.monotonic()
    db_key, fingerprint = _get_db_cache_key_and_fingerprint()
    if fingerprint is None:
        return _compute_briefing(now)

    inflight_key = (db_key, fingerprint)
    leader = False
    flight: Optional[_BriefingInFlight] = None

    with _briefing_cache_lock:
        entry = _briefing_cache.get(db_key)
        if entry is not None and _is_cache_entry_fresh(entry, fingerprint, now, monotonic_now):
            # LRU 순서 갱신
            _briefing_cache[db_key] = _briefing_cache.pop(db_key)
            return _clone_briefing_response(entry.response)

        flight = _briefing_inflight.get(inflight_key)
        if flight is None:
            flight = _BriefingInFlight(event=threading.Event(), computed_utc=now)
            _briefing_inflight[inflight_key] = flight
            leader = True

    if not leader:
        finished = flight.event.wait(timeout=BRIEFING_INFLIGHT_WAIT_TIMEOUT_SECONDS)
        if finished:
            if flight.error is not None:
                raise flight.error
            if (
                flight.result is not None
                and abs((now - flight.computed_utc).total_seconds()) < BRIEFING_CACHE_TTL_SECONDS
            ):
                return _clone_briefing_response(flight.result)
        return _compute_briefing(now)

    try:
        result = _compute_briefing(now)
    except BaseException as exc:
        with _briefing_cache_lock:
            flight.error = exc
            if _briefing_inflight.get(inflight_key) is flight:
                _briefing_inflight.pop(inflight_key, None)
            flight.event.set()
        raise

    finished_monotonic = time.monotonic()
    _, current_fp = _get_db_cache_key_and_fingerprint()
    with _briefing_cache_lock:
        if current_fp == fingerprint:
            _briefing_cache.pop(db_key, None)
            while len(_briefing_cache) >= BRIEFING_CACHE_MAX_ENTRIES:
                oldest_key = next(iter(_briefing_cache))
                _briefing_cache.pop(oldest_key, None)
            _briefing_cache[db_key] = _BriefingCacheEntry(
                fingerprint=fingerprint,
                computed_utc=now,
                computed_monotonic=finished_monotonic,
                response=result,
            )
        flight.result = result
        if _briefing_inflight.get(inflight_key) is flight:
            _briefing_inflight.pop(inflight_key, None)
        flight.event.set()

    return _clone_briefing_response(result)
