import type { SourceCount, SourceItem } from "./article.ts";

export const SOURCE_FILTERS = [
  "네이버뉴스",
  "Google News",
  "GeekNews",
  "Reddit AI",
  "GitHub Trending",
  "Hugging Face",
  "arXiv",
  "dev.to",
];

// 사이드바에 표시할 고정 출처 목록과 개수를 조립한다 ("전체"가 맨 앞, 미응답 출처는 0).
export function buildSourceItems(sources: SourceCount[], totalAll: number): SourceItem[] {
  return [
    { source: "", count: totalAll },
    ...SOURCE_FILTERS.map((source) => ({
      source,
      count: sources.find((item) => item.source === source)?.count ?? 0,
    })),
  ];
}
