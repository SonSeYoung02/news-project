import json
import os
from unittest import mock
from unittest.mock import patch

import pytest

import db


class TestGeminiClientConfig:
    def test_client_uses_v1beta(self):
        """Gemini 클라이언트는 v1beta API 버전과 설정된 타임아웃으로 생성된다."""
        import config
        import translation.translator as tr

        tr._gemini_client = None
        try:
            with patch.dict(os.environ, {"GEMINI_API_KEY": "dummy"}), patch(
                "google.genai.Client"
            ) as mock_client:
                tr.get_gemini_client()
            kwargs = mock_client.call_args.kwargs
            assert kwargs["http_options"]["api_version"] == "v1beta"
            assert kwargs["http_options"]["timeout"] == config.GEMINI_TIMEOUT_MS
            assert config.GEMINI_TIMEOUT_MS == 180000
        finally:
            tr._gemini_client = None

    def test_default_daily_limit_is_20(self):
        """환경 변수가 지정되지 않았을 때 일일 기본 한도는 20회다."""
        import config

        if "GEMINI_DAILY_LIMIT" not in os.environ:
            assert config.GEMINI_DAILY_LIMIT == 20


def _job(i, n):
    return {"article_id": i, "title": "t", "content": "a" * (n - 1), "content_hash": f"h{i}"}


class TestBatcher:
    def _ids(self, batches):
        return [[j["article_id"] for j in b] for b in batches]

    def test_groups_by_chars(self):
        """글자 수 상한(max_chars)을 넘지 않도록 기사를 묶음으로 분할한다."""
        from translation.batcher import build_batches

        batches = build_batches(
            [_job(1, 5000), _job(2, 5000), _job(3, 5000)],
            max_chars=12000,
            max_articles=10,
        )
        assert self._ids(batches) == [[1, 2], [3]]

    def test_groups_by_count(self):
        """기사 수 상한(max_articles)에 도달하면 다음 묶음으로 분리한다."""
        from translation.batcher import build_batches

        batches = build_batches(
            [_job(i, 100) for i in range(1, 13)],
            max_chars=12000,
            max_articles=10,
        )
        assert [len(b) for b in batches] == [10, 2]

    def test_oversized_article_alone_keeps_order(self):
        """단일 기사가 max_chars를 초과해도 순서를 유지한 단독 묶음으로 배치한다."""
        from translation.batcher import build_batches

        batches = build_batches(
            [_job(1, 1000), _job(2, 15000), _job(3, 1000)],
            max_chars=12000,
            max_articles=10,
        )
        assert self._ids(batches) == [[1], [2], [3]]

    def test_empty_queue(self):
        """빈 대기열을 전달하면 빈 묶음 목록을 반환한다."""
        from translation.batcher import build_batches

        assert build_batches([]) == []


def _ko(n):
    return "엔비디아가 실적을 발표했다. " * n


def _src_batch():
    return [
        {"article_id": 1, "title": "AI chips", "content": "Nvidia reports " * 30},
        {"article_id": 2, "title": "GPU news", "content": "Nvidia reports " * 30},
    ]


class _FakeApiError(Exception):
    def __init__(self, code, message, details):
        super().__init__(f"{code} {message}")
        self.code = code
        self.message = message
        self.details = details


class TestBatchParsing:
    def _raw(self, items):
        return json.dumps(items, ensure_ascii=False)

    def test_parse_valid_response(self):
        """정상 JSON 배열 응답에서 모든 유효 기사 ID를 파싱한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw([
            {"id": 1, "title": "AI 칩", "content": _ko(20)},
            {"id": 2, "title": "GPU 소식", "content": _ko(20)},
        ])
        assert set(parse_batch_response(raw, _src_batch())) == {1, 2}

    def test_parse_accepts_string_ids(self):
        """응답 ID가 문자열 숫자여도 정수 ID로 변환해 매칭한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw([{"id": "1", "title": "AI 칩", "content": _ko(20)}])
        assert set(parse_batch_response(raw, _src_batch())) == {1}

    def test_parse_strips_code_fence(self):
        """Markdown JSON 코드 펜스로 감싼 응답도 펜스를 제거하고 파싱한다."""
        from translation.batch_translator import parse_batch_response

        raw = "```json\n" + self._raw([{"id": 1, "title": "AI 칩", "content": _ko(20)}]) + "\n```"
        assert set(parse_batch_response(raw, _src_batch())) == {1}

    def test_parse_accepts_wrapped_list(self):
        """단일 키 딕셔너리 안에 목록이 감싸진 JSON 응답도 허용한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw({"articles": [{"id": 1, "title": "AI 칩", "content": _ko(20)}]})
        assert set(parse_batch_response(raw, _src_batch())) == {1}

    def test_parse_non_list_raises(self):
        """목록 형태가 아닌 JSON 객체 응답은 BatchParseError를 발생시킨다."""
        from translation.batch_translator import BatchParseError, parse_batch_response

        with pytest.raises(BatchParseError):
            parse_batch_response('{"id": 1}', _src_batch())

    def test_parse_drops_unknown_duplicate_and_non_korean(self):
        """없는 ID, 중복 ID, 한글 미포함 응답 항목은 모두 검증 단계에서 제외한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw([
            {"id": 99, "title": "없는 기사", "content": _ko(20)},
            {"id": 1, "title": "AI 칩", "content": _ko(20)},
            {"id": 1, "title": "AI 칩 2", "content": _ko(20)},
            {"id": 2, "title": "GPU news", "content": "Nvidia reports " * 30},
        ])
        assert parse_batch_response(raw, _src_batch()) == {}

    def test_parse_drops_suspected_summary(self):
        """원문 대비 지나치게 짧은 번역은 요약 의심으로 판단해 제외한다."""
        from translation.batch_translator import parse_batch_response

        batch = [{"article_id": 1, "title": "t", "content": "x" * 1000}]
        raw = self._raw([{"id": 1, "title": "요약", "content": "가" * 200}])
        assert parse_batch_response(raw, batch) == {}

    def test_validate_allows_empty_content_when_source_empty(self):
        """원문 본문이 비어 있는 기사는 번역 본문이 비어 있어도 유효한 결과로 채택한다."""
        from translation.batch_translator import parse_batch_response

        batch = [{"article_id": 1, "title": "AI chips", "content": ""}]
        raw = self._raw([{"id": 1, "title": "AI 칩", "content": ""}])
        assert parse_batch_response(raw, batch) == {1: {"title": "AI 칩", "content": ""}}

    def test_parse_drops_empty_content_when_source_nonempty(self):
        """원문 본문이 있는데 번역 본문이 비어 있으면 결과에서 제외한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw([{"id": 1, "title": "AI 칩", "content": ""}])
        assert parse_batch_response(raw, _src_batch()) == {}

    def test_parse_skips_malformed_items(self):
        """문자열이나 id 누락 객체 등 비정상 항목은 건너뛰고 정상 항목만 파싱한다."""
        from translation.batch_translator import parse_batch_response

        raw = self._raw(["문자열", {"title": "id 없음"}, {"id": 1, "title": "AI 칩", "content": _ko(20)}])
        assert set(parse_batch_response(raw, _src_batch())) == {1}

    def test_parse_broken_json_raises(self):
        """잘못된 JSON 문자열은 BatchParseError를 발생시킨다."""
        from translation.batch_translator import BatchParseError, parse_batch_response

        with pytest.raises(BatchParseError):
            parse_batch_response('[{"id": 1, "title": "AI', _src_batch())

    def test_call_gemini_batch_request_shape(self):
        """Gemini 묶음 요청 시 JSON 응답 MIME, thinking_budget=0, 직렬화된 원문 payload를 전달한다."""
        from translation import batch_translator as bt

        client = mock.MagicMock()
        client.models.generate_content.return_value.text = "[]"
        with mock.patch.object(bt.translator, "get_gemini_client", return_value=client):
            out = bt.call_gemini_batch(_src_batch())
        assert out == "[]"
        kwargs = client.models.generate_content.call_args.kwargs
        config = kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.thinking_config.thinking_budget == 0
        expected = json.dumps(
            [
                {"id": 1, "title": "AI chips", "content": "Nvidia reports " * 30},
                {"id": 2, "title": "GPU news", "content": "Nvidia reports " * 30},
            ],
            ensure_ascii=False,
        )
        assert expected in kwargs["contents"]

    def test_call_gemini_batch_classifies_errors(self):
        """400 응답 오류 발생 시 PermanentApiError로 분류해 예외를 던진다."""
        from translation import batch_translator as bt

        client = mock.MagicMock()
        client.models.generate_content.side_effect = _FakeApiError(400, "bad", {})
        with mock.patch.object(bt.translator, "get_gemini_client", return_value=client):
            with pytest.raises(bt.PermanentApiError):
                bt.call_gemini_batch(_src_batch())


class TestErrorClassification:
    def test_classify_daily_quota(self):
        """일일 무료 한도(RequestsPerDay) 429 오류는 DailyQuotaExceeded로 분류한다."""
        from translation.batch_translator import DailyQuotaExceeded, classify_api_error

        details = {
            "error": {
                "code": 429,
                "details": [
                    {"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "70490s"},
                ],
            }
        }
        assert isinstance(
            classify_api_error(_FakeApiError(429, "Quota exceeded", details)),
            DailyQuotaExceeded,
        )
        e2 = _FakeApiError(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier", None)
        assert isinstance(classify_api_error(e2), DailyQuotaExceeded)

    def test_classify_minute_limit(self):
        """분당 한도 429 오류는 RetryInfo 대기 초를 포함한 MinuteRateLimited로 분류한다."""
        from translation.batch_translator import MinuteRateLimited, classify_api_error

        details = {
            "error": {
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}
                ]
            }
        }
        r = classify_api_error(_FakeApiError(429, "slow down", details))
        assert isinstance(r, MinuteRateLimited)
        assert r.retry_seconds == 37

    def test_classify_minute_limit_fractional_and_default(self):
        """소수점 retryDelay를 파싱하고 지연 정보가 없으면 기본 60초를 사용한다."""
        from translation.batch_translator import classify_api_error

        details = {"error": {"details": [{"retryDelay": "37.5s"}]}}
        assert classify_api_error(_FakeApiError(429, "x", details)).retry_seconds == 37.5
        assert classify_api_error(_FakeApiError(429, "x", None)).retry_seconds == 60

    def test_classify_bad_request(self):
        """400·403·404 클라이언트 오류는 모두 PermanentApiError로 분류한다."""
        from translation.batch_translator import PermanentApiError, classify_api_error

        for code in (400, 403, 404):
            assert isinstance(
                classify_api_error(_FakeApiError(code, "bad", {})),
                PermanentApiError,
            )

    def test_classify_server_and_network_errors(self):
        """503 서버 오류와 네트워크 예외는 10초 대기 후 재시도하는 MinuteRateLimited로 분류한다."""
        from translation.batch_translator import MinuteRateLimited, classify_api_error

        r = classify_api_error(_FakeApiError(503, "unavailable", {}))
        assert isinstance(r, MinuteRateLimited)
        assert r.retry_seconds == 10
        r = classify_api_error(ConnectionError("net"))
        assert isinstance(r, MinuteRateLimited)
        assert r.retry_seconds == 10


class TestBatchReviewFixes:
    def test_missing_api_key_is_permanent_error(self):
        """API 키 누락 ValueError는 재시도 대상이 아닌 PermanentApiError로 변환한다."""
        from translation import batch_translator as bt

        with mock.patch.object(bt.translator, "get_gemini_client", side_effect=ValueError("no key")):
            with pytest.raises(bt.PermanentApiError):
                bt.call_gemini_batch(_src_batch())

    def test_parse_coerces_content_to_str(self):
        """응답의 title·content가 문자열이 아니어도 문자열로 변환해 저장한다."""
        from translation.batch_translator import parse_batch_response

        batch = [{"article_id": 1, "title": "t", "content": ""}]
        raw = json.dumps([{"id": 1, "title": "제목", "content": ["가", "나"]}], ensure_ascii=False)
        result = parse_batch_response(raw, batch)
        assert 1 in result
        assert isinstance(result[1]["content"], str)
        assert isinstance(result[1]["title"], str)


class _CountingRateLimiter:
    def __init__(self, allowed=None):
        self.allowed = allowed
        self.calls = 0

    def wait_and_consume(self, tokens=0, requests=1):
        if self.allowed is not None and self.calls >= self.allowed:
            return False
        self.calls += 1
        return True


def _tjob(i):
    return {"article_id": i, "title": f"t{i}", "content": "Nvidia reports " * 30, "content_hash": f"h{i}"}


def _ok_raw(ids):
    return json.dumps(
        [{"id": i, "title": f"제목{i}", "content": _ko(20)} for i in ids],
        ensure_ascii=False,
    )


@pytest.mark.usefixtures("temp_db")
class TestTranslateBatch:
    def _row(self, i):
        return db.get_or_create_translation(i, f"h{i}")

    def _run(self, batch, side_effect, limiter=None, **kw):
        from translation import batch_translator as bt

        limiter = limiter or _CountingRateLimiter()
        with mock.patch(
            "translation.batch_translator.call_gemini_batch", side_effect=side_effect
        ) as m, mock.patch("translation.batch_translator.time.sleep") as sl:
            out = bt.translate_batch(batch, limiter, **kw)
        return out, m, sl

    def test_success_saves_completed(self):
        """묶음 번역이 모두 성공하면 DB 상태가 completed와 모델명으로 저장된다."""
        out, m, _ = self._run([_tjob(1), _tjob(2)], [_ok_raw([1, 2])], model="m-x")
        assert sorted(out.completed_ids) == [1, 2]
        assert out.stop_reason is None
        r = self._row(1)
        assert r["status"] == "completed"
        assert r["model"] == "m-x"

    def test_missing_item_stays_pending(self):
        """응답에서 누락된 기사는 실패 처리하지 않고 attempts=0인 pending 상태로 유지한다."""
        out, _, _ = self._run([_tjob(1), _tjob(2)], [_ok_raw([1])])
        assert out.completed_ids == [1]
        assert out.pending_ids == [2]
        r = self._row(2)
        assert r["status"] == "pending"
        assert r["attempts"] == 0

    def test_daily_quota_stops_without_failing(self):
        """일일 한도 초과 시 stop_reason=daily_quota로 중단하고 기사는 보류한다."""
        from translation.batch_translator import DailyQuotaExceeded

        out, _, _ = self._run([_tjob(1), _tjob(2)], DailyQuotaExceeded("x"))
        assert out.stop_reason == "daily_quota"
        assert out.failed_ids == []
        assert sorted(out.pending_ids) == [1, 2]
        assert self._row(1)["attempts"] == 0

    def test_minute_limit_waits_and_retries_once(self):
        """분당 한도 오류 시 지정 시간 대기 후 1회 재시도해 번역을 완료한다."""
        from translation.batch_translator import MinuteRateLimited

        limiter = _CountingRateLimiter()
        out, m, sl = self._run(
            [_tjob(1), _tjob(2)],
            [MinuteRateLimited("x", 5), _ok_raw([1, 2])],
            limiter,
        )
        sl.assert_called_once_with(5)
        assert sorted(out.completed_ids) == [1, 2]
        assert limiter.calls == 2

    def test_minute_limit_sleep_capped(self):
        """분당 한도 대기 시간이 60초를 넘으면 최대 60초까지만 대기한다."""
        from translation.batch_translator import MinuteRateLimited

        out, _, sl = self._run(
            [_tjob(1), _tjob(2)],
            [MinuteRateLimited("x", 120), _ok_raw([1, 2])],
        )
        sl.assert_called_once_with(60)

    def test_minute_limit_twice_leaves_pending(self):
        """재시도 후에도 분당 한도 오류가 반복되면 실패 없이 보류 처리한다."""
        from translation.batch_translator import MinuteRateLimited

        out, m, _ = self._run(
            [_tjob(1), _tjob(2)],
            [MinuteRateLimited("x", 1), MinuteRateLimited("x", 1)],
        )
        assert m.call_count == 2
        assert sorted(out.pending_ids) == [1, 2]
        assert out.stop_reason is None
        assert out.failed_ids == []

    def test_parse_error_splits_in_half(self):
        """응답 파싱 실패 시 묶음을 절반으로 나누어 재시도해 모두 완료한다."""
        from translation.batch_translator import BatchParseError

        batch = [_tjob(i) for i in range(1, 5)]
        out, m, _ = self._run(
            batch, [BatchParseError("x"), _ok_raw([1, 2]), _ok_raw([3, 4])]
        )
        assert m.call_count == 3
        assert sorted(out.completed_ids) == [1, 2, 3, 4]

    def test_split_retry_stops_when_quota_exhausted(self):
        """파싱 실패 후 분할 재시도 중 요청 한도가 소진되면 즉시 중단하고 보류한다."""
        from translation.batch_translator import BatchParseError

        batch = [_tjob(i) for i in range(1, 5)]
        out, m, _ = self._run(
            batch, [BatchParseError("x")], _CountingRateLimiter(allowed=1)
        )
        assert out.stop_reason == "daily_quota"
        assert sorted(out.pending_ids) == [1, 2, 3, 4]
        assert out.failed_ids == []

    def test_split_second_half_skipped_after_daily_quota(self):
        """분할 재시도의 전반부에서 일일 한도가 소진되면 후반부는 호출하지 않고 보류한다."""
        from translation.batch_translator import BatchParseError, DailyQuotaExceeded

        batch = [_tjob(i) for i in range(1, 5)]
        out, m, _ = self._run(batch, [BatchParseError("x"), DailyQuotaExceeded("x")])
        assert m.call_count == 2
        assert out.stop_reason == "daily_quota"
        assert sorted(out.pending_ids) == [1, 2, 3, 4]

    def test_single_item_parse_error_stays_pending(self):
        """단건 묶음에서 파싱 오류가 발생하면 더 분할하지 않고 보류한다."""
        from translation.batch_translator import BatchParseError

        out, m, _ = self._run([_tjob(1)], [BatchParseError("x")])
        assert m.call_count == 1
        assert out.pending_ids == [1]

    def test_permanent_error_marks_failed(self):
        """영구 API 오류 발생 시 시도 횟수와 오류 메시지를 기록하고 failed로 분류한다."""
        from translation.batch_translator import PermanentApiError

        out, _, _ = self._run([_tjob(1), _tjob(2)], PermanentApiError("bad"))
        assert out.failed_ids == [1, 2]
        assert out.stop_reason == "permanent_error"
        r = self._row(1)
        assert r["attempts"] == 1
        assert "묶음 번역 실패" in r["last_error"]

    def test_quota_checked_before_each_call(self):
        """호출 전 일일 한도가 이미 소진되어 있으면 API 호출 없이 보류한다."""
        out, m, _ = self._run(
            [_tjob(1), _tjob(2)],
            [_ok_raw([1, 2])],
            _CountingRateLimiter(allowed=0),
        )
        m.assert_not_called()
        assert out.stop_reason == "daily_quota"
        assert sorted(out.pending_ids) == [1, 2]

    def test_already_completed_skipped(self):
        """이미 번역 완료된 기사는 Gemini 호출 대상에서 제외하고 완료 목록에 포함한다."""
        db.get_or_create_translation(1, "h1")
        db.complete_article_translation(1, "h1", "제목", "본문", "m")
        out, m, _ = self._run([_tjob(1), _tjob(2)], [_ok_raw([2])])
        assert sorted(out.completed_ids) == [1, 2]
        assert len(m.call_args.args[0]) == 1
        assert m.call_args.args[0][0]["article_id"] == 2
