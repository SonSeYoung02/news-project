import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArticleDetail, ArticleList, useArticleState, useArticles } from "../domains/article/index.ts";
import type { View } from "../domains/article/index.ts";
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

export default function App() {
  const [view, setView] = useState<View>("briefing");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const isCompact = useMediaQuery(COMPACT_QUERY, () => setFiltersOpen(false));

  // hook 호출 순서가 곧 effect 실행 순서다: 기사 상태 → 브리핑 → 기사 피드 → 자동 선택.
  const articleState = useArticleState({ view, isCompact });
  const {
    articles,
    loading,
    error,
    selected,
    setSelected,
    isCompactRef,
    listRef,
    handleSelectArticle,
    handleBackToList,
  } = articleState;

  const { briefing, briefingLoading, briefingError, retryBriefing } = useBriefing({ view, setSelected, isCompactRef });

  const {
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
  } = useArticles(articleState);

  useEffect(() => {
    if (view === "briefing" && !isCompact && !briefingLoading && !selected && briefing && (briefing.articles || []).length > 0) {
      setSelected(briefing.articles[0]);
    }
  }, [view, isCompact, briefingLoading, selected, briefing]);

  useEffect(() => {
    if (view === "articles" && !isCompact && !loading && !selected && articles.length > 0) {
      setSelected(articles[0]);
    }
  }, [view, isCompact, loading, selected, articles]);

  const handleSourceClick = (src: string) => {
    setView("articles");
    setFiltersOpen(false);
    toggleSource(src);
  };

  const handleResetFilters = () => {
    setView("articles");
    resetFilters();
  };

  const handleResetSearch = () => {
    setView("articles");
    resetSearch();
  };

  const handleSearchSubmit = (e?: FormEvent<HTMLFormElement>) => {
    e?.preventDefault();
    setView("articles");
    submitSearch();
  };

  const handleViewChange = (id: View) => {
    if (view !== id) {
      setView(id);
      setSelected(null);
    }
    setFiltersOpen(false);
  };

  const detailEmptyMessage =
    view === "briefing"
      ? (briefingLoading
          ? "브리핑을 불러오는 중..."
          : briefingError
          ? "브리핑을 불러오지 못했습니다"
          : (briefing?.articles || []).length === 0
          ? "최근 24시간에 수집된 AI 기사가 없습니다"
          : "기사를 선택하세요")
      : (loading
          ? "기사를 불러오는 중..."
          : error
          ? "기사를 불러오지 못했습니다"
          : articles.length === 0
          ? (search ? "검색 결과가 없습니다" : "표시할 기사가 없습니다")
          : "기사를 선택하세요");

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
        {isCompact && selected && <ReadingHeader selected={selected} onBack={handleBackToList} />}

        <Topbar
          isCompact={isCompact}
          selected={selected}
          view={view}
          selectedSource={selectedSource}
          query={query}
          onQueryChange={setQuery}
          onSearchSubmit={handleSearchSubmit}
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
              ...(isCompact && selected ? { display: "none" } : {}),
            }}
          >
            {view === "briefing" && (
              <BriefingList
                briefing={briefing}
                briefingLoading={briefingLoading}
                briefingError={briefingError}
                onRetry={retryBriefing}
                selectedId={selected?.id}
                onSelectArticle={handleSelectArticle}
              />
            )}
            {view === "articles" && (
              <ArticleList
                articles={articles}
                loading={loading}
                error={error}
                search={search}
                selectedSource={selectedSource}
                selectedId={selected?.id}
                onSelectArticle={handleSelectArticle}
                onRemoveSource={() => handleSourceClick("")}
                onResetFilters={handleResetFilters}
                onResetSearch={handleResetSearch}
                page={page}
                totalPages={totalPages}
                onPageChange={changePage}
              />
            )}
          </div>

          <ArticleDetail selected={selected} isCompact={isCompact} emptyMessage={detailEmptyMessage} />
        </div>
      </main>
    </div>
  );
}
