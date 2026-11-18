export interface Article {
  id: number;
  url: string;
  source: string;
  title: string;
  content: string | null;
  published_at: string | null;
  crawled_at: string | null;
  summary: string | null;
  major_category: string | null;
  sub_category: string | null;
  tags: string[];
  original_title: string | null;
  original_content: string | null;
  translated_title: string | null;
  translated_content: string | null;
  translation_status: string | null;
}

export interface ArticleListResult {
  total: number;
  page: number;
  size: number;
  articles: Article[];
}

export interface SourceCount {
  source: string;
  count: number;
}

// 사이드바 출처 항목 (source가 ""이면 "전체")
export interface SourceItem {
  source: string;
  count: number;
}
