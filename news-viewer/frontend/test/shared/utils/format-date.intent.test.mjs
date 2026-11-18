import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { formatDate } from "../../../src/shared/utils/formatDate.ts";

describe("날짜 포맷 유틸리티 의도", () => {
  test("유효한 날짜 문자열을 한국어(ko-KR) 날짜 형식으로 변환한다", () => {
    const input = "2026-05-14T12:00:00Z";
    const expected = new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(new Date(input));

    assert.equal(formatDate(input), expected);
    assert.match(formatDate(input), /2026년\s*5월\s*14일/);
  });

  test("날짜로 해석할 수 없는 잘못된 문자열은 앞 10자만 반환한다", () => {
    assert.equal(formatDate("2026-99-99 invalid"), "2026-99-99");
    assert.equal(formatDate("invalid-date-string"), "invalid-da");
    assert.equal(formatDate("not-a-date"), "not-a-date");
  });

  test("빈 문자열이나 null, undefined 입력은 빈 문자열을 반환한다", () => {
    assert.equal(formatDate(""), "");
    assert.equal(formatDate(null), "");
    assert.equal(formatDate(undefined), "");
  });
});
