import { BORDER, TEXT_MUTED } from "../../styles/theme.js";
import { sharedStyles } from "../../styles/shared.js";

const s = {
  pagination: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: 12,
    padding: "16px 16px 20px",
    borderTop: `1px solid ${BORDER}`,
    background: "#ffffff",
  },
  pageBtn: (disabled) => ({
    padding: "6px 14px",
    borderRadius: 7,
    border: `1px solid ${BORDER}`,
    background: disabled ? "#f4f6f4" : "#ffffff",
    color: disabled ? TEXT_MUTED : "#28382c",
    cursor: disabled ? "default" : "pointer",
    fontSize: 12.5,
    fontWeight: 550,
    fontFamily: "inherit",
    transition: "background 0.15s, border-color 0.15s",
  }),
  pageInfo: {
    fontSize: 12.5,
    color: TEXT_MUTED,
    minWidth: 60,
    textAlign: "center",
    fontVariantNumeric: "tabular-nums",
  },
  touchButton: sharedStyles.touchButton,
};

export default function Pagination({ page, totalPages, onPageChange }) {
  return (
    <div style={s.pagination}>
      <button
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page === 1}
        style={{ ...s.pageBtn(page === 1), ...s.touchButton }}
      >
        이전
      </button>
      <span style={s.pageInfo}>{page} / {totalPages}</span>
      <button
        onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        disabled={page === totalPages}
        style={{ ...s.pageBtn(page === totalPages), ...s.touchButton }}
      >
        다음
      </button>
    </div>
  );
}
