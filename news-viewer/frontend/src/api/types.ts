// 백엔드(news-viewer/backend/app) 응답 스키마에 대응하는 타입

// app/article/schemas.py Article
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

// GET /articles (ArticleListResponse)
export interface ArticleListResponse {
  total: number;
  page: number;
  size: number;
  articles: Article[];
}

// GET /briefing (BriefingResponse)
export interface BriefingResponse {
  generated_at: string;
  window_start: string;
  window_end: string;
  selection_method: string;
  articles: Article[];
}

// GET /sources 항목 (SourceCount)
export interface SourceCount {
  source: string;
  count: number;
}

// GET /categories 항목 (CategoryCount)
export interface CategoryCount {
  major_category: string;
  count: number;
}
