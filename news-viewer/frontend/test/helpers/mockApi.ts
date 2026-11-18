import { act } from "@testing-library/react";
import { vi } from "vitest";
import type {
  Article,
  ArticleListResponseDto as ArticleListResponse,
  SourceCount,
} from "../../src/domains/article/index.ts";
import type { Briefing, BriefingResponseDto as BriefingResponse } from "../../src/domains/briefing/index.ts";

const COMPACT_QUERY = "(max-width: 1023px)";
let compactViewport = false;
const mediaListeners = new Set<(event: MediaQueryListEvent) => void>();

function createMediaQueryList(query: string): MediaQueryList {
  return {
    get matches() {
      return query === COMPACT_QUERY ? compactViewport : false;
    },
    media: query,
    onchange: null,
    addEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
      if (type !== "change" || typeof listener !== "function") return;
      mediaListeners.add(listener as (event: MediaQueryListEvent) => void);
    },
    removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
      if (type !== "change" || typeof listener !== "function") return;
      mediaListeners.delete(listener as (event: MediaQueryListEvent) => void);
    },
    addListener(listener: ((this: MediaQueryList, ev: MediaQueryListEvent) => void) | null) {
      if (listener) mediaListeners.add(listener);
    },
    removeListener(listener: ((this: MediaQueryList, ev: MediaQueryListEvent) => void) | null) {
      if (listener) mediaListeners.delete(listener);
    },
    dispatchEvent() {
      return true;
    },
  } as MediaQueryList;
}

export function installMatchMediaMock(): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => createMediaQueryList(query),
  });
}

export function resetViewportMock(): void {
  compactViewport = false;
  mediaListeners.clear();
  installMatchMediaMock();
}

export function setViewportCompact(isCompact: boolean): void {
  installMatchMediaMock();
  const changed = compactViewport !== isCompact;
  compactViewport = isCompact;
  if (!changed || mediaListeners.size === 0) return;

  const event = Object.assign(new Event("change"), {
    matches: isCompact,
    media: COMPACT_QUERY,
  }) as MediaQueryListEvent;

  act(() => {
    for (const listener of [...mediaListeners]) {
      listener(event);
    }
  });
}

export function createMockArticle(overrides: Partial<Article> = {}): Article {
  const id = overrides.id ?? 1;
  return {
    id,
    url: `https://example.com/articles/${id}`,
    source: "GeekNews",
    title: `테스트 기사 ${id}`,
    content: `테스트 기사 본문 ${id}`,
    published_at: "2026-11-18T08:00:00Z",
    crawled_at: "2026-11-18T08:30:00Z",
    summary: `테스트 기사 요약 ${id}`,
    major_category: "AI",
    sub_category: "LLM",
    tags: ["AI", "LLM"],
    original_title: null,
    original_content: null,
    translated_title: null,
    translated_content: null,
    translation_status: null,
    ...overrides,
  };
}

export function createMockBriefing(overrides: Partial<Briefing> = {}): Briefing {
  return {
    generated_at: "2026-11-18T09:00:00Z",
    window_start: "2026-11-17T09:00:00Z",
    window_end: "2026-11-18T09:00:00Z",
    selection_method: "hybrid",
    articles: [
      createMockArticle({
        id: 101,
        source: "GeekNews",
        title: "오늘의 브리핑 AI 기사 1",
        summary: "브리핑 핵심 요약 1",
        content: "브리핑 기사 본문 1",
        major_category: "AI",
        sub_category: "에이전트",
        tags: ["AI", "Agent", "LLM", "Briefing"],
      }),
      createMockArticle({
        id: 102,
        source: "arXiv",
        title: "오늘의 브리핑 AI 기사 2",
        summary: "브리핑 핵심 요약 2",
        content: "브리핑 기사 본문 2",
        major_category: "AI 연구",
        sub_category: "추론",
        tags: ["Research", "Reasoning"],
      }),
    ],
    ...overrides,
  };
}

export const DEFAULT_SOURCES: SourceCount[] = [
  { source: "네이버뉴스", count: 5 },
  { source: "Google News", count: 3 },
  { source: "GeekNews", count: 4 },
  { source: "Reddit AI", count: 2 },
  { source: "GitHub Trending", count: 1 },
  { source: "Hugging Face", count: 6 },
  { source: "arXiv", count: 7 },
  { source: "dev.to", count: 2 },
];

const DEFAULT_ARTICLES: Article[] = [
  createMockArticle({
    id: 1,
    source: "GeekNews",
    title: "기본 피드 기사 1",
    summary: "기본 피드 요약 1",
    content: "기본 피드 본문 1",
    tags: ["AI", "GeekNews"],
  }),
  createMockArticle({
    id: 2,
    source: "arXiv",
    title: "기본 피드 기사 2",
    summary: "기본 피드 요약 2",
    content: "기본 피드 본문 2",
    major_category: "AI 연구",
    tags: ["Research", "arXiv"],
  }),
];

export interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

export function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export interface RecordedRequest {
  url: string;
  pathname: string;
  searchParams: URLSearchParams;
  signal: AbortSignal | undefined;
}

export interface ArticlesQuery {
  page: number;
  size: number;
  source: string;
  q: string;
}

export interface HttpErrorPayload {
  status: number;
  body?: unknown;
}

export type EndpointPayload<T> = T | Error | HttpErrorPayload;
export type MockEndpointValue<T> = EndpointPayload<T> | Promise<EndpointPayload<T>>;

export type BriefingOption =
  | MockEndpointValue<BriefingResponse>
  | ((req: RecordedRequest) => MockEndpointValue<BriefingResponse>);

export type SourcesOption =
  | MockEndpointValue<SourceCount[]>
  | ((req: RecordedRequest) => MockEndpointValue<SourceCount[]>);

export type ArticlesOption =
  | Article[]
  | MockEndpointValue<ArticleListResponse>
  | ((query: ArticlesQuery, req: RecordedRequest) => MockEndpointValue<ArticleListResponse>);

export interface MockApiOptions {
  briefing?: BriefingOption;
  sources?: SourcesOption;
  articles?: ArticlesOption;
  totalAll?: number;
}

export interface MockFetchController {
  calls: string[];
  requests: RecordedRequest[];
  setBriefing: (next: BriefingOption) => void;
  setSources: (next: SourcesOption) => void;
  setArticles: (next: ArticlesOption) => void;
}

function isHttpErrorPayload(value: unknown): value is HttpErrorPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    typeof (value as HttpErrorPayload).status === "number"
  );
}

async function toFetchResponse<T>(value: MockEndpointValue<T>): Promise<Response> {
  const resolved = await value;
  if (resolved instanceof Error) {
    throw resolved;
  }
  if (isHttpErrorPayload(resolved)) {
    return {
      ok: resolved.status >= 200 && resolved.status < 300,
      status: resolved.status,
      json: async () => resolved.body ?? {},
    } as Response;
  }
  return {
    ok: true,
    status: 200,
    json: async () => resolved,
  } as Response;
}

function paginateArticles(
  allArticles: Article[],
  query: ArticlesQuery,
  totalAllOverride?: number,
): ArticleListResponse {
  if (query.size === 1 && !query.source && !query.q && totalAllOverride !== undefined) {
    return {
      total: totalAllOverride,
      page: 1,
      size: 1,
      articles: allArticles.slice(0, 1),
    };
  }

  const keyword = query.q.trim().toLowerCase();
  const filtered = allArticles.filter((article) => {
    if (query.source && article.source !== query.source) return false;
    if (!keyword) return true;
    return [article.title, article.content ?? "", article.summary ?? ""].some((field) =>
      field.toLowerCase().includes(keyword),
    );
  });

  const start = Math.max(0, (query.page - 1) * query.size);
  return {
    total: filtered.length,
    page: query.page,
    size: query.size,
    articles: filtered.slice(start, start + query.size),
  };
}

export function setupMockFetch(options: MockApiOptions = {}): MockFetchController {
  const calls: string[] = [];
  const requests: RecordedRequest[] = [];

  let briefingOption: BriefingOption = options.briefing ?? createMockBriefing();
  let sourcesOption: SourcesOption = options.sources ?? DEFAULT_SOURCES;
  let articlesOption: ArticlesOption = options.articles ?? DEFAULT_ARTICLES;

  if (!globalThis.fetch) {
    globalThis.fetch = (() => Promise.reject(new Error("fetch is not implemented"))) as typeof fetch;
  }

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const parsed = new URL(rawUrl, "http://127.0.0.1");
    const req: RecordedRequest = {
      url: rawUrl,
      pathname: parsed.pathname,
      searchParams: parsed.searchParams,
      signal: init?.signal ?? undefined,
    };

    calls.push(rawUrl);
    requests.push(req);

    if (parsed.pathname === "/api/briefing") {
      const result = typeof briefingOption === "function" ? briefingOption(req) : briefingOption;
      return toFetchResponse(result);
    }

    if (parsed.pathname === "/api/sources") {
      const result = typeof sourcesOption === "function" ? sourcesOption(req) : sourcesOption;
      return toFetchResponse(result);
    }

    if (parsed.pathname === "/api/articles") {
      const query: ArticlesQuery = {
        page: Number(parsed.searchParams.get("page") || "1"),
        size: Number(parsed.searchParams.get("size") || "20"),
        source: parsed.searchParams.get("source") || "",
        q: parsed.searchParams.get("q") || "",
      };

      if (Array.isArray(articlesOption)) {
        return toFetchResponse(paginateArticles(articlesOption, query, options.totalAll));
      }
      if (typeof articlesOption === "function") {
        return toFetchResponse(articlesOption(query, req));
      }
      return toFetchResponse(articlesOption);
    }

    return {
      ok: false,
      status: 404,
      json: async () => ({ detail: `Unhandled path: ${parsed.pathname}` }),
    } as Response;
  });

  return {
    calls,
    requests,
    setBriefing(next) {
      briefingOption = next;
    },
    setSources(next) {
      sourcesOption = next;
    },
    setArticles(next) {
      articlesOption = next;
    },
  };
}
