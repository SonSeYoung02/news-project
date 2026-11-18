"""app.briefing.service 순수 규칙(날짜 파싱·브리핑 선정·다양성·후보 압축) 단위 테스트."""

from datetime import datetime, timedelta, timezone

import pytest

from app.briefing import service

BASE_NOW = datetime(2026, 11, 10, 3, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   \t\n  ", None),
        ("not-a-date", None),
        ("2026-13-45T99:00:00Z", None),
        ("0001-01-01T00:00:00+09:00", None),
        ("9999-12-31T23:59:59-09:00", None),
        ("2026-11-10T02:00:00Z", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
        ("  2026-11-10T11:00:00+09:00  ", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
        ("2026-11-09T21:00:00-05:00", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
        # 타임존이 없는 문자열은 크롤러 로컬 시각(KST, UTC+9)으로 해석해 UTC로 변환한다.
        ("2026-11-10T11:00:00", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
        ("Tue, 10 Nov 2026 11:00:00 +0900", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
        ("Tue, 10 Nov 2026 11:00:00", datetime(2026, 11, 10, 2, 0, 0, tzinfo=timezone.utc)),
    ],
)
def test_article_time_normalizes_diverse_formats_to_utc(raw, expected):
    """날짜 파서는 ISO 8601·RFC 2822·타임존 없는 KST 문자열을 UTC로 정규화하고 오류/오버플로는 None을 반환한다."""
    assert service._article_time(raw) == expected


def test_select_briefing_ids_empty_and_under_limit():
    """후보가 비어 있으면 빈 목록을, 상한(5건) 미만이면 가능한 후보 전체를 규칙 순으로 선정한다."""
    assert service._select_briefing_ids([]) == []

    t1 = BASE_NOW - timedelta(minutes=30)
    t2 = BASE_NOW - timedelta(minutes=10)
    pool = [
        (t1, 1, "src_a", "LLM"),
        (t2, 2, "src_b", "Vision"),
    ]
    assert service._select_briefing_ids(pool) == [2, 1]


def test_select_briefing_ids_prioritizes_unseen_topic_over_unseen_source_and_recency():
    """새로운 비어있지 않은 주제(sub_category)가 미선정 출처나 더 최신 시각보다 우선한다."""
    t_latest = BASE_NOW
    t_mid = BASE_NOW - timedelta(minutes=5)
    t_older = BASE_NOW - timedelta(minutes=20)

    candidates = [
        # 1번째 선정: 가장 최신인 (1, src_a, LLM)
        (t_latest, 1, "src_a", "LLM"),
        # 2번째 경쟁: (2)는 더 최신이고 새 출처(src_b)지만 이미 선정된 주제(LLM)
        (t_mid, 2, "src_b", "LLM"),
        # (3)은 더 오래됐고 이미 선정된 출처(src_a)지만 새로운 주제(Robotics) → 2순위로 선택되어야 함
        (t_older, 3, "src_a", "Robotics"),
    ]
    snapshot = list(candidates)

    selected = service._select_briefing_ids(candidates, limit=3)
    assert selected == [1, 3, 2]
    # 호출자의 원본 리스트는 변경되지 않아야 한다.
    assert candidates == snapshot


def test_select_briefing_ids_empty_topic_does_not_receive_novelty_bonus():
    """빈 주제('')는 신규 주제 가점을 받지 못하며, 출처 다양성과 최신순으로 평가된다."""
    t1 = BASE_NOW
    t2 = BASE_NOW - timedelta(minutes=5)
    t3 = BASE_NOW - timedelta(minutes=10)

    candidates = [
        (t1, 1, "src_a", "LLM"),
        # 더 최신(t2)이고 같은 출처(src_a), 빈 주제("")
        (t2, 2, "src_a", ""),
        # 조금 오래됐지만(t3) 새로운 출처(src_b), 빈 주제("") → 출처 다양성으로 (2)보다 먼저 선정
        (t3, 3, "src_b", ""),
    ]

    assert service._select_briefing_ids(candidates, limit=3) == [1, 3, 2]


def test_select_briefing_ids_tie_breaks_by_larger_id_and_fills_up_to_limit():
    """동일 출처·동일 주제만 남아 다양성이 소진되더라도 최신순·큰 ID 순으로 최대 limit건까지 채운다."""
    same_time = BASE_NOW - timedelta(minutes=10)
    candidates = [
        (same_time, 10, "src_only", "LLM"),
        (same_time, 25, "src_only", "LLM"),
        (BASE_NOW - timedelta(minutes=1), 3, "src_only", "LLM"),
        (BASE_NOW - timedelta(minutes=2), 4, "src_only", "LLM"),
        (BASE_NOW - timedelta(minutes=3), 5, "src_only", "LLM"),
        (BASE_NOW - timedelta(minutes=4), 6, "src_only", "LLM"),
    ]

    assert service._select_briefing_ids(candidates, limit=5) == [3, 4, 5, 6, 25]


def test_compact_briefing_candidates_returns_small_pool_unchanged_and_caps_large_pool():
    """후보가 limit 이하이면 그대로 반환하고, 초과 시 중복 없이 4-버킷 상한 크기 이하로 압축해 선정 동등성을 유지한다."""
    small_pool = [(BASE_NOW - timedelta(minutes=i), i, "s", "t") for i in range(1, 6)]
    assert service._compact_briefing_candidates(small_pool, limit=5) is small_pool

    # 상위권이 전부 동일 출처·빈 주제로 채워져도 버킷 2·3·4가 후순위 다양성 후보를 보존해야 한다.
    limit = 3
    large_pool = [
        (BASE_NOW - timedelta(minutes=i), 1000 - i, "dominant_src", "")
        for i in range(10)
    ] + [
        (BASE_NOW - timedelta(minutes=20 + i), 100 + i, f"src_{i % 5}", f"topic_{i % 5}")
        for i in range(30)
    ]

    compacted = service._compact_briefing_candidates(large_pool, limit=limit)
    max_expected = 3 * limit + (2 * (limit - 1) * limit + 1)  # 3*3 + 13 = 22
    assert len(compacted) <= max_expected
    assert len({item[1] for item in compacted}) == len(compacted)
    assert service._select_briefing_ids(compacted, limit=limit) == service._select_briefing_ids(
        large_pool, limit=limit
    )


def test_compute_briefing_builds_24h_window_and_metadata(monkeypatch):
    """_compute_briefing은 정확히 24시간 윈도우와 선정 설명을 구성하고 순수 규칙 함수를 repository에 전달한다."""
    recorded = {}

    def fake_fetch(*, window_start, window_end, parse_time_fn, compact_fn, select_ids_fn):
        recorded["window_start"] = window_start
        recorded["window_end"] = window_end
        recorded["parse_time_fn"] = parse_time_fn
        recorded["compact_fn"] = compact_fn
        recorded["select_ids_fn"] = select_ids_fn
        return [{"id": 1, "title": "모의 브리핑 기사"}]

    monkeypatch.setattr(service.repository, "fetch_and_select_briefing_articles", fake_fetch)

    result = service._compute_briefing(BASE_NOW)

    assert recorded["window_start"] == BASE_NOW - timedelta(hours=24)
    assert recorded["window_end"] == BASE_NOW
    assert recorded["parse_time_fn"] is service._article_time
    assert recorded["compact_fn"] is service._compact_briefing_candidates
    assert recorded["select_ids_fn"] is service._select_briefing_ids
    assert result == {
        "generated_at": BASE_NOW.isoformat(),
        "window_start": (BASE_NOW - timedelta(hours=24)).isoformat(),
        "window_end": BASE_NOW.isoformat(),
        "selection_method": service.SELECTION_METHOD_DESCRIPTION,
        "articles": [{"id": 1, "title": "모의 브리핑 기사"}],
    }
