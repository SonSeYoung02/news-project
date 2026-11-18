import { ACCENT_LIGHT, ACCENT_DARK, BORDER, TEXT_SECONDARY } from "../../../shared/styles/theme.ts";
import { sharedStyles } from "../../../shared/styles/shared.ts";
import type { StyleMap } from "../../../shared/styles/shared.ts";
import type { Article } from "../model/article.ts";
import ArticleCard from "./ArticleCard.tsx";
import Pagination from "./Pagination.tsx";

const s = {
  activeFilterBar: {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 8,
    padding: "10px 14px",
    margin: "12px 14px",
    background: "#f6f9f6",
    borderRadius: 8,
    border: "1px solid #dbe6dc",
    maxWidth: "calc(100% - 28px)",
    boxSizing: "border-box",
  },
  activeFilterLabel: {
    fontSize: 12,
    fontWeight: 650,
    color: "#28382c",
    marginRight: 2,
  },
  activeFilterChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    minHeight: 44,
    padding: "6px 12px",
    boxSizing: "border-box",
    borderRadius: 20,
    background: ACCENT_LIGHT,
    color: ACCENT_DARK,
    border: "1px solid #cce2d0",
    fontSize: 12.5,
    fontWeight: 550,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  activeFilterRemove: {
    fontSize: 11,
    fontWeight: 700,
    lineHeight: 1,
    color: "inherit",
  },
  filterResetBtn: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    padding: "6px 10px",
    boxSizing: "border-box",
    borderRadius: 6,
    background: "transparent",
    color: TEXT_SECONDARY,
    border: "none",
    fontSize: 12,
    fontWeight: 500,
    cursor: "pointer",
    marginLeft: "auto",
    fontFamily: "inherit",
    textDecoration: "underline",
  },
  emptyState: {
    padding: "48px 20px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
  },
  emptyIcon: {
    fontSize: 32,
    marginBottom: 12,
    opacity: 0.7,
  },
  emptyTitle: {
    fontSize: 15,
    fontWeight: 650,
    color: "#16241a",
    marginBottom: 6,
    letterSpacing: "-0.2px",
  },
  emptyDesc: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    lineHeight: 1.5,
    maxWidth: 280,
    marginBottom: 18,
  },
  resetBtn: {
    padding: "8px 18px",
    borderRadius: 7,
    border: `1px solid ${BORDER}`,
    background: "#ffffff",
    color: ACCENT_DARK,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    transition: "background 0.15s, border-color 0.15s",
    fontFamily: "inherit",
  },
  statusText: sharedStyles.statusText,
  touchButton: sharedStyles.touchButton,
} satisfies StyleMap;

interface ArticleListProps {
  articles: Article[];
  loading: boolean;
  error: string;
  search: string;
  selectedSource: string;
  selectedId: number | undefined;
  onSelectArticle: (article: Article) => void;
  onRemoveSource: () => void;
  onResetFilters: () => void;
  onResetSearch: () => void;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

// 전체 기사 보기의 목록 영역: 적용된 필터, 로딩·빈 결과 상태, 기사 카드, 페이지 이동
export default function ArticleList({
  articles,
  loading,
  error,
  search,
  selectedSource,
  selectedId,
  onSelectArticle,
  onRemoveSource,
  onResetFilters,
  onResetSearch,
  page,
  totalPages,
  onPageChange,
}: ArticleListProps) {
  const activeChips = [
    ...(selectedSource
      ? [
          {
            key: "source",
            label: `출처: ${selectedSource}`,
            ariaLabel: `출처: ${selectedSource} 필터 해제`,
            onRemove: onRemoveSource,
          },
        ]
      : []),
    ...(search
      ? [
          {
            key: "search",
            label: `검색: ${search}`,
            ariaLabel: `검색: ${search} 필터 해제`,
            onRemove: onResetSearch,
          },
        ]
      : []),
  ];

  return (
    <>
      {activeChips.length > 0 && (
        <div style={s.activeFilterBar} aria-label="활성 필터">
          <span style={s.activeFilterLabel}>적용된 필터:</span>
          {activeChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              style={s.activeFilterChip}
              onClick={chip.onRemove}
              aria-label={chip.ariaLabel}
            >
              <span>{chip.label}</span>
              <span style={s.activeFilterRemove} aria-hidden="true">✕</span>
            </button>
          ))}
          {selectedSource && (
            <button
              type="button"
              style={s.filterResetBtn}
              onClick={onResetFilters}
            >
              필터 초기화
            </button>
          )}
        </div>
      )}

      {loading && <div style={s.statusText}>불러오는 중...</div>}
      {!loading && !error && articles.length === 0 && (
        search ? (
          <div style={s.emptyState}>
            <div style={s.emptyIcon} aria-hidden="true">🔍</div>
            <div style={s.emptyTitle}>
              &lsquo;{search}&rsquo;에 대한 검색 결과가 없습니다
            </div>
            <div style={s.emptyDesc}>
              단어의 철자가 정확한지 확인하거나 다른 검색어로 검색해 보세요.
            </div>
            <button
              type="button"
              onClick={onResetSearch}
              style={{ ...s.resetBtn, ...s.touchButton }}
            >
              검색어 초기화
            </button>
          </div>
        ) : (
          <div style={s.statusText}>기사가 없습니다</div>
        )
      )}

      {(!loading ? articles : []).map((a) => (
        <ArticleCard key={a.id} article={a} selected={selectedId === a.id} onSelect={onSelectArticle} />
      ))}

      {totalPages > 1 && (
        <Pagination page={page} totalPages={totalPages} onPageChange={onPageChange} />
      )}
    </>
  );
}
