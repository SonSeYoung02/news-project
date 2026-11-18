import { describe, expect, it, vi } from "vitest";
import { fetchArticleById } from "../../../../src/domains/article/api/articleApi.ts";
import { HttpError } from "../../../../src/shared/api/client.ts";

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

describe("article 도메인 단건 조회 API 어댑터", () => {
  it("상세 URL 직접 진입 시 GET /api/articles/{id} 로 단건 조회하고 응답 DTO를 도메인 모델로 변환한다", async () => {
    const fetchSpy = mockFetchJsonOnce({
      id: 77,
      url: "https://example.com/articles/77",
      source: "GeekNews",
      title: "단건 조회 테스트 기사",
      tags: null,
    });
    const controller = new AbortController();

    const article = await fetchArticleById(77, controller.signal);

    expect(fetchSpy).toHaveBeenCalledWith("/api/articles/77", { signal: controller.signal });
    expect(article).toEqual({
      id: 77,
      url: "https://example.com/articles/77",
      source: "GeekNews",
      title: "단건 조회 테스트 기사",
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
    });
  });

  it("존재하지 않는 기사 단건 조회(404)는 status=404 인 HttpError를 던지고 500 오류도 상태를 보존한다", async () => {
    mockFetchJsonOnce({ detail: "Article not found" }, false, 404);
    await expect(fetchArticleById(999999)).rejects.toSatisfy(
      (err: unknown) => err instanceof HttpError && err.status === 404 && err.message === "HTTP 404",
    );

    mockFetchJsonOnce({ detail: "Server error" }, false, 500);
    await expect(fetchArticleById(1)).rejects.toSatisfy(
      (err: unknown) => err instanceof HttpError && err.status === 500 && err.message === "HTTP 500",
    );
  });
});
