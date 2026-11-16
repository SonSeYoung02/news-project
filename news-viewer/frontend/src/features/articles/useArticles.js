import { useEffect, useState, useRef, useReducer } from "react";
import { fetchJSON } from "../../api/client.js";
import { articleReducer, initialArticleState } from "./articleState.js";

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

const SIZE = 20;

// 기사 목록·선택 상태(리듀서)와 목록 스크롤 위치를 관리한다.
// 선택된 기사(selected)는 브리핑 보기와 기사 보기가 함께 사용한다.
// 주의: effect 실행 순서를 유지하기 위해 App에서 useBriefing보다 먼저 호출한다.
export function useArticleState({ view, isCompact }) {
  const [articleState, dispatch] = useReducer(articleReducer, initialArticleState);

  const setSelected = (articleOrUpdater) => {
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

  const listRef = useRef(null);
  const listScrollPos = useRef(0);

  const handleSelectArticle = (article) => {
    if (listRef.current) {
      listScrollPos.current = listRef.current.scrollTop;
    }
    setSelected(article);
  };

  const handleBackToList = () => {
    setSelected(null);
  };

  const { selected } = articleState;
  useEffect(() => {
    if (!selected && isCompact && listRef.current && listScrollPos.current > 0) {
      requestAnimationFrame(() => {
        if (listRef.current) {
          listRef.current.scrollTop = listScrollPos.current;
        }
      });
    }
  }, [selected, isCompact]);

  const startFetch = () => {
    const nextReqId = ++reqIdRef.current;
    dispatch({ type: "START_FETCH", requestId: nextReqId, view: viewRef.current });
    return nextReqId;
  };

  const resetListScroll = () => {
    listScrollPos.current = 0;
    if (listRef.current) listRef.current.scrollTop = 0;
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
    handleSelectArticle,
    handleBackToList,
    startFetch,
    resetListScroll,
  };
}

// 기사 피드 조회 조건(페이지·출처·검색어)과 사이드바 메타데이터를 관리하고 기사 목록을 불러온다.
// requestId로 늦게 도착한 이전 응답을 버린다.
export function useArticles({ dispatch, reqIdRef, activeReqRef, viewRef, isCompactRef, startFetch, resetListScroll, total }) {
  const [sources, setSources] = useState([]);
  const [totalAll, setTotalAll] = useState(0);
  const [page, setPage] = useState(1);
  const [selectedSource, setSelectedSource] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [fetchRev, setFetchRev] = useState(0);
  const [metadataError, setMetadataError] = useState("");

  // totalAll은 마운트 시 한 번만 불러온다(사이드바 "전체" 개수 고정).
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchJSON("/sources", controller.signal),
      fetchJSON("/articles?page=1&size=1", controller.signal),
    ])
      .then(([sourceData, articleData]) => {
        setSources(sourceData);
        setTotalAll(articleData.total);
      })
      .catch(() => {
        if (!controller.signal.aborted) setMetadataError("필터 정보를 불러오지 못했습니다. 서버 연결을 확인해 주세요.");
      });
    return () => controller.abort();
  }, []);

  const triggerFetch = () => {
    startFetch();
    setFetchRev((r) => r + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    let currentReqId = reqIdRef.current;
    if (activeReqRef.current === currentReqId) {
      currentReqId = startFetch();
    }
    activeReqRef.current = currentReqId;

    const params = new URLSearchParams({ page, size: SIZE });
    if (selectedSource) params.set("source", selectedSource);
    if (search) params.set("q", search);

    fetchJSON(`/articles?${params}`, controller.signal)
      .then((data) => {
        dispatch({
          type: "FETCH_SUCCESS",
          requestId: currentReqId,
          articles: data.articles,
          total: data.total,
          isCompact: isCompactRef.current,
          view: viewRef.current,
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          dispatch({
            type: "FETCH_ERROR",
            requestId: currentReqId,
            error: "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
          });
        }
      });

    return () => controller.abort();
  }, [page, selectedSource, search, fetchRev]);

  const totalPages = Math.ceil(total / SIZE);
  const sourceItems = [
    { source: "", count: totalAll },
    ...SOURCE_FILTERS.map((source) => ({
      source,
      count: sources.find((item) => item.source === source)?.count ?? 0,
    })),
  ];

  // 아래 동작들은 호출 순서(triggerFetch → 상태 변경 → 스크롤 초기화)를 기존과 동일하게 유지한다.
  const toggleSource = (src) => {
    triggerFetch();
    setSelectedSource((prev) => (prev === src ? "" : src));
    setPage(1);
    resetListScroll();
  };

  const resetFilters = () => {
    triggerFetch();
    setSelectedSource("");
    setPage(1);
    resetListScroll();
  };

  const resetSearch = () => {
    triggerFetch();
    setQuery("");
    setSearch("");
    setPage(1);
    resetListScroll();
  };

  const submitSearch = () => {
    triggerFetch();
    setSearch(query);
    setPage(1);
    resetListScroll();
  };

  const changePage = (newPage) => {
    triggerFetch();
    setPage(newPage);
    resetListScroll();
  };

  return {
    sources,
    totalAll,
    page,
    selectedSource,
    query,
    setQuery,
    search,
    metadataError,
    totalPages,
    sourceItems,
    toggleSource,
    resetFilters,
    resetSearch,
    submitSearch,
    changePage,
  };
}
