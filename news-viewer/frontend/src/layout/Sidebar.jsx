import { ACCENT, ACCENT_LIGHT, ACCENT_DARK, BORDER, TEXT_MUTED } from "../styles/theme.js";
import { sharedStyles } from "../styles/shared.js";

const VIEW_ITEMS = [
  { id: "briefing", label: "오늘의 AI 브리핑" },
  { id: "articles", label: "전체 기사" },
];

const s = {
  sidebar: {
    width: 240,
    background: "#f7f9f7",
    borderRight: `1px solid ${BORDER}`,
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
  },
  sidebarHeader: {
    padding: "20px 18px 16px",
    borderBottom: `1px solid ${BORDER}`,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sidebarBrand: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  sidebarBrandIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    background: ACCENT,
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 750,
    fontSize: 16,
    flexShrink: 0,
  },
  sidebarTitle: {
    fontSize: 17,
    fontWeight: 750,
    color: "#16241a",
    letterSpacing: "-0.4px",
    lineHeight: 1.25,
  },
  sidebarSubtitle: {
    fontSize: 11,
    color: TEXT_MUTED,
    marginTop: 2,
    fontWeight: 500,
  },
  sidebarScroll: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "14px 10px 18px",
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: TEXT_MUTED,
    textTransform: "uppercase",
    letterSpacing: "0.6px",
    padding: "0 10px",
    marginBottom: 6,
    marginTop: 18,
  },
  filterItem: (active) => ({
    width: "100%",
    minHeight: 44,
    padding: "8px 12px",
    borderRadius: 7,
    border: "none",
    cursor: "pointer",
    marginBottom: 2,
    background: active ? ACCENT_LIGHT : "transparent",
    color: active ? ACCENT_DARK : "#334136",
    fontWeight: active ? 650 : 450,
    fontSize: 13.5,
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    transition: "background 0.15s, color 0.15s",
    fontFamily: "inherit",
    textAlign: "left",
  }),
  filterCount: (active) => ({
    fontSize: 11,
    color: active ? ACCENT_DARK : TEXT_MUTED,
    fontWeight: 500,
    fontVariantNumeric: "tabular-nums",
    background: active ? "#d7eadb" : "#edf2ee",
    padding: "2px 7px",
    borderRadius: 10,
  }),
  compactSidebar: { width: "100%", flexShrink: 0, borderRight: "none", borderBottom: `1px solid ${BORDER}` },
  compactHeader: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "12px 16px", borderBottom: "none" },
  compactFilters: { maxHeight: "40dvh", padding: "0 12px 14px" },
  filterControl: { width: "100%", minHeight: 44, border: "none", fontFamily: "inherit", textAlign: "left" },
  filterButton: sharedStyles.filterButton,
};

export default function Sidebar({
  isCompact,
  filtersOpen,
  onToggleFilters,
  view,
  onViewChange,
  sourceItems,
  selectedSource,
  onSourceClick,
}) {
  return (
    <aside style={{ ...s.sidebar, ...(isCompact ? s.compactSidebar : {}) }}>
      <div style={{ ...s.sidebarHeader, ...(isCompact ? s.compactHeader : {}) }}>
        <div style={s.sidebarBrand}>
          <div style={s.sidebarBrandIcon}>📰</div>
          <div>
            <div style={s.sidebarTitle}>뉴스 뷰어</div>
            <div style={s.sidebarSubtitle}>크롤링 뉴스 모아보기</div>
          </div>
        </div>
        {isCompact && (
          <button
            type="button"
            style={s.filterButton}
            aria-expanded={filtersOpen}
            aria-controls="news-filters"
            onClick={onToggleFilters}
          >
            {filtersOpen ? "필터 닫기" : "필터"}
          </button>
        )}
      </div>
      <div id="news-filters" hidden={isCompact && !filtersOpen} style={{ ...s.sidebarScroll, ...(isCompact ? s.compactFilters : {}) }}>
        <div style={s.sectionLabel}>보기</div>
        {VIEW_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={view === item.id}
            style={{ ...s.filterItem(view === item.id), ...s.filterControl }}
            onClick={() => onViewChange(item.id)}
          >
            {item.label}
          </button>
        ))}

        <div style={s.sectionLabel}>출처</div>
        {sourceItems.map((src) => (
          <button
            type="button"
            key={src.source}
            aria-pressed={selectedSource === src.source}
            onClick={() => onSourceClick(src.source)}
            style={{ ...s.filterItem(selectedSource === src.source), ...s.filterControl }}
          >
            <span>{src.source || "전체"}</span>
            <span style={s.filterCount(selectedSource === src.source)}>{src.count}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
