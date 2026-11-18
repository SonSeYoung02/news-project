import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ArticleCard from "../../../../src/domains/article/ui/ArticleCard.tsx";
import { createMockArticle } from "../../../helpers/mockApi.ts";

describe("기사 카드 미리보기 렌더링", () => {
  it("요약이 없으면 본문의 Markdown 문법을 제거한 평문 미리보기를 표시한다", () => {
    const markdownContent = [
      "## 개요",
      "",
      "**핵심 기술**과 [자세한 링크](https://example.com)를 정리했습니다.",
      "- 항목 A",
      "```js",
      "console.log('ok');",
      "```",
    ].join("\n");

    render(
      <ArticleCard
        article={createMockArticle({
          summary: null,
          content: markdownContent,
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );

    expect(
      screen.getByText("개요 핵심 기술과 자세한 링크를 정리했습니다. 항목 A console.log('ok');"),
    ).toBeInTheDocument();
  });

  it("요약이 있으면 본문 대신 요약을 미리보기로 사용하고 95자 초과 시 말줄임표를 붙인다", () => {
    render(
      <ArticleCard
        article={createMockArticle({
          summary: "가".repeat(96),
          content: "## 본문은 표시되지 않음",
        })}
        selected={false}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText(`${"가".repeat(95)}…`)).toBeInTheDocument();
  });
});
