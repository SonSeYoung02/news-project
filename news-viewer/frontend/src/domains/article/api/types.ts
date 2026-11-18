// 백엔드(news-viewer/backend/app) 응답 스키마에 대응하는 DTO 타입

// app/article/schemas.py Article
export interface ArticleDto {
  id: number;
  url: string;
  source: string;
  title: string;
  content?: string | null;
  published_at?: string | null;
  crawled_at?: string | null;
  summary?: string | null;
  major_category?: string | null;
  sub_category?: string | null;
  tags?: string[] | null;
  original_title?: string | null;
  original_content?: string | null;
  translated_title?: string | null;
  translated_content?: string | null;
  translation_status?: string | null;
}

// GET /articles (ArticleListResponse)
export interface ArticleListResponseDto {
  total: number;
  page: number;
  size: number;
  articles?: ArticleDto[] | null;
}

// GET /sources 항목 (SourceCount)
export interface SourceCountDto {
  source: string;
  count: number;
}

// GET /categories 항목 (CategoryCount)
export interface CategoryCountDto {
  major_category: string;
  count: number;
}
