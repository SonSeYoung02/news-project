import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router";
import type { View } from "../model/articleState.ts";
import {
  buildRouteUrl,
  changePageRoute,
  createDetailNavigationState,
  createFilterTransitionState,
  getListUrl,
  getPreferredArticleId,
  isDefinedRoute,
  parseRouteState,
  resetFiltersRoute,
  resetSearchRoute,
  selectArticleRoute,
  shouldNavigateBackInHistory,
  submitSearchRoute,
  switchViewRoute,
  toggleSourceRoute,
} from "../model/routeState.ts";
import type { DetailNavigationState, RouteState } from "../model/routeState.ts";

// react-router 위치와 URL 상태 전환을 조율하는 hook.
export function useArticleRoute() {
  const location = useLocation();
  const navigate = useNavigate();

  const isDefined = useMemo(() => isDefinedRoute(location.pathname), [location.pathname]);
  const route = useMemo(
    () => parseRouteState(location.pathname, location.search),
    [location.pathname, location.search],
  );
  const listUrl = useMemo(() => getListUrl(route), [route]);
  const preferredArticleId = useMemo(
    () => getPreferredArticleId(location.state),
    [location.state],
  );

  const navigateToRoute = useCallback(
    (next: RouteState | null, options?: { replace?: boolean; state?: DetailNavigationState }) => {
      if (!next) return;
      navigate(buildRouteUrl(next), options);
    },
    [navigate],
  );

  const goToView = useCallback(
    (targetView: View) => {
      navigateToRoute(switchViewRoute(route, targetView));
    },
    [navigateToRoute, route],
  );

  const toggleSource = useCallback(
    (src: string) => {
      const state = createFilterTransitionState(route);
      navigateToRoute(toggleSourceRoute(route, src), state ? { state } : undefined);
    },
    [navigateToRoute, route],
  );

  const resetFilters = useCallback(() => {
    const state = createFilterTransitionState(route);
    navigateToRoute(resetFiltersRoute(route), state ? { state } : undefined);
  }, [navigateToRoute, route]);

  const submitSearch = useCallback(
    (query: string) => {
      const state = createFilterTransitionState(route);
      navigateToRoute(submitSearchRoute(route, query), state ? { state } : undefined);
    },
    [navigateToRoute, route],
  );

  const resetSearch = useCallback(() => {
    const state = createFilterTransitionState(route);
    navigateToRoute(resetSearchRoute(route), state ? { state } : undefined);
  }, [navigateToRoute, route]);

  const changePage = useCallback(
    (nextPage: number) => {
      navigateToRoute(changePageRoute(route, nextPage));
    },
    [navigateToRoute, route],
  );

  const selectArticle = useCallback(
    (articleId: number) => {
      const nextUrl = buildRouteUrl(selectArticleRoute(route, articleId));
      const state = createDetailNavigationState(route);
      navigate(nextUrl, state ? { state } : undefined);
    },
    [navigate, route],
  );

  const replaceAutoSelectedArticle = useCallback(
    (articleId: number) => {
      navigate(buildRouteUrl(selectArticleRoute(route, articleId)), { replace: true });
    },
    [navigate, route],
  );

  const clearBriefingSelectionOnRefresh = useCallback(() => {
    if (route.view === "briefing" && route.articleId !== null) {
      navigate("/briefing", { replace: true });
    }
  }, [navigate, route]);

  const goBackToList = useCallback(() => {
    if (shouldNavigateBackInHistory(location.state, route)) {
      navigate(-1);
      return;
    }
    navigate(listUrl);
  }, [listUrl, location.state, navigate, route]);

  return {
    route,
    isDefined,
    listUrl,
    preferredArticleId,
    goToView,
    toggleSource,
    resetFilters,
    submitSearch,
    resetSearch,
    changePage,
    selectArticle,
    replaceAutoSelectedArticle,
    clearBriefingSelectionOnRefresh,
    goBackToList,
  };
}
