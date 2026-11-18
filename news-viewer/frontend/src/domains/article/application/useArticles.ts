import { useEffect, useState, useRef, useReducer } from "react";
import type { Dispatch, MutableRefObject, RefObject } from "react";
import { fetchArticleList, fetchSourceCounts, fetchTotalArticleCount } from "../api/articleApi.ts";
import type { SourceCount, SourceItem } from "../model/article.ts";
import { articleReducer, initialArticleState } from "../model/articleState.ts";
import type { ArticleAction, ArticleState, SelectedUpdater, View } from "../model/articleState.ts";
import { buildSourceItems } from "../model/sourceFilters.ts";

const SIZE = 20;

export interface UseArticleStateOptions {
  view: View;
  isCompact: boolean;
  articleId: number | null;
  listKey: string;
}

export interface ArticleStateApi extends ArticleState {
  dispatch: Dispatch<ArticleAction>;
  setSelected: (articleOrUpdater: SelectedUpdater) => void;
  reqIdRef: MutableRefObject<number>;
  activeReqRef: MutableRefObject<number>;
  viewRef: MutableRefObject<View>;
  isCompactRef: MutableRefObject<boolean>;
  listRef: RefObject<HTMLDivElement>;
  saveScrollBeforeSelect: () => void;
  startFetch: () => number;
  resetListScroll: () => void;
}

// 기사 목록·선택 상태(리듀서)와 목록 스크롤 위치를 관리한다.
// 주의: effect 실행 순서를 유지하기 위해 App에서 useBriefing보다 먼저 호출한다.
export function useArticleState({ view, isCompact, articleId, listKey }: UseArticleStateOptions): ArticleStateApi {
  const [articleState, dispatch] = useReducer(articleReducer, initialArticleState);

  const setSelected = (articleOrUpdater: SelectedUpdater) => {
    dispatch({ type: "SELECT_ARTICLE", payload: articleOrUpdater });
  };

  const reqIdRef = useRef(0);
  const activeReqRef = useRef(0);

  const viewRef = useRef(view);
  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  const isCompactRef = useRef(isCompact);
  useEffect(() => {
    isCompactRef.current = isCompact;
    dispatch({ type: "RESIZE_VIEWPORT", isCompact, view });
  }, [isCompact, view]);

  const listRef = useRef<HTMLDivElement>(null);
  const listScrollPos = useRef(0);
  const prevListKeyRef = useRef(listKey);

  const saveScrollBeforeSelect = () => {
    if (listRef.current) {
      listScrollPos.current = listRef.current.scrollTop;
    }
  };

  const resetListScroll = () => {
    listScrollPos.current = 0;
    if (listRef.current) listRef.current.scrollTop = 0;
  };

  useEffect(() => {
    if (prevListKeyRef.current !== listKey) {
      prevListKeyRef.current = listKey;
      resetListScroll();
      return;
    }
    if (articleId === null && isCompact && listRef.current && listScrollPos.current > 0) {
      requestAnimationFrame(() => {
        if (listRef.current) {
          listRef.current.scrollTop = listScrollPos.current;
        }
      });
    }
  }, [articleId, isCompact, listKey]);

  const startFetch = () => {
    const nextReqId = ++reqIdRef.current;
    dispatch({ type: "START_FETCH", requestId: nextReqId, view: viewRef.current });
    return nextReqId;
  };

  return {
    ...articleState,
    dispatch,
    setSelected,
    reqIdRef,
    activeReqRef,
    viewRef,
    isCompactRef,
    listRef,
    saveScrollBeforeSelect,
    startFetch,
    resetListScroll,
  };
}

export interface UseArticlesOptions {
  articleState: ArticleStateApi;
  view: View;
  page: number;
  selectedSource: string;
  search: string;
  listKey: string;
}

// URL에서 파생된 조회 조건(보기·페이지·출처·검색어)과 사이드바 메타데이터를 관리하고 기사 목록을 불러온다.
// requestId로 늦게 도착한 이전 응답을 버린다.
export function useArticles({
  articleState,
  view,
  page,
  selectedSource,
  search,
  listKey,
}: UseArticlesOptions) {
  const {
    dispatch,
    reqIdRef,
    activeReqRef,
    viewRef,
    isCompactRef,
    startFetch,
    loading,
    total,
  } = articleState;

  const [sources, setSources] = useState<SourceCount[]>([]);
  const [totalAll, setTotalAll] = useState(0);
  const [query, setQuery] = useState(search);
  const [metadataError, setMetadataError] = useState("");
  const [loadedListKey, setLoadedListKey] = useState("");

  useEffect(() => {
    setQuery(search);
  }, [search]);

  // totalAll은 마운트 시 한 번만 불러온다(사이드바 "전체" 개수 고정).
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchSourceCounts(controller.signal),
      fetchTotalArticleCount(controller.signal),
    ])
      .then(([sourceData, totalCount]) => {
        setSources(sourceData);
        setTotalAll(totalCount);
      })
      .catch(() => {
        if (!controller.signal.aborted) setMetadataError("필터 정보를 불러오지 못했습니다. 서버 연결을 확인해 주세요.");
      });
    return () => controller.abort();
  }, []);

  const currentListKey = view === "articles" ? listKey : "";

  useEffect(() => {
    if (view !== "articles") {
      setLoadedListKey("");
      return;
    }

    const controller = new AbortController();
    const currentReqId = startFetch();
    activeReqRef.current = currentReqId;

    fetchArticleList(
      {
        page,
        size: SIZE,
        source: selectedSource || undefined,
        q: search || undefined,
      },
      controller.signal,
    )
      .then((data) => {
        dispatch({
          type: "FETCH_SUCCESS",
          requestId: currentReqId,
          articles: data.articles,
          total: data.total,
          isCompact: isCompactRef.current,
          view: viewRef.current,
        });
        if (reqIdRef.current === currentReqId) {
          setLoadedListKey(currentListKey);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          dispatch({
            type: "FETCH_ERROR",
            requestId: currentReqId,
            error: "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
            view: viewRef.current,
          });
          if (reqIdRef.current === currentReqId) {
            setLoadedListKey(currentListKey);
          }
        }
      });

    return () => controller.abort();
  }, [view, page, selectedSource, search, currentListKey]);

  const totalPages = Math.ceil(total / SIZE);
  const sourceItems: SourceItem[] = buildSourceItems(sources, totalAll);

  const isArticlesLoading = view === "articles" && (loading || loadedListKey !== currentListKey);
  const isArticlesReady = view === "articles" && !loading && loadedListKey === currentListKey;

  return {
    sources,
    totalAll,
    query,
    setQuery,
    metadataError,
    totalPages,
    sourceItems,
    isArticlesLoading,
    isArticlesReady,
  };
}
