const PREVIEW_MAX_LENGTH = 95;

// 카드 미리보기용으로 Markdown 문법을 제거하고 공백을 정리한 평문을 생성한다.
export function stripMarkdown(text: string | null | undefined): string {
  if (!text) return "";

  return text
    .replace(/\r\n?/g, "\n")
    .replace(/^[ \t]{0,3}(?:`{3,}|~{3,})[^\n]*$/gm, "")
    .replace(/^[ \t]{0,3}\[[^\]]+\]:[ \t]*\S+.*$/gm, "")
    .replace(/!\[([^\]]*)\]\((?:[^()\n]+|\([^()\n]*\))*\)/g, "$1")
    .replace(/\[([^\]]+)\]\((?:[^()\n]+|\([^()\n]*\))*\)/g, "$1")
    .replace(/\[([^\]]+)\]\[[^\]]*\]/g, "$1")
    .replace(/^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/gm, "")
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+[ \t]*)?$/gm, "$1")
    .replace(/^[ \t]{0,3}(?:>[ \t]?)+/gm, "")
    .replace(/^[ \t]*[-*+][ \t]+(?:\[[ xX]\][ \t]+)?/gm, "")
    .replace(/^[ \t]*\d+[.)][ \t]+/gm, "")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/`+/g, "")
    .replace(/\*\*\*([^*\s](?:[^*\n]*?[^*\s])?)\*\*\*/g, "$1")
    .replace(/___([^_\s](?:[^_\n]*?[^_\s])?)___/g, "$1")
    .replace(/\*\*([^*\s](?:[^*\n]*?[^*\s])?)\*\*/g, "$1")
    .replace(/__([^_\s](?:[^_\n]*?[^_\s])?)__/g, "$1")
    .replace(/~~([^~\s](?:[^~\n]*?[^~\s])?)~~/g, "$1")
    .replace(/\*([^*\s](?:[^*\n]*?[^*\s])?)\*/g, "$1")
    .replace(/(?<![\p{L}\p{N}_])_([^_\s](?:[^_\n]*?[^_\s])?)_(?![\p{L}\p{N}_])/gu, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export function formatArticlePreview(
  summary: string | null | undefined,
  content: string | null | undefined,
  maxLength = PREVIEW_MAX_LENGTH,
): string {
  const previewText = summary?.trim() ? summary : stripMarkdown(content);
  if (!previewText) return "";
  return previewText.length > maxLength ? `${previewText.slice(0, maxLength)}…` : previewText;
}
