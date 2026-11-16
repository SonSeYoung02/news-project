import { BORDER, TEXT_SECONDARY } from "../../styles/theme.js";
import { sharedStyles } from "../../styles/shared.js";
import ArticleCard from "../articles/ArticleCard.jsx";

const s = {
  briefingHeader: {
    padding: "24px 20px 20px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#f4f8f4",
  },
  briefingTitle: {
    margin: "0 0 8px",
    fontSize: 19,
    fontWeight: 750,
    color: "#16241a",
    letterSpacing: "-0.3px",
  },
  briefingDescription: {
    margin: "0 0 8px",
    fontSize: 12.5,
    lineHeight: 1.6,
    color: TEXT_SECONDARY,
  },
  statusText: sharedStyles.statusText,
  error: sharedStyles.error,
  filterButton: sharedStyles.filterButton,
};

// 오늘의 AI 브리핑 보기의 목록 영역: 안내·새로고침, 로딩·오류·빈 상태, 브리핑 기사 카드
export default function BriefingList({ briefing, briefingLoading, briefingError, onRetry, selectedId, onSelectArticle }) {
  return (
    <>
      <section aria-label="오늘의 AI 브리핑" style={s.briefingHeader}>
        <h2 style={s.briefingTitle}>오늘의 AI 브리핑</h2>
        <p style={s.briefingDescription}>최근 24시간의 AI 소식 최대 5개를 모았습니다.</p>
        <p style={s.briefingDescription}>주제·출처 다양성과 최신순을 반영한 선정입니다.</p>
        {briefing && (
          <p style={s.briefingDescription}>
            조회 시각: {new Date(briefing.generated_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)
          </p>
        )}
        <button
          type="button"
          style={s.filterButton}
          disabled={briefingLoading}
          onClick={onRetry}
        >
          새로고침
        </button>
      </section>

      {briefingLoading && (
        <div role="status" style={s.statusText}>브리핑을 불러오는 중...</div>
      )}
      {briefingError && (
        <div role="alert" style={s.error}>
          {briefingError}{" "}
          <button type="button" style={s.filterButton} onClick={onRetry}>
            다시 시도
          </button>
        </div>
      )}
      {!briefingLoading && !briefingError && (briefing?.articles || []).length === 0 && (
        <div style={s.statusText}>최근 24시간에 수집된 AI 기사가 없습니다.</div>
      )}

      {(!briefingLoading && !briefingError ? briefing?.articles || [] : []).map((a) => (
        <ArticleCard key={a.id} article={a} selected={selectedId === a.id} onSelect={onSelectArticle} />
      ))}
    </>
  );
}
