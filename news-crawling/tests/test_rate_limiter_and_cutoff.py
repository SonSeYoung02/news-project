from datetime import datetime, timedelta, timezone

from translation.rate_limiter import CutoffController, RateLimiter

KST = timezone(timedelta(hours=9))


def test_rate_limiter_daily_budget_and_persistence(temp_db):
    """일일 호출 한도를 소진하면 이후 요청이 차단되고 DB 영속화로 새 인스턴스에서도 유지된다."""
    limiter1 = RateLimiter(daily_limit=5, request_interval=0.01)

    for _ in range(5):
        assert limiter1.wait_and_consume(tokens=50)

    # 6번째 호출은 일일 한도 초과로 차단
    assert not limiter1.wait_and_consume(tokens=50)

    # 새 인스턴스를 생성해도 DB 영속화 덕분에 여전히 한도 초과
    limiter2 = RateLimiter(daily_limit=5, request_interval=0.01)
    assert not limiter2.wait_and_consume(tokens=50)


def test_cutoff_controller_time_boundaries():
    """새벽 마감 시각(05:55) 경계 전후에 따라 요청 허용 여부가 정확히 갈린다."""
    controller = CutoffController(cutoff_hour=5, cutoff_minute=55, deadline_hour=6, deadline_minute=0)

    # 1. 05:54:59 (마감 전 -> 허용)
    t_before = datetime(2026, 11, 12, 5, 54, 59, tzinfo=KST)
    assert controller.can_request(now_dt=t_before)

    # 2. 05:55:00 정각 (마감 도달 -> 차단)
    t_cutoff = datetime(2026, 11, 12, 5, 55, 0, tzinfo=KST)
    assert not controller.can_request(now_dt=t_cutoff)

    # 3. 05:58:30 (마감 시간대 -> 차단)
    t_mid = datetime(2026, 11, 12, 5, 58, 30, tzinfo=KST)
    assert not controller.can_request(now_dt=t_mid)

    # 4. 01:30:00 (정상 새벽 시간 -> 허용)
    t_normal = datetime(2026, 11, 12, 1, 30, 0, tzinfo=KST)
    assert controller.can_request(now_dt=t_normal)
