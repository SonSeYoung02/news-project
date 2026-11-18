import { describe, expect, it, vi } from "vitest";
import {
  fetchArticleList,
  fetchSourceCounts,
  fetchTotalArticleCount,
  toArticle,
} from "../../../../src/domains/article/api/articleApi.ts";

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

describe("article 도메인 API 어댑터", () => {
  it("기사 목록 조회 시 페이지·출처·검색어 쿼리 파라미터를 전달하고 응답 DTO를 도메인 모델로 변환한다", async () => {
    const fetchSpy = mockFetchJsonOnce({
      total: 42,
      page: 2,
      size: 20,
      articles: [
        {
          id: 7,
          url: "https://example.com/articles/7",
          source: "GeekNews",
          title: "AI 에이전트 테스트",
          tags: null,
        },
      ],
    });
    const controller = new AbortController();

    const result = await fetchArticleList(
      { page: 2, size: 20, source: "GeekNews", q: "AI 에이전트" },
      controller.signal,
    );

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/articles?page=2&size=20&source=GeekNews&q=AI+%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8",
      { signal: controller.signal },
    );
    expect(result).toEqual({
      total: 42,
      page: 2,
      size: 20,
      articles: [
        {
          id: 7,
          url: "https://example.com/articles/7",
          source: "GeekNews",
          title: "AI 에이전트 테스트",
          content: null,
          published_at: null,
          crawled_at: null,
          summary: null,
          major_category: null,
          sub_category: null,
          tags: [],
          original_title: null,
          original_content: null,
          translated_title: null,
          translated_content: null,
          translation_status: null,
        },
      ],
    });

    const emptyFilterSpy = mockFetchJsonOnce({
      total: 0,
      page: 1,
      size: 20,
      articles: null,
    });
    const emptyResult = await fetchArticleList({ page: 1, size: 20 });
    expect(emptyFilterSpy).toHaveBeenCalledWith("/api/articles?page=1&size=20", { signal: undefined });
    expect(emptyResult.articles).toEqual([]);
  });

  it("출처 목록과 전체 기사 수 조회 시 각 엔드포인트 응답을 도메인 값으로 변환한다", async () => {
    const sourcesSpy = mockFetchJsonOnce([
      { source: "GeekNews", count: 8 },
      { source: "arXiv", count: 5 },
    ]);
    const sources = await fetchSourceCounts();
    expect(sourcesSpy).toHaveBeenCalledWith("/api/sources", { signal: undefined });
    expect(sources).toEqual([
      { source: "GeekNews", count: 8 },
      { source: "arXiv", count: 5 },
    ]);

    const totalSpy = mockFetchJsonOnce({ total: 123, page: 1, size: 1, articles: [] });
    const total = await fetchTotalArticleCount();
    expect(totalSpy).toHaveBeenCalledWith("/api/articles?page=1&size=1", { signal: undefined });
    expect(total).toBe(123);

    const normalized = toArticle({
      id: 9,
      url: "https://example.com/9",
      source: "arXiv",
      title: "최소 DTO",
    });
    expect(normalized.tags).toEqual([]);
    expect(normalized.summary).toBeNull();
  });

  it("서버가 비정상 HTTP 상태 코드를 반환하면 오류를 던진다", async () => {
    mockFetchJsonOnce({ detail: "server error" }, false, 500);
    await expect(fetchArticleList({ page: 1, size: 20 })).rejects.toThrow("HTTP 500");

    mockFetchJsonOnce({ detail: "not found" }, false, 404);
    await expect(fetchSourceCounts()).rejects.toThrow("HTTP 404");

    mockFetchJsonOnce({ detail: "bad gateway" }, false, 502);
    await expect(fetchTotalArticleCount()).rejects.toThrow("HTTP 502");
  });
});
