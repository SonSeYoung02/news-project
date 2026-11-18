import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ArticleBody, {
  cleanArticleText,
  isSafeUrl,
  safeUrlTransform,
} from "../../../../src/domains/article/ui/ArticleBody.tsx";

describe("기사 본문 정제 및 안전한 마크다운 렌더링", () => {
  it("본문에서 광고가 포함된 줄을 제거하고 문단 구분과 줄바꿈은 유지한다", () => {
    const adText =
      "첫 번째 줄\n[광고] 이벤트 안내\n두 번째 줄\n\n새로운 문단\n광고 문의: 02-1234\n마지막 줄";
    const cleaned = cleanArticleText(adText);

    expect(cleaned).not.toContain("광고");
    expect(cleaned).toBe("첫 번째 줄\n두 번째 줄\n\n새로운 문단\n마지막 줄");

    const collapsed = cleanArticleText("첫 문단\r\n\r\n\r\n\r\n둘째 문단   \r\n\r\n[광고] 배너\r\n\r\n셋째 문단");
    expect(collapsed).toBe("첫 문단\n\n둘째 문단\n\n셋째 문단");

    expect(cleanArticleText("")).toBe("");
    expect(cleanArticleText(null)).toBe("");
    expect(cleanArticleText(undefined)).toBe("");
    expect(cleanArticleText("[광고] 안내\n   \n광고")).toBe("");
  });

  it("허용된 URL 스킴(http, https, mailto, tel, /, #)만 통과시키고 javascript·data·vbscript 스킴은 차단한다", () => {
    const allowedUrls = [
      "https://news.ycombinator.com",
      "http://example.com",
      "mailto:editor@news.com",
      "tel:02-1234-5678",
      "/articles/10",
      "//cdn.example.com/guide",
      "#section-1",
    ];
    for (const url of allowedUrls) {
      expect(isSafeUrl(url)).toBe(true);
      expect(safeUrlTransform(url)).toBe(url);
    }

    const blockedUrls = [
      "javascript:alert(document.cookie)",
      "JAVASCRIPT:alert(1)",
      "data:text/html,<script>alert(1)</script>",
      "vbscript:msgbox(1)",
      "ftp://example.com/file",
      "articles/1",
      "",
      "   ",
    ];
    for (const url of blockedUrls) {
      expect(isSafeUrl(url)).toBe(false);
      expect(safeUrlTransform(url)).toBe("");
    }
    expect(isSafeUrl(null)).toBe(false);
    expect(isSafeUrl(undefined)).toBe(false);
  });

  it("본문 내 원시 HTML 태그(<script>, <img>)와 악성 마크다운 링크·이미지를 실행 불가능하게 무력화한다", () => {
    const xssContent = "본문 내용 <script>alert('xss')</script> <img src=x onerror=alert(1)> <b>태그</b>";
    const { container, rerender } = render(<ArticleBody content={xssContent} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>alert('xss')</script>");
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");

    const unsafeLinks = "[악성 링크](javascript:alert(1))\n[데이터 링크](data:text/html,abc)";
    rerender(<ArticleBody content={unsafeLinks} />);

    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("javascript:");
    expect(container.innerHTML).not.toContain("data:");
    expect(screen.getByText("악성 링크").tagName).toBe("SPAN");
    expect(screen.getByText("데이터 링크").tagName).toBe("SPAN");

    rerender(<ArticleBody content="![악성 이미지](javascript:alert(1))" />);
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src") ?? "").not.toContain("javascript:");
  });

  it("마크다운 제목·강조·인용구·목록·코드블록을 렌더링하고 외부 링크는 새 창(noopener noreferrer)으로 연다", () => {
    const mdContent = [
      "# 제목 1",
      "## 제목 2",
      "**굵게** 및 *기울임*, `inline code`",
      "> 인용구",
      "- 목록 1\n- 목록 2",
      "```python\nprint('code')\n```",
      "[안전 링크](https://example.com)",
      "[프로토콜 상대 링크](//example.com/shared)",
      "[내부 경로](/articles/1)",
    ].join("\n\n");

    const { container } = render(<ArticleBody content={mdContent} />);

    expect(screen.getByRole("heading", { level: 1, name: "제목 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "제목 2" })).toBeInTheDocument();
    expect(screen.getByText("굵게").tagName).toBe("STRONG");
    expect(screen.getByText("기울임").tagName).toBe("EM");
    expect(container.querySelector("blockquote")).toHaveTextContent("인용구");

    const listItems = container.querySelectorAll("ul > li");
    expect(listItems).toHaveLength(2);
    expect(container.querySelector("pre > code")).toHaveTextContent("print('code')");
    expect(screen.getByText("inline code").tagName).toBe("CODE");

    const externalLink = screen.getByRole("link", { name: "안전 링크" });
    expect(externalLink).toHaveAttribute("href", "https://example.com");
    expect(externalLink).toHaveAttribute("target", "_blank");
    expect(externalLink).toHaveAttribute("rel", "noopener noreferrer");

    const protocolRelativeLink = screen.getByRole("link", { name: "프로토콜 상대 링크" });
    expect(protocolRelativeLink).toHaveAttribute("href", "//example.com/shared");
    expect(protocolRelativeLink).toHaveAttribute("target", "_blank");
    expect(protocolRelativeLink).toHaveAttribute("rel", "noopener noreferrer");

    const internalLink = screen.getByRole("link", { name: "내부 경로" });
    expect(internalLink).toHaveAttribute("href", "/articles/1");
    expect(internalLink).not.toHaveAttribute("target", "_blank");
  });

  it("일반 텍스트의 단일 줄바꿈(<br>)과 빈 줄 문단 구분(<p>)을 유지한다", () => {
    const plainText = "국방부가 ... 파견했습니다.\n국방부는 ... 말했습니다.\n\n기술분석팀은 ... 구성됐습니다.";
    const { container } = render(<ArticleBody content={plainText} />);

    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.querySelector("br")).toBeInTheDocument();
  });

  it("마크다운 이미지는 화면 넘침 방지를 위해 max-width: 100%, height: auto, loading=lazy 속성을 가진다", () => {
    const imgContent =
      "![매우 긴 대체 텍스트가 들어간 이미지 설명으로 화면을 넘치지 않아야 하는 케이스입니다](https://images.unsplash.com/photo-1500000000?w=4000)";
    render(<ArticleBody content={imgContent} />);

    const img = screen.getByRole("img", {
      name: "매우 긴 대체 텍스트가 들어간 이미지 설명으로 화면을 넘치지 않아야 하는 케이스입니다",
    });
    expect(img).toHaveAttribute("loading", "lazy");
    expect(img).toHaveStyle({ "max-width": "100%", height: "auto" });
  });

  it("부모로부터 전달된 타이포그래피 스타일(fontSize, lineHeight, color)을 문단과 목록에 상속하고 whiteSpace는 normal로 정규화한다", () => {
    const issue38Style = {
      fontSize: 17,
      lineHeight: 1.82,
      color: "#1f2937",
      whiteSpace: "pre-wrap",
      marginBottom: 28,
    } as const;

    const { container } = render(
      <ArticleBody content={"38번 이슈에서 전달된 문단입니다.\n\n- 목록 항목 1"} style={issue38Style} />,
    );

    const rootContainer = container.firstElementChild as HTMLElement;
    expect(rootContainer).toHaveStyle({ "white-space": "normal" });

    const paragraph = screen.getByText("38번 이슈에서 전달된 문단입니다.");
    expect(paragraph).toHaveStyle({
      "font-size": "17px",
      color: "#1f2937",
    });
    expect(paragraph.style.lineHeight).toBe("1.82");

    const listItem = screen.getByText("목록 항목 1");
    expect(listItem).toHaveStyle({
      "font-size": "17px",
      color: "#1f2937",
    });
    expect(listItem.style.lineHeight).toBe("1.82");
  });

  it("정제된 본문이 비어 있으면 안내 문구를 본문 색상(color: inherit)으로 표시한다", () => {
    const baselineStyle = {
      fontSize: 15,
      lineHeight: 1.85,
      color: "#374151",
      whiteSpace: "pre-wrap",
      marginBottom: 28,
    } as const;

    const { container, rerender } = render(<ArticleBody content="" style={baselineStyle} />);
    for (const emptyInput of ["", null, "[광고] 만 있는 본문"]) {
      rerender(<ArticleBody content={emptyInput} style={baselineStyle} />);
      const fallback = screen.getByText("이 기사는 원문 본문을 가져오지 못했습니다.");
      expect(fallback).toBeInTheDocument();
      expect(fallback.style.color).toBe("inherit");
      expect(container.innerHTML).not.toContain("#9ca3af");
    }
  });
});
