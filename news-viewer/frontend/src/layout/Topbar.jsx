import { ACCENT, ACCENT_DARK, BORDER, TEXT_SECONDARY, TEXT_MUTED } from "../styles/theme.js";
import { sharedStyles } from "../styles/shared.js";

const s = {
  topbar: {
    minHeight: 64,
    padding: "12px 24px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#ffffff",
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "center",
    flexShrink: 0,
  },
  topbarTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "#334136",
    display: "flex",
    alignItems: "center",
    gap: 8,
    whiteSpace: "nowrap",
  },
  searchForm: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flex: "0 1 380px",
    maxWidth: "100%",
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    padding: "9px 14px",
    borderRadius: 8,
    border: `1px solid ${BORDER}`,
    fontSize: 14,
    background: "#f8faf8",
    color: "#16241a",
    transition: "border-color 0.15s, background-color 0.15s",
    fontFamily: "inherit",
  },
  searchBtn: {
    padding: "9px 18px",
    borderRadius: 8,
    background: ACCENT,
    color: "#ffffff",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 650,
    letterSpacing: "0.1px",
    flexShrink: 0,
    transition: "background 0.15s",
    fontFamily: "inherit",
  },
  compactTopbar: { padding: "10px 14px", gap: 8 },
  compactReadingHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 14px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#ffffff",
    minHeight: 52,
    gap: 12,
    flexShrink: 0,
  },
  compactReadingMeta: {
    fontSize: 13,
    color: TEXT_SECONDARY,
    fontWeight: 550,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  backButton: {
    minHeight: 44,
    minWidth: 44,
    padding: "8px 14px",
    border: `1px solid ${BORDER}`,
    borderRadius: 7,
    background: "#ffffff",
    color: ACCENT_DARK,
    font: "inherit",
    fontSize: 13.5,
    fontWeight: 650,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    flexShrink: 0,
  },
  touchButton: sharedStyles.touchButton,
};

// 좁은 화면에서 기사를 읽는 동안 상단에 표시하는 목록 복귀 헤더
export function ReadingHeader({ selected, onBack }) {
  return (
    <header style={s.compactReadingHeader}>
      <button
        type="button"
        style={s.backButton}
        onClick={onBack}
        aria-label="기사 목록으로 돌아가기"
      >
        ← 목록
      </button>
      <span style={s.compactReadingMeta}>
        {selected.source} · {selected.major_category}
      </span>
    </header>
  );
}

export default function Topbar({ isCompact, selected, view, selectedSource, query, onQueryChange, onSearchSubmit }) {
  return (
    <div style={{ ...s.topbar, ...(isCompact ? s.compactTopbar : {}), ...(isCompact && selected ? { display: "none" } : {}) }}>
      {!isCompact && (
        <div style={s.topbarTitle}>
          <span>{view === "briefing" ? "오늘의 AI 브리핑" : "기사 피드"}</span>
          {view === "articles" && selectedSource && (
            <span style={{ fontSize: 12, color: TEXT_MUTED, fontWeight: 400 }}>
              {`· ${selectedSource}`}
            </span>
          )}
        </div>
      )}
      <form onSubmit={onSearchSubmit} style={s.searchForm}>
        <input
          aria-label="기사 검색"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="기사 제목, 본문으로 검색..."
          style={s.searchInput}
        />
        <button
          type="submit"
          style={{ ...s.searchBtn, ...s.touchButton }}
        >
          검색
        </button>
      </form>
    </div>
  );
}
