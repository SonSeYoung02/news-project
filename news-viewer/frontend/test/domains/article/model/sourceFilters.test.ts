import { describe, expect, it } from "vitest";
import { SOURCE_FILTERS, buildSourceItems } from "../../../../src/domains/article/model/sourceFilters.ts";

describe("출처 필터 도메인 규칙", () => {
  it("전체 항목을 맨 앞에 두고 7개 고정 출처 순서대로 개수를 매핑하며 응답에 없는 출처는 0으로 채운다", () => {
    const items = buildSourceItems(
      [
        { source: "arXiv", count: 5 },
        { source: "네이버뉴스", count: 12 },
        { source: "GeekNews", count: 8 },
        { source: "등록되지않은출처", count: 99 },
      ],
      100,
    );

    expect(items).toEqual([
      { source: "", count: 100 },
      { source: "네이버뉴스", count: 12 },
      { source: "Google News", count: 0 },
      { source: "GeekNews", count: 8 },
      { source: "GitHub Trending", count: 0 },
      { source: "Hugging Face", count: 0 },
      { source: "arXiv", count: 5 },
      { source: "dev.to", count: 0 },
    ]);
    expect(items.slice(1).map((item) => item.source)).toEqual(SOURCE_FILTERS);
  });

  it("출처별 개수 응답이 비어 있어도 전체 항목과 7개 고정 출처를 0건으로 초기화해 반환한다", () => {
    const items = buildSourceItems([], 0);

    expect(items).toHaveLength(8);
    expect(items).toHaveLength(1 + SOURCE_FILTERS.length);
    expect(items[0]).toEqual({ source: "", count: 0 });
    expect(items.slice(1).every((item) => item.count === 0)).toBe(true);
  });

  it("응답에 Reddit AI가 포함되어도 고정 출처 목록에 없으므로 반환 항목에서 제외한다", () => {
    const items = buildSourceItems(
      [
        { source: "Reddit AI", count: 2 },
        { source: "GeekNews", count: 4 },
      ],
      6,
    );

    expect(SOURCE_FILTERS).not.toContain("Reddit AI");
    expect(items.some((item) => item.source === "Reddit AI")).toBe(false);
  });
});
