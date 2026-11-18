import { describe, expect, it } from "vitest";
import { formatArticlePreview, stripMarkdown } from "../../../../src/domains/article/model/articlePreview.ts";

describe("기사 카드 미리보기 Markdown 평문 변환", () => {
  it("제목 기호·강조·링크·목록·코드 펜스·인용구 등 Markdown 문법을 제거하고 공백을 정리한 평문을 반환한다", () => {
    const markdown = [
      "## 개요",
      "",
      "이 기사는 **중요한 강조**와 *기울임*, ~~취소선~~, [공식 링크](https://example.com/guide)를 다룹니다.",
      "",
      "- 첫 번째 목록 항목",
      "* 두 번째 목록 항목",
      "1. 순서 있는 항목",
      "",
      "```typescript",
      "const result = runAgent();",
      "```",
      "",
      "> 인용문과 `인라인 코드` 및 ![이미지 설명](https://example.com/img.png)",
    ].join("\n");

    expect(stripMarkdown(markdown)).toBe(
      "개요 이 기사는 중요한 강조와 기울임, 취소선, 공식 링크를 다룹니다. 첫 번째 목록 항목 두 번째 목록 항목 순서 있는 항목 const result = runAgent(); 인용문과 인라인 코드 및 이미지 설명",
    );
  });

  it("식별자의 밑줄(snake_case)이나 빈 입력·괄호가 포함된 링크 URL을 안전하게 처리한다", () => {
    expect(stripMarkdown("")).toBe("");
    expect(stripMarkdown(null)).toBe("");
    expect(stripMarkdown(undefined)).toBe("");
    expect(stripMarkdown("변수명 `my_snake_case` 와 my_other_var 그리고 _강조_")).toBe(
      "변수명 my_snake_case 와 my_other_var 그리고 강조",
    );
    expect(stripMarkdown("[위키](https://en.wikipedia.org/wiki/AI_(disambiguation)) 참고")).toBe(
      "위키 참고",
    );
  });

  it("미리보기 텍스트는 요약을 우선하고 요약이 없을 때만 본문에서 Markdown을 제거한 뒤 95자 초과 시 말줄임표로 자른다", () => {
    expect(formatArticlePreview("간결한 요약", "## 제목\n\n**본문**")).toBe("간결한 요약");

    const longMarkdown = `## 개요\n\n${"가".repeat(100)}`;
    expect(formatArticlePreview(null, longMarkdown)).toBe(`개요 ${"가".repeat(92)}…`);

    const exactMarkdown = `## ${"나".repeat(95)}`;
    expect(formatArticlePreview("", exactMarkdown)).toBe("나".repeat(95));
  });
});
