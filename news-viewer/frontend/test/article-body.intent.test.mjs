import { fileURLToPath } from "node:url";
import { describe, test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

describe("기사 본문 정리·URL 안전화·렌더링 의도", () => {
  let vite;
  let ArticleBody;
  let cleanArticleText;
  let isSafeUrl;
  let safeUrlTransform;

  before(async () => {
    vite = await createServer({
      root: frontendRoot,
      server: { middlewareMode: true, ws: false },
      appType: "custom",
      optimizeDeps: { noDiscovery: true },
    });
    try {
      ({
        default: ArticleBody,
        cleanArticleText,
        isSafeUrl,
        safeUrlTransform,
      } = await vite.ssrLoadModule("/src/features/articles/ArticleBody.tsx"));
    } catch (error) {
      await vite.close();
      vite = undefined;
      throw error;
    }
  });

  after(async () => {
    if (vite) {
      await vite.close();
      vite = undefined;
    }
  });

  test("본문에서 '광고'가 포함된 줄을 제거하고 나머지 본문 줄은 유지한다", () => {
    const raw = "첫 번째 문장입니다.\n[광고] 특별 프로모션 안내\n두 번째 문장입니다.\n배너 광고 문의\n세 번째 문장입니다.";
    const cleaned = cleanArticleText(raw);

    assert.equal(cleaned, "첫 번째 문장입니다.\n두 번째 문장입니다.\n세 번째 문장입니다.");
  });

  test("연속된 빈 줄과 광고 제거로 생긴 여분의 빈 줄을 하나의 빈 줄로 축소한다", () => {
    const raw = "첫 문단\r\n\r\n\r\n\r\n둘째 문단   \r\n\r\n[광고] 중간 배너\r\n\r\n셋째 문단";
    const cleaned = cleanArticleText(raw);

    assert.equal(cleaned, "첫 문단\n\n둘째 문단\n\n셋째 문단");
  });

  test("본문이 비어 있거나 광고 줄만 있으면 빈 문자열을 반환한다", () => {
    assert.equal(cleanArticleText(""), "");
    assert.equal(cleanArticleText(null), "");
    assert.equal(cleanArticleText(undefined), "");
    assert.equal(cleanArticleText("[광고] 안내\n   \n광고"), "");
  });

  test("http, https, mailto, tel 프로토콜과 /, # 경로만 안전한 URL로 허용한다", () => {
    const allowedUrls = [
      "http://example.com/news",
      "https://example.com/news?id=1",
      "mailto:editor@example.com",
      "tel:02-1234-5678",
      "/articles/42",
      "//cdn.example.com/guide",
      "#section-1",
    ];

    for (const url of allowedUrls) {
      assert.equal(isSafeUrl(url), true, `${url} 은 허용되어야 한다`);
      assert.equal(safeUrlTransform(url), url, `${url} 은 그대로 유지되어야 한다`);
    }
  });

  test("javascript, data, vbscript 등 허용되지 않은 프로토콜·상대경로와 빈 값은 차단한다", () => {
    const blockedUrls = [
      "javascript:alert(1)",
      "JAVASCRIPT:alert(1)",
      "data:text/html,<script>alert(1)</script>",
      "vbscript:msgbox(1)",
      "ftp://example.com/file",
      "articles/1",
      "",
      "   ",
    ];

    for (const url of blockedUrls) {
      assert.equal(isSafeUrl(url), false, `${JSON.stringify(url)} 은 차단되어야 한다`);
      assert.equal(safeUrlTransform(url), "", `${JSON.stringify(url)} 은 빈 문자열로 변환되어야 한다`);
    }
    assert.equal(isSafeUrl(null), false);
    assert.equal(isSafeUrl(undefined), false);
  });

  test("정리된 본문이 비어 있으면 본문 없음 안내 문구를 렌더링한다", () => {
    for (const emptyContent of ["", null, "[광고] 만 있는 본문"]) {
      const html = renderToStaticMarkup(React.createElement(ArticleBody, { content: emptyContent }));
      assert.ok(html.includes("이 기사는 원문 본문을 가져오지 못했습니다."));
    }
  });

  test("위험한 링크는 클릭할 수 없는 텍스트로 표시하고 외부 링크는 새 창 속성으로 렌더링한다", () => {
    const markdown = [
      "[위험 링크](javascript:alert(1))",
      "[외부 링크](https://example.com/post)",
      "[프로토콜 상대 링크](//example.com/shared)",
      "[내부 경로](/articles/1)",
    ].join("\n\n");

    const html = renderToStaticMarkup(React.createElement(ArticleBody, { content: markdown }));

    assert.equal(html.includes("javascript:"), false);
    assert.match(html, /<span[^>]*>위험 링크<\/span>/);
    assert.match(
      html,
      /<a[^>]*href="https:\/\/example\.com\/post"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*>외부 링크<\/a>/,
    );
    assert.match(
      html,
      /<a[^>]*href="\/\/example\.com\/shared"[^>]*target="_blank"[^>]*rel="noopener noreferrer"[^>]*>프로토콜 상대 링크<\/a>/,
    );
    assert.match(html, /<a[^>]*href="\/articles\/1"[^>]*>내부 경로<\/a>/);
    assert.equal(/<a[^>]*href="\/articles\/1"[^>]*target="_blank"/.test(html), false);
  });

  test("허용되지 않은 이미지 URL은 빈 값으로 제거한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleBody, { content: "![위험 이미지](javascript:alert(1))" }),
    );

    assert.equal(html.includes("javascript:"), false);
    assert.ok(html.includes("<img"));
    assert.ok(!html.includes('src="javascript:'));
    assert.ok(html.includes('src=""') || !html.includes("src="));
  });
});
