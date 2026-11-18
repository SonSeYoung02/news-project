import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from app.common.config import (
    BRIEFING_CACHE_MAX_ENTRIES,
    BRIEFING_CACHE_TTL_SECONDS,
    BRIEFING_INFLIGHT_WAIT_TIMEOUT_SECONDS,
)
from app.common.database import _get_active_db_path
from app.common.runtime import resolve_main_attr

# 브리핑 후보 튜플 타입: (발행/수집 시각, 기사 ID, 출처, 소분류 토픽)
BriefingCandidateTuple = tuple[datetime, int, str, str]


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


def _is_cache_entry_fresh(
    entry: _BriefingCacheEntry,
    fingerprint: tuple,
    now: datetime,
    monotonic_now: float,
) -> bool:
    if entry.fingerprint != fingerprint:
        return False
    ttl = resolve_main_attr("BRIEFING_CACHE_TTL_SECONDS", BRIEFING_CACHE_TTL_SECONDS)
    monotonic_elapsed = monotonic_now - entry.computed_monotonic
    utc_elapsed = (now - entry.computed_utc).total_seconds()
    return -1.0 <= monotonic_elapsed < ttl and -1.0 <= utc_elapsed < ttl


def get_or_compute_briefing(now: datetime, compute_fn: Callable[[datetime], dict]) -> dict:
    monotonic_now = time.monotonic()
    db_key, fingerprint = _get_db_cache_key_and_fingerprint()
    if fingerprint is None:
        return compute_fn(now)

    inflight_key = (db_key, fingerprint)
    leader = False
    flight: Optional[_BriefingInFlight] = None
    ttl = resolve_main_attr("BRIEFING_CACHE_TTL_SECONDS", BRIEFING_CACHE_TTL_SECONDS)

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
            if flight.result is not None and abs((now - flight.computed_utc).total_seconds()) < ttl:
                return _clone_briefing_response(flight.result)
        return compute_fn(now)

    try:
        result = compute_fn(now)
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
