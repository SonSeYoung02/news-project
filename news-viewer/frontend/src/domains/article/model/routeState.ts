import type { View } from "./articleState.ts";

export interface RouteState {
  view: View;
  articleId: number | null;
  source: string;
  search: string;
  page: number;
}

export interface DetailNavigationState {
  fromListUrl?: string;
  preferredArticleId?: number;
}

export const DEFAULT_ROUTE_STATE: RouteState = {
  view: "briefing",
  articleId: null,
  source: "",
  search: "",
  page: 1,
};

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === "/") return "/";
  return pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

export function parsePage(rawPage: string | number | null | undefined): number {
  if (typeof rawPage === "number") {
    return Number.isSafeInteger(rawPage) && rawPage >= 1 ? rawPage : 1;
  }
  if (!rawPage) return 1;
  const trimmed = rawPage.trim();
  if (!/^\d+$/.test(trimmed)) return 1;
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : 1;
}

export function parseArticleId(rawId: string | number | null | undefined): number | null {
  if (typeof rawId === "number") {
    return Number.isSafeInteger(rawId) && rawId >= 1 ? rawId : null;
  }
  if (!rawId) return null;
  const trimmed = rawId.trim();
  if (!/^[1-9]\d*$/.test(trimmed)) return null;
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : null;
}

export function isDefinedRoute(pathname: string): boolean {
  const norm = normalizePathname(pathname);
  if (norm === "/briefing" || norm === "/articles") return true;
  const match = norm.match(/^\/(briefing|articles)\/([^/]+)$/);
  if (!match) return false;
  return parseArticleId(match[2]) !== null;
}

export function parseRouteState(pathname: string, search = ""): RouteState {
  const norm = normalizePathname(pathname);

  if (norm === "/briefing") {
    return { ...DEFAULT_ROUTE_STATE, view: "briefing" };
  }

  const briefingDetail = norm.match(/^\/briefing\/([^/]+)$/);
  if (briefingDetail) {
    const articleId = parseArticleId(briefingDetail[1]);
    if (articleId !== null) {
      return { ...DEFAULT_ROUTE_STATE, view: "briefing", articleId };
    }
    return { ...DEFAULT_ROUTE_STATE };
  }

  if (norm === "/articles" || /^\/articles\/[^/]+$/.test(norm)) {
    const detailMatch = norm.match(/^\/articles\/([^/]+)$/);
    const articleId = detailMatch ? parseArticleId(detailMatch[1]) : null;
    if (detailMatch && articleId === null) {
      return { ...DEFAULT_ROUTE_STATE };
    }

    const params = new URLSearchParams(search);
    return {
      view: "articles",
      articleId,
      source: params.get("source") ?? "",
      search: params.get("q") ?? "",
      page: parsePage(params.get("page")),
    };
  }

  return { ...DEFAULT_ROUTE_STATE };
}

export function buildRouteUrl(route: RouteState): string {
  if (route.view === "briefing") {
    return route.articleId !== null ? `/briefing/${route.articleId}` : "/briefing";
  }

  const base = route.articleId !== null ? `/articles/${route.articleId}` : "/articles";
  const params = new URLSearchParams();
  if (route.source) params.set("source", route.source);
  if (route.search) params.set("q", route.search);
  const normalizedPage = parsePage(route.page);
  if (normalizedPage > 1) params.set("page", String(normalizedPage));

  const queryString = params.toString();
  return queryString ? `${base}?${queryString}` : base;
}

export function getListUrl(route: RouteState): string {
  return buildRouteUrl({ ...route, articleId: null });
}

export function switchViewRoute(current: RouteState, targetView: View): RouteState | null {
  if (current.view === targetView) return null;
  return {
    view: targetView,
    articleId: null,
    source: "",
    search: "",
    page: 1,
  };
}

export function toggleSourceRoute(current: RouteState, source: string): RouteState {
  const currentSource = current.view === "articles" ? current.source : "";
  const currentSearch = current.view === "articles" ? current.search : "";
  return {
    view: "articles",
    articleId: null,
    source: currentSource === source ? "" : source,
    search: currentSearch,
    page: 1,
  };
}

export function resetFiltersRoute(current: RouteState): RouteState {
  return {
    view: "articles",
    articleId: null,
    source: "",
    search: current.view === "articles" ? current.search : "",
    page: 1,
  };
}

export function submitSearchRoute(current: RouteState, query: string): RouteState {
  const normalizedQuery = query.trim() === "" ? "" : query;
  return {
    view: "articles",
    articleId: null,
    source: current.view === "articles" ? current.source : "",
    search: normalizedQuery,
    page: 1,
  };
}

export function resetSearchRoute(current: RouteState): RouteState {
  return {
    view: "articles",
    articleId: null,
    source: current.view === "articles" ? current.source : "",
    search: "",
    page: 1,
  };
}

export function changePageRoute(current: RouteState, nextPage: number): RouteState {
  return {
    view: "articles",
    articleId: null,
    source: current.view === "articles" ? current.source : "",
    search: current.view === "articles" ? current.search : "",
    page: parsePage(nextPage),
  };
}

export function selectArticleRoute(current: RouteState, articleId: number): RouteState {
  return {
    ...current,
    articleId,
  };
}

export function backToListRoute(current: RouteState): RouteState {
  return {
    ...current,
    articleId: null,
  };
}

export function createDetailNavigationState(current: RouteState): DetailNavigationState | undefined {
  if (current.articleId !== null) return undefined;
  return { fromListUrl: getListUrl(current) };
}

export function createFilterTransitionState(current: RouteState): DetailNavigationState | undefined {
  if (current.view === "briefing" && current.articleId !== null) {
    return { preferredArticleId: current.articleId };
  }
  return undefined;
}

export function getPreferredArticleId(navState: unknown): number | null {
  if (!navState || typeof navState !== "object") return null;
  const { preferredArticleId } = navState as DetailNavigationState;
  return typeof preferredArticleId === "number" ? preferredArticleId : null;
}

export function pickAutoSelectedArticleId(
  articleIds: number[],
  preferredArticleId: number | null = null,
): number | null {
  if (articleIds.length === 0) return null;
  if (preferredArticleId !== null && articleIds.includes(preferredArticleId)) {
    return preferredArticleId;
  }
  return articleIds[0];
}

export function shouldNavigateBackInHistory(navState: unknown, current: RouteState): boolean {
  if (!navState || typeof navState !== "object") return false;
  const { fromListUrl } = navState as DetailNavigationState;
  return typeof fromListUrl === "string" && fromListUrl === getListUrl(current);
}

export type DetailErrorKind = "none" | "not_found" | "error";

export function resolveArticleDetailErrorKind(error: unknown): Exclude<DetailErrorKind, "none"> {
  if (error && typeof error === "object" && "status" in error && (error as { status: unknown }).status === 404) {
    return "not_found";
  }
  return "error";
}

export function resolveArticleDetailError(error: unknown): string {
  if (resolveArticleDetailErrorKind(error) === "not_found") {
    return "요청한 기사를 찾을 수 없습니다.";
  }
  return "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.";
}

const APP_TITLE = "뉴스 뷰어";

export interface DocumentTitleParams {
  route: RouteState;
  articleTitle?: string | null;
  detailErrorKind?: DetailErrorKind;
}

export function getDocumentTitle({
  route,
  articleTitle,
  detailErrorKind = "none",
}: DocumentTitleParams): string {
  if (route.articleId !== null) {
    const trimmedTitle = articleTitle?.trim();
    if (trimmedTitle) {
      return `${trimmedTitle} - ${APP_TITLE}`;
    }
    if (detailErrorKind === "not_found") {
      return `기사를 찾을 수 없음 - ${APP_TITLE}`;
    }
    if (detailErrorKind === "error") {
      return `기사를 불러오지 못함 - ${APP_TITLE}`;
    }
    return APP_TITLE;
  }

  if (route.view === "briefing") {
    return `오늘의 AI 브리핑 - ${APP_TITLE}`;
  }

  const filterParts: string[] = [];
  if (route.source) {
    filterParts.push(route.source);
  }
  const trimmedSearch = route.search.trim();
  if (trimmedSearch) {
    filterParts.push(`'${trimmedSearch}'`);
  }

  const feedTitle = filterParts.length > 0 ? `${filterParts.join(" · ")} - 기사 피드` : "기사 피드";
  return `${feedTitle} - ${APP_TITLE}`;
}

export interface DetailEmptyMessageParams {
  view: View;
  articleId: number | null;
  listLoading: boolean;
  listError: string;
  detailLoading: boolean;
  detailError: string;
  itemCount: number;
  search: string;
}

export function getDetailEmptyMessage({
  view,
  articleId,
  listLoading,
  listError,
  detailLoading,
  detailError,
  itemCount,
  search,
}: DetailEmptyMessageParams): string {
  if (articleId !== null) {
    if (detailError) return detailError;
    if (detailLoading || listLoading) {
      return view === "briefing" ? "브리핑을 불러오는 중..." : "기사를 불러오는 중...";
    }
    return "요청한 기사를 찾을 수 없습니다.";
  }

  if (view === "briefing") {
    if (listLoading) return "브리핑을 불러오는 중...";
    if (listError) return "브리핑을 불러오지 못했습니다";
    if (itemCount === 0) return "최근 24시간에 수집된 AI 기사가 없습니다";
    return "기사를 선택하세요";
  }

  if (listLoading) return "기사를 불러오는 중...";
  if (listError) return "기사를 불러오지 못했습니다";
  if (itemCount === 0) return search ? "검색 결과가 없습니다" : "표시할 기사가 없습니다";
  return "기사를 선택하세요";
}

export interface AutoSelectParams {
  articleId: number | null;
  isCompact: boolean;
  listReady: boolean;
  listError: string;
  articleCount: number;
}

export function shouldAutoSelectFirstArticle({
  articleId,
  isCompact,
  listReady,
  listError,
  articleCount,
}: AutoSelectParams): boolean {
  return articleId === null && !isCompact && listReady && !listError && articleCount > 0;
}
