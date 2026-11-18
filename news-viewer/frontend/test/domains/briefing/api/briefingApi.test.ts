import { describe, expect, it, vi } from "vitest";
import { fetchBriefing, toBriefing } from "../../../../src/domains/briefing/api/briefingApi.ts";

function mockFetchJsonOnce(payload: unknown, ok = true, status = 200) {
  if (!globalThis.fetch) {
    globalThis.fetch = (() => Promise.reject(new Error("fetch is not implemented"))) as typeof fetch;
  }
  return vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
    ok,
    status,
    json: async () => payload,
  } as Response);
}

describe("briefing 도메인 API 어댑터", () => {
  it("브리핑 조회 응답 DTO를 브리핑 도메인 모델로 변환하고 기사 배열이 누락되어도 빈 배열로 안전하게 정규화한다", async () => {
    const fetchSpy = mockFetchJsonOnce({
      generated_at: "2026-11-18T09:00:00Z",
      window_start: "2026-11-17T09:00:00Z",
      window_end: "2026-11-18T09:00:00Z",
      selection_method: "hybrid",
      articles: [
        {
          id: 101,
          url: "https://example.com/101",
          source: "GeekNews",
          title: "브리핑 기사",
          tags: undefined,
        },
      ],
    });
    const controller = new AbortController();

    const briefing = await fetchBriefing(controller.signal);

    expect(fetchSpy).toHaveBeenCalledWith("/api/briefing", { signal: controller.signal });
    expect(briefing.generated_at).toBe("2026-11-18T09:00:00Z");
    expect(briefing.articles).toHaveLength(1);
    expect(briefing.articles[0]).toMatchObject({
      id: 101,
      title: "브리핑 기사",
      summary: null,
      tags: [],
    });

    const withoutArticles = toBriefing({
      generated_at: "2026-11-18T09:00:00Z",
      window_start: "2026-11-17T09:00:00Z",
      window_end: "2026-11-18T09:00:00Z",
      selection_method: "hybrid",
      articles: null,
    });
    expect(withoutArticles.articles).toEqual([]);
  });

  it("브리핑 조회 시 서버가 비정상 HTTP 상태 코드를 반환하면 오류를 던진다", async () => {
    mockFetchJsonOnce({ detail: "unavailable" }, false, 503);
    await expect(fetchBriefing()).rejects.toThrow("HTTP 503");
  });
});
