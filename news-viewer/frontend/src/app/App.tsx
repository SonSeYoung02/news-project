import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Navigate, Route, Routes } from "react-router";
import {
  ArticleDetail,
  ArticleList,
  getDetailEmptyMessage,
  pickAutoSelectedArticleId,
  shouldAutoSelectFirstArticle,
  useArticleDetail,
  useArticleRoute,
  useArticleState,
  useArticles,
} from "../domains/article/index.ts";
import type { Article, View } from "../domains/article/index.ts";
import { BriefingList, useBriefing } from "../domains/briefing/index.ts";
import useMediaQuery from "../shared/hooks/useMediaQuery.ts";
import { sharedStyles } from "../shared/styles/shared.ts";
import type { StyleMap } from "../shared/styles/shared.ts";
import { BORDER } from "../shared/styles/theme.ts";
import Sidebar from "./layout/Sidebar.tsx";
import Topbar, { ReadingHeader } from "./layout/Topbar.tsx";

const COMPACT_QUERY = "(max-width: 1023px)";

const s = {
  layout: {
    display: "flex",
    height: "100dvh",
    overflow: "hidden",
    background: "#ffffff",
  },
  main: {
    flex: 1,
    minWidth: 0,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    background: "#ffffff",
  },
  content: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    overflow: "hidden",
  },
  listPanel: {
    flex: "0 0 clamp(340px, 32vw, 480px)",
    minWidth: 320,
    overflowY: "auto",
    borderRight: `1px solid ${BORDER}`,
    background: "#ffffff",
    padding: 0,
  },
  compactLayout: { flexDirection: "column" },
  compactList: { width: "100%", minWidth: 0, flex: 1, borderRight: "none" },
  error: sharedStyles.error,
} satisfies StyleMap;

function NewsViewerShell() {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const isCompact = useMediaQuery(COMPACT_QUERY, () => setFiltersOpen(false));

  const {
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
  } = useArticleRoute();

  const { view, articleId, source: selectedSource, search, page } = route;

  // hook 호출 순서가 곧 effect 실행 순서다: 기사 상태 → 브리핑 → 기사 피드 → 단건 조회 → 자동 선택.
  const articleState = useArticleState({
    view,
    isCompact,
    articleId,
    listKey: listUrl,
  });

  const {
    articles,
    error,
    listRef,
    saveScrollBeforeSelect,
  } = articleState;

  const {
    briefing,
    briefingLoading,
    briefingError,
    isBriefingReady,
    retryBriefing,
  } = useBriefing({ view });

  const {
    query,
    setQuery,
    metadataError,
    totalPages,
    sourceItems,
    isArticlesLoading,
    isArticlesReady,
  } = useArticles({
    articleState,
    view,
    page,
    selectedSource,
    search,
    listKey: listUrl,
  });

  const briefingArticles = briefing?.articles || [];
  const activeListArticles = view === "briefing" ? briefingArticles : articles;
  const activeListReady = view === "briefing" ? isBriefingReady : isArticlesReady;
  const activeListLoading = view === "briefing" ? briefingLoading : isArticlesLoading;
  const activeListError = view === "briefing" ? briefingError : error;

  const { selected, detailLoading, detailError } = useArticleDetail({
    articleId,
    listArticles: activeListArticles,
    listReady: activeListReady,
  });

  useEffect(() => {
    if (!isDefined) return;
    if (
      shouldAutoSelectFirstArticle({
        articleId,
        isCompact,
        listReady: activeListReady,
        listError: activeListError,
        articleCount: activeListArticles.length,
      })
    ) {
      const targetId = pickAutoSelectedArticleId(
        activeListArticles.map((article) => article.id),
        preferredArticleId,
      );
      if (targetId !== null) {
        replaceAutoSelectedArticle(targetId);
      }
    }
  }, [
    isDefined,
    articleId,
    isCompact,
    activeListReady,
    activeListError,
    activeListArticles,
    preferredArticleId,
    replaceAutoSelectedArticle,
  ]);

  if (!isDefined) {
    return <Navigate to="/briefing" replace />;
  }

  const handleSourceClick = (src: string) => {
    setFiltersOpen(false);
    toggleSource(src);
  };

  const handleSearchSubmit = (e?: FormEvent<HTMLFormElement>) => {
    e?.preventDefault();
    submitSearch(query);
  };

  const handleViewChange = (id: View) => {
    setFiltersOpen(false);
    goToView(id);
  };

  const handleSelectArticle = (article: Article) => {
    saveScrollBeforeSelect();
    selectArticle(article.id);
  };

  const handleRetryBriefing = () => {
    clearBriefingSelectionOnRefresh();
    retryBriefing();
  };

  const isDetailRoute = articleId !== null;
  const detailEmptyMessage = getDetailEmptyMessage({
    view,
    articleId,
    listLoading: activeListLoading,
    listError: activeListError,
    detailLoading,
    detailError,
    itemCount: activeListArticles.length,
    search,
  });

  return (
    <div style={{ ...s.layout, ...(isCompact ? s.compactLayout : {}) }}>
      <Sidebar
        isCompact={isCompact}
        filtersOpen={filtersOpen}
        onToggleFilters={() => setFiltersOpen((open) => !open)}
        view={view}
        onViewChange={handleViewChange}
        sourceItems={sourceItems}
        selectedSource={selectedSource}
        onSourceClick={handleSourceClick}
      />

      <main style={s.main}>
        {isCompact && isDetailRoute && <ReadingHeader selected={selected} onBack={goBackToList} />}

        <Topbar
          isCompact={isCompact}
          selected={selected}
          view={view}
          selectedSource={selectedSource}
          query={query}
          onQueryChange={setQuery}
          onSearchSubmit={handleSearchSubmit}
          hideOnCompact={isDetailRoute}
        />

        {((view === "articles" && error) || metadataError) && (
          <div role="alert" style={s.error}>
            {(view === "articles" && error) || metadataError}
          </div>
        )}

        <div style={s.content}>
          {/* 기사 목록 / 브리핑 목록 (스크롤 위치는 listRef로 보존) */}
          <div
            ref={listRef}
            aria-label={view === "briefing" ? "오늘의 AI 브리핑 목록" : "기사 목록"}
            style={{
              ...s.listPanel,
              ...(isCompact ? s.compactList : {}),
              ...(isCompact && isDetailRoute ? { display: "none" } : {}),
            }}
          >
            {view === "briefing" && (
              <BriefingList
                briefing={briefing}
                briefingLoading={briefingLoading}
                briefingError={briefingError}
                onRetry={handleRetryBriefing}
                selectedId={selected?.id ?? articleId ?? undefined}
                onSelectArticle={handleSelectArticle}
              />
            )}
            {view === "articles" && (
              <ArticleList
                articles={articles}
                loading={isArticlesLoading}
                error={error}
                search={search}
                selectedSource={selectedSource}
                selectedId={selected?.id ?? articleId ?? undefined}
                onSelectArticle={handleSelectArticle}
                onRemoveSource={() => handleSourceClick("")}
                onResetFilters={resetFilters}
                onResetSearch={resetSearch}
                page={page}
                totalPages={totalPages}
                onPageChange={changePage}
              />
            )}
          </div>

          <ArticleDetail
            selected={selected}
            isCompact={isCompact}
            emptyMessage={detailEmptyMessage}
            forceShowOnCompact={isDetailRoute}
          />
        </div>
      </main>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/briefing" replace />} />
      <Route element={<NewsViewerShell />}>
        <Route path="/briefing" element={null} />
        <Route path="/briefing/:id" element={null} />
        <Route path="/articles" element={null} />
        <Route path="/articles/:id" element={null} />
      </Route>
      <Route path="*" element={<Navigate to="/briefing" replace />} />
    </Routes>
  );
}

export default AppRoutes;
