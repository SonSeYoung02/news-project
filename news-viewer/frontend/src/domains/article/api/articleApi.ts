import { fetchJSON } from "../../../shared/api/client.ts";
import type { Article, ArticleListResult, SourceCount } from "../model/article.ts";
import type { ArticleDto, ArticleListResponseDto, SourceCountDto } from "./types.ts";

export interface FetchArticleListParams {
  page: number;
  size: number;
  source?: string;
  q?: string;
}

export function toArticle(dto: ArticleDto): Article {
  return {
    id: dto.id,
    url: dto.url,
    source: dto.source,
    title: dto.title,
    content: dto.content ?? null,
    published_at: dto.published_at ?? null,
    crawled_at: dto.crawled_at ?? null,
    summary: dto.summary ?? null,
    major_category: dto.major_category ?? null,
    sub_category: dto.sub_category ?? null,
    tags: Array.isArray(dto.tags) ? dto.tags : [],
    original_title: dto.original_title ?? null,
    original_content: dto.original_content ?? null,
    translated_title: dto.translated_title ?? null,
    translated_content: dto.translated_content ?? null,
    translation_status: dto.translation_status ?? null,
  };
}

export async function fetchArticleList(
  { page, size, source, q }: FetchArticleListParams,
  signal?: AbortSignal,
): Promise<ArticleListResult> {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (source) params.set("source", source);
  if (q) params.set("q", q);

  const dto = await fetchJSON<ArticleListResponseDto>(`/articles?${params}`, signal);
  return {
    total: dto.total,
    page: dto.page,
    size: dto.size,
    articles: Array.isArray(dto.articles) ? dto.articles.map(toArticle) : [],
  };
}

export async function fetchArticleById(articleId: number, signal?: AbortSignal): Promise<Article> {
  const dto = await fetchJSON<ArticleDto>(`/articles/${articleId}`, signal);
  return toArticle(dto);
}

export async function fetchSourceCounts(signal?: AbortSignal): Promise<SourceCount[]> {
  const dtos = await fetchJSON<SourceCountDto[]>("/sources", signal);
  return Array.isArray(dtos)
    ? dtos.map((item) => ({ source: item.source, count: item.count }))
    : [];
}

export async function fetchTotalArticleCount(signal?: AbortSignal): Promise<number> {
  const dto = await fetchJSON<ArticleListResponseDto>("/articles?page=1&size=1", signal);
  return dto.total;
}
