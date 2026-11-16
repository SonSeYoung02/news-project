import { ACCENT, ACCENT_DARK, BORDER, TEXT_SECONDARY, TEXT_MUTED } from "../../styles/theme.js";
import SourceMark from "../../components/SourceMark.jsx";
import { sharedStyles } from "../../styles/shared.js";
import { formatDate } from "../../utils/formatDate.js";

const s = {
  card: (selected) => ({
    width: "100%",
    textAlign: "left",
    fontFamily: "inherit",
    overflowWrap: "anywhere",
    padding: "16px 20px 15px",
    cursor: "pointer",
    background: selected ? "#edf5ef" : "#ffffff",
    border: "none",
    borderBottom: `1px solid ${BORDER}`,
    borderLeft: selected ? `3px solid ${ACCENT}` : "3px solid transparent",
    transition: "background 0.15s, border-left-color 0.15s",
    display: "block",
  }),
  cardMeta: {
    fontSize: 12,
    color: TEXT_MUTED,
    fontWeight: 500,
    marginBottom: 6,
    display: "flex",
    gap: 7,
    alignItems: "center",
    flexWrap: "wrap",
  },
  cardSourceName: {
    fontWeight: 650,
    color: "#2a3d2e",
  },
  cardCategory: {
    color: ACCENT_DARK,
    fontWeight: 550,
  },
  cardDate: {
    color: TEXT_MUTED,
  },
  cardDot: {
    width: 3,
    height: 3,
    borderRadius: "50%",
    background: "#98a69a",
    flexShrink: 0,
  },
  cardTitle: {
    fontSize: 14.5,
    fontWeight: 650,
    lineHeight: 1.45,
    marginBottom: 6,
    color: "#16241a",
  },
  cardSummary: {
    fontSize: 12.5,
    color: TEXT_SECONDARY,
    lineHeight: 1.55,
    marginBottom: 8,
  },
  tagRow: sharedStyles.tagRow,
  tag: sharedStyles.tag,
};

// 기사 목록·브리핑 목록이 함께 사용하는 기사 카드
export default function ArticleCard({ article: a, selected, onSelect }) {
  const previewText = a.summary || a.content;
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(a)}
      style={s.card(selected)}
    >
      <div style={s.cardMeta}>
        <SourceMark source={a.source} />
        <span style={s.cardSourceName}>{a.source}</span>
        <span style={s.cardDot} />
        <span style={s.cardCategory}>{a.major_category}</span>
        {a.published_at && (
          <>
            <span style={s.cardDot} />
            <span style={s.cardDate}>{formatDate(a.published_at)}</span>
          </>
        )}
      </div>
      <div style={s.cardTitle}>{a.title}</div>
      {previewText && (
        <div style={s.cardSummary}>
          {previewText.slice(0, 95)}{previewText.length > 95 ? "…" : ""}
        </div>
      )}
      {(a.tags || []).length > 0 && (
        <div style={s.tagRow}>
          {(a.tags || []).slice(0, 3).map((t) => (
            <span key={t} style={s.tag}>{t}</span>
          ))}
        </div>
      )}
    </button>
  );
}
