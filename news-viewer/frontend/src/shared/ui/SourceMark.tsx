// 출처별 [약어, 글자색, 배경색]
const SOURCE_MARKS: Record<string, [label: string, color: string, background: string]> = {
  "네이버뉴스": ["N", "#1b874b", "#edf7ef"],
  "Google News": ["G", "#34629e", "#edf3fc"],
  GeekNews: ["GN", "#9e5c2c", "#fcf3ec"],
  "Reddit AI": ["R", "#b35732", "#fcf1ec"],
  "GitHub Trending": ["GH", "#36413a", "#edf1ee"],
  "Hugging Face": ["HF", "#8a6a20", "#fdf8e8"],
  arXiv: ["aX", "#9c4040", "#fdf0f0"],
  "dev.to": ["d", "#3f4c45", "#edf1ee"],
};

interface SourceMarkProps {
  source: string;
  size?: number;
}

export default function SourceMark({ source, size = 18 }: SourceMarkProps) {
  const [label, color, background] = SOURCE_MARKS[source] || [source?.slice(0, 2) || "뉴스", "#455348", "#edf1ee"];
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        borderRadius: 4,
        fontSize: size <= 18 ? 9 : 10,
        lineHeight: 1,
        fontWeight: 700,
        color,
        background,
        flexShrink: 0,
        letterSpacing: "-0.3px",
      }}
    >
      {label}
    </span>
  );
}
