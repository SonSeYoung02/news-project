import { ACCENT_DARK, BORDER, TEXT_MUTED } from "./theme.js";

// 여러 화면 파일이 함께 사용하는 인라인 스타일
export const sharedStyles = {
  filterButton: {
    minHeight: 44,
    padding: "8px 14px",
    border: `1px solid ${BORDER}`,
    borderRadius: 7,
    background: "#ffffff",
    color: ACCENT_DARK,
    font: "inherit",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
  error: { padding: "12px 16px", color: "#991b1b", background: "#fef2f2", fontSize: 13.5, flexShrink: 0, borderBottom: "1px solid #fee2e2" },
  statusText: {
    textAlign: "center",
    color: TEXT_MUTED,
    padding: "40px 16px",
    fontSize: 13.5,
  },
  touchButton: { minHeight: 44 },
  tagRow: {
    display: "flex",
    gap: 5,
    flexWrap: "wrap",
  },
  tag: {
    fontSize: 11,
    background: "#edf5ef",
    color: ACCENT_DARK,
    border: "1px solid #d5e5d8",
    padding: "2px 8px",
    borderRadius: 14,
    fontWeight: 500,
  },
};
