import { ACCENT, ACCENT_DARK, TEXT_SECONDARY, TEXT_MUTED } from "../../../shared/styles/theme.ts";
import { sharedStyles } from "../../../shared/styles/shared.ts";
import type { StyleMap } from "../../../shared/styles/shared.ts";
import SourceMark from "../../../shared/ui/SourceMark.tsx";
import { formatDate } from "../../../shared/utils/formatDate.ts";
import type { Article } from "../model/article.ts";
import type { DetailErrorKind } from "../model/routeState.ts";
import ArticleBody from "./ArticleBody.tsx";

const s = {
  readerContainer: {
    maxWidth: 780,
    width: "100%",
    margin: "0 auto",
    overflowWrap: "anywhere",
    wordBreak: "break-word",
  },
  detailPanel: {
    flex: 1,
    minWidth: 0,
    overflowY: "auto",
    padding: "36px 44px",
    background: "#ffffff",
  },
  detailEmpty: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    alignItems: "center",
    justifyContent: "center",
    color: TEXT_MUTED,
    textAlign: "center",
    padding: "32px",
  },
  detailEmptyMessage: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    lineHeight: 1.6,
  },
  detailEmptyActions: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexWrap: "wrap",
    gap: 8,
  },
  secondaryActionButton: sharedStyles.filterButton,
  primaryActionButton: {
    ...sharedStyles.filterButton,
    background: ACCENT,
    border: `1px solid ${ACCENT}`,
    color: "#ffffff",
  },
  detailMeta: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    fontSize: 13,
    color: ACCENT_DARK,
    fontWeight: 600,
    marginBottom: 12,
    flexWrap: "wrap",
  },
  detailTitle: {
    fontSize: 25,
    fontWeight: 750,
    lineHeight: 1.35,
    marginBottom: 14,
    color: "#142217",
    letterSpacing: "-0.02em",
    overflowWrap: "anywhere",
    wordBreak: "break-word",
  },
  detailDate: {
    fontSize: 12.5,
    color: TEXT_MUTED,
    marginBottom: 24,
    display: "flex",
    gap: 8,
    alignItems: "center",
  },
  detailLink: {
    color: ACCENT_DARK,
    textDecoration: "none",
    fontWeight: 550,
    display: "inline-flex",
    alignItems: "center",
    gap: 3,
  },
  summaryBox: {
    background: "#f4f8f4",
    border: "1px solid #d5e5d8",
    borderLeft: `4px solid ${ACCENT}`,
    borderRadius: 8,
    padding: "16px 20px",
    marginBottom: 28,
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: ACCENT_DARK,
    textTransform: "uppercase",
    letterSpacing: "0.6px",
    marginBottom: 8,
  },
  summaryText: {
    fontSize: 14.5,
    lineHeight: 1.75,
    color: "#28382c",
  },
  detailContent: {
    fontSize: 17,
    lineHeight: 1.82,
    color: "#28382c",
    whiteSpace: "pre-wrap",
    marginBottom: 32,
    overflowWrap: "anywhere",
    wordBreak: "break-word",
  },
  compactDetail: { width: "100%", padding: "20px 16px", flex: 1 },
  compactDetailTitle: { fontSize: 21, lineHeight: 1.35 },
  tagRow: sharedStyles.tagRow,
  tag: sharedStyles.tag,
} satisfies StyleMap;

// 선택된 기사의 상세 영역. 선택된 기사가 없으면 emptyMessage를 보여준다.
interface ArticleDetailProps {
  selected: Article | null;
  isCompact: boolean;
  emptyMessage: string;
  forceShowOnCompact?: boolean;
  errorKind?: DetailErrorKind;
  onBackToList?: () => void;
  onRetry?: () => void;
}

export default function ArticleDetail({
  selected,
  isCompact,
  emptyMessage,
  forceShowOnCompact = false,
  errorKind = "none",
  onBackToList,
  onRetry,
}: ArticleDetailProps) {
  const showPanel = !isCompact || Boolean(selected) || forceShowOnCompact;
  const showRecoveryActions = errorKind === "not_found" || errorKind === "error";
  return (
    <div
      aria-label="기사 상세"
      style={{
        ...s.detailPanel,
        ...(isCompact ? s.compactDetail : {}),
        ...(!showPanel ? { display: "none" } : {}),
      }}
    >
      {!selected ? (
        <div style={s.detailEmpty}>
          <span style={s.detailEmptyMessage}>
            {emptyMessage}
          </span>
          {showRecoveryActions && (onBackToList || (errorKind === "error" && onRetry)) && (
            <div style={s.detailEmptyActions}>
              {errorKind === "error" && onRetry && (
                <button
                  type="button"
                  style={s.primaryActionButton}
                  onClick={onRetry}
                >
                  다시 시도
                </button>
              )}
              {onBackToList && (
                <button
                  type="button"
                  style={s.secondaryActionButton}
                  onClick={onBackToList}
                >
                  목록으로 돌아가기
                </button>
              )}
            </div>
          )}
        </div>
      ) : (
        <div style={s.readerContainer}>
          <div style={s.detailMeta}>
            <SourceMark source={selected.source} size={20} />
            <span>{selected.source}</span>
            <span>·</span>
            <span>{selected.major_category}</span>
            {selected.sub_category && (
              <>
                <span>·</span>
                <span style={{ color: TEXT_SECONDARY }}>{selected.sub_category}</span>
              </>
            )}
          </div>
          <h1 style={{ ...s.detailTitle, ...(isCompact ? s.compactDetailTitle : {}) }}>{selected.title}</h1>
          <div style={s.detailDate}>
            <span>{formatDate(selected.published_at) || selected.published_at?.slice(0, 10)}</span>
            {selected.url && (
              <>
                <span>·</span>
                <a href={selected.url} target="_blank" rel="noreferrer" style={s.detailLink}>
                  원문 보기 ↗
                </a>
              </>
            )}
          </div>
          {selected.summary && (
            <div style={s.summaryBox}>
              <div style={s.summaryLabel}>LLM 분석</div>
              <div style={s.summaryText}>{selected.summary}</div>
            </div>
          )}
          <ArticleBody content={selected.content} style={s.detailContent} />
          {(selected.tags || []).length > 0 && (
            <div style={s.tagRow}>
              {(selected.tags || []).map((t) => (
                <span key={t} style={{ ...s.tag, fontSize: 12, padding: "4px 12px" }}>{t}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
