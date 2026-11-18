import { fileURLToPath } from "node:url";
import { describe, test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const frontendRoot = fileURLToPath(new URL("../..", import.meta.url));

function makeArticle(overrides = {}) {
  return {
    id: 1,
    url: "https://example.com/articles/1",
    source: "GeekNews",
    title: "AI 에이전트 테스트 기사",
    content: "기사 원문 내용입니다.",
    published_at: "2026-05-14T12:00:00Z",
    crawled_at: "2026-05-14T12:10:00Z",
    summary: "핵심 요약입니다.",
    major_category: "AI",
    sub_category: "에이전트",
    tags: ["AI", "Agent", "LLM"],
    original_title: null,
    original_content: null,
    translated_title: null,
    translated_content: null,
    translation_status: null,
    ...overrides,
  };
}

function matchButtonTag(html, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return html.match(new RegExp(`<button\\b[^>]*>${escaped}<\\/button>`));
}

function hasButton(html, label) {
  return Boolean(matchButtonTag(html, label));
}

function getButtonTag(html, label) {
  const match = matchButtonTag(html, label);
  assert.ok(match, `'${label}' 버튼을 렌더링해야 한다`);
  return match[0];
}

function isButtonDisabled(html, label) {
  return /\bdisabled(?:=""|\s|>)/.test(getButtonTag(html, label));
}

describe("출처 목록 및 viewer-ui 컴포넌트 렌더링 의도", () => {
  let vite;
  let SOURCE_FILTERS;
  let buildSourceItems;
  let ArticleList;
  let Pagination;
  let BriefingList;
  let ArticleDetail;
  let ArticleCard;
  let Sidebar;
  let Topbar;
  let ReadingHeader;

  before(async () => {
    vite = await createServer({
      root: frontendRoot,
      server: { middlewareMode: true, ws: false },
      appType: "custom",
      optimizeDeps: { noDiscovery: true },
    });
    try {
      ({ SOURCE_FILTERS, buildSourceItems } = await vite.ssrLoadModule("/src/domains/article/model/sourceFilters.ts"));
      ({ default: ArticleList } = await vite.ssrLoadModule("/src/domains/article/ui/ArticleList.tsx"));
      ({ default: Pagination } = await vite.ssrLoadModule("/src/domains/article/ui/Pagination.tsx"));
      ({ default: BriefingList } = await vite.ssrLoadModule("/src/domains/briefing/ui/BriefingList.tsx"));
      ({ default: ArticleDetail } = await vite.ssrLoadModule("/src/domains/article/ui/ArticleDetail.tsx"));
      ({ default: ArticleCard } = await vite.ssrLoadModule("/src/domains/article/ui/ArticleCard.tsx"));
      ({ default: Sidebar } = await vite.ssrLoadModule("/src/app/layout/Sidebar.tsx"));
      ({ default: Topbar, ReadingHeader } = await vite.ssrLoadModule("/src/app/layout/Topbar.tsx"));
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

  test("고정 출처 목록(SOURCE_FILTERS)은 명세에 정의된 7개 출처와 순서를 따른다", () => {
    assert.deepEqual(SOURCE_FILTERS, [
      "네이버뉴스",
      "Google News",
      "GeekNews",
      "GitHub Trending",
      "Hugging Face",
      "arXiv",
      "dev.to",
    ]);
  });

  test("사이드바에 Reddit AI가 표시되지 않는다", () => {
    const sourceItems = buildSourceItems(
      [
        { source: "Reddit AI", count: 2 },
        { source: "GeekNews", count: 4 },
      ],
      6,
    );
    const html = renderToStaticMarkup(
      React.createElement(Sidebar, {
        isCompact: false,
        filtersOpen: false,
        onToggleFilters: () => {},
        view: "briefing",
        onViewChange: () => {},
        sourceItems,
        selectedSource: "",
        onSourceClick: () => {},
      }),
    );

    assert.ok(html.includes("GeekNews"));
    assert.equal(html.includes("Reddit AI"), false);
  });

  test("ArticleList는 검색 결과가 없을 때 검색어 안내 문구와 검색어 초기화 버튼을 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleList, {
        articles: [],
        loading: false,
        error: "",
        search: "에이전트",
        selectedSource: "",
        selectedId: undefined,
        onSelectArticle: () => {},
        onRemoveSource: () => {},
        onResetFilters: () => {},
        onResetSearch: () => {},
        page: 1,
        totalPages: 0,
        onPageChange: () => {},
      }),
    );

    assert.ok(html.includes("‘에이전트’에 대한 검색 결과가 없습니다"));
    assert.ok(html.includes("단어의 철자가 정확한지 확인하거나 다른 검색어로 검색해 보세요."));
    getButtonTag(html, "검색어 초기화");
    assert.equal(html.includes("기사가 없습니다"), false);
  });

  test("ArticleList는 검색어 없이 기사가 비어 있으면 '기사가 없습니다'를 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleList, {
        articles: [],
        loading: false,
        error: "",
        search: "",
        selectedSource: "",
        selectedId: undefined,
        onSelectArticle: () => {},
        onRemoveSource: () => {},
        onResetFilters: () => {},
        onResetSearch: () => {},
        page: 1,
        totalPages: 0,
        onPageChange: () => {},
      }),
    );

    assert.ok(html.includes("기사가 없습니다"));
    assert.equal(html.includes("검색어 초기화"), false);
  });

  test("ArticleList는 출처 필터가 적용되면 활성 필터 배지와 초기화 버튼을 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleList, {
        articles: [makeArticle()],
        loading: false,
        error: "",
        search: "",
        selectedSource: "GeekNews",
        selectedId: 1,
        onSelectArticle: () => {},
        onRemoveSource: () => {},
        onResetFilters: () => {},
        onResetSearch: () => {},
        page: 1,
        totalPages: 1,
        onPageChange: () => {},
      }),
    );

    assert.ok(html.includes("적용된 필터:"));
    assert.ok(html.includes("출처: GeekNews"));
    getButtonTag(html, "필터 초기화");
  });

  test("ArticleList는 로딩 중일 때 '불러오는 중...'을 표시하고 기사 카드는 숨긴다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleList, {
        articles: [makeArticle({ title: "숨겨져야 할 기사" })],
        loading: true,
        error: "",
        search: "",
        selectedSource: "",
        selectedId: undefined,
        onSelectArticle: () => {},
        onRemoveSource: () => {},
        onResetFilters: () => {},
        onResetSearch: () => {},
        page: 1,
        totalPages: 1,
        onPageChange: () => {},
      }),
    );

    assert.ok(html.includes("불러오는 중..."));
    assert.equal(html.includes("숨겨져야 할 기사"), false);
    assert.equal(html.includes("기사가 없습니다"), false);
  });

  test("ArticleList는 전체 페이지 수가 1 이하이면 페이지네이션을 표시하지 않고 2 이상이면 표시한다", () => {
    for (const totalPages of [0, 1]) {
      const html = renderToStaticMarkup(
        React.createElement(ArticleList, {
          articles: totalPages === 0 ? [] : [makeArticle()],
          loading: false,
          error: "",
          search: "",
          selectedSource: "",
          selectedId: totalPages === 0 ? undefined : 1,
          onSelectArticle: () => {},
          onRemoveSource: () => {},
          onResetFilters: () => {},
          onResetSearch: () => {},
          page: 1,
          totalPages,
          onPageChange: () => {},
        }),
      );
      assert.equal(hasButton(html, "이전"), false);
      assert.equal(hasButton(html, "다음"), false);
      assert.equal(html.includes(`1 / ${totalPages}`), false);
    }

    const multiPageHtml = renderToStaticMarkup(
      React.createElement(ArticleList, {
        articles: [makeArticle()],
        loading: false,
        error: "",
        search: "",
        selectedSource: "",
        selectedId: 1,
        onSelectArticle: () => {},
        onRemoveSource: () => {},
        onResetFilters: () => {},
        onResetSearch: () => {},
        page: 2,
        totalPages: 3,
        onPageChange: () => {},
      }),
    );
    assert.ok(multiPageHtml.includes("2 / 3"));
    getButtonTag(multiPageHtml, "이전");
    getButtonTag(multiPageHtml, "다음");
  });

  test("Pagination은 '<현재> / <전체>'를 표시하고 첫·마지막 페이지에 따라 이전·다음 버튼을 비활성화한다", () => {
    const firstPageHtml = renderToStaticMarkup(
      React.createElement(Pagination, { page: 1, totalPages: 4, onPageChange: () => {} }),
    );
    assert.ok(firstPageHtml.includes("1 / 4"));
    assert.equal(isButtonDisabled(firstPageHtml, "이전"), true);
    assert.equal(isButtonDisabled(firstPageHtml, "다음"), false);

    const middlePageHtml = renderToStaticMarkup(
      React.createElement(Pagination, { page: 2, totalPages: 4, onPageChange: () => {} }),
    );
    assert.ok(middlePageHtml.includes("2 / 4"));
    assert.equal(isButtonDisabled(middlePageHtml, "이전"), false);
    assert.equal(isButtonDisabled(middlePageHtml, "다음"), false);

    const lastPageHtml = renderToStaticMarkup(
      React.createElement(Pagination, { page: 4, totalPages: 4, onPageChange: () => {} }),
    );
    assert.ok(lastPageHtml.includes("4 / 4"));
    assert.equal(isButtonDisabled(lastPageHtml, "이전"), false);
    assert.equal(isButtonDisabled(lastPageHtml, "다음"), true);
  });

  test("BriefingList는 로딩 중일 때 안내 문구와 비활성화된 새로고침 버튼을 표시하고 카드를 비운다", () => {
    const html = renderToStaticMarkup(
      React.createElement(BriefingList, {
        briefing: {
          generated_at: "2026-05-14T12:00:00Z",
          window_start: "2026-05-13T12:00:00Z",
          window_end: "2026-05-14T12:00:00Z",
          selection_method: "hybrid",
          articles: [makeArticle({ title: "로딩 중에는 숨겨질 브리핑 기사" })],
        },
        briefingLoading: true,
        briefingError: "",
        onRetry: () => {},
        selectedId: undefined,
        onSelectArticle: () => {},
      }),
    );

    assert.ok(html.includes("브리핑을 불러오는 중..."));
    assert.equal(isButtonDisabled(html, "새로고침"), true);
    assert.equal(html.includes("로딩 중에는 숨겨질 브리핑 기사"), false);
  });

  test("BriefingList는 조회 실패 시 오류 문구와 다시 시도 버튼을 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(BriefingList, {
        briefing: null,
        briefingLoading: false,
        briefingError: "브리핑을 불러오지 못했습니다.",
        onRetry: () => {},
        selectedId: undefined,
        onSelectArticle: () => {},
      }),
    );

    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes("브리핑을 불러오지 못했습니다."));
    getButtonTag(html, "다시 시도");
    assert.equal(html.includes("최근 24시간에 수집된 AI 기사가 없습니다."), false);
  });

  test("BriefingList는 브리핑 기사가 비어 있으면 빈 상태 문구를 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(BriefingList, {
        briefing: {
          generated_at: "2026-05-14T12:00:00Z",
          window_start: "2026-05-13T12:00:00Z",
          window_end: "2026-05-14T12:00:00Z",
          selection_method: "hybrid",
          articles: [],
        },
        briefingLoading: false,
        briefingError: "",
        onRetry: () => {},
        selectedId: undefined,
        onSelectArticle: () => {},
      }),
    );

    assert.ok(html.includes("최근 24시간에 수집된 AI 기사가 없습니다."));
  });

  test("BriefingList는 조회 완료 시 한국 시간 조회 시각과 브리핑 기사 카드를 표시한다", () => {
    const generatedAt = "2026-05-14T12:00:00Z";
    const expectedTime = new Date(generatedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
    const html = renderToStaticMarkup(
      React.createElement(BriefingList, {
        briefing: {
          generated_at: generatedAt,
          window_start: "2026-05-13T12:00:00Z",
          window_end: generatedAt,
          selection_method: "hybrid",
          articles: [makeArticle({ id: 7, title: "오늘의 주요 AI 브리핑 기사" })],
        },
        briefingLoading: false,
        briefingError: "",
        onRetry: () => {},
        selectedId: 7,
        onSelectArticle: () => {},
      }),
    );

    assert.ok(html.includes("오늘의 AI 브리핑"));
    assert.ok(html.includes(`조회 시각: ${expectedTime} (한국 시간)`));
    assert.ok(html.includes("오늘의 주요 AI 브리핑 기사"));
    assert.ok(html.includes('aria-pressed="true"'));
    assert.equal(isButtonDisabled(html, "새로고침"), false);
  });

  test("ArticleDetail은 선택된 기사가 없으면 emptyMessage를 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleDetail, {
        selected: null,
        isCompact: false,
        emptyMessage: "기사를 선택하세요",
      }),
    );

    assert.ok(html.includes("기사를 선택하세요"));
    assert.equal(html.includes("LLM 분석"), false);
  });

  test("ArticleDetail은 요약이 있으면 LLM 분석 박스, 원문 보기 링크, 전체 태그를 표시한다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleDetail, {
        selected: makeArticle({
          summary: "이 기사의 LLM 요약입니다.",
          sub_category: "추론 모델",
          url: "https://example.com/original",
          tags: ["태그1", "태그2", "태그3", "태그4"],
        }),
        isCompact: false,
        emptyMessage: "기사를 선택하세요",
      }),
    );

    assert.ok(html.includes("LLM 분석"));
    assert.ok(html.includes("이 기사의 LLM 요약입니다."));
    assert.ok(html.includes("추론 모델"));
    assert.match(
      html,
      /<a[^>]*href="https:\/\/example\.com\/original"[^>]*target="_blank"[^>]*>원문 보기 ↗<\/a>/,
    );
    for (const tag of ["태그1", "태그2", "태그3", "태그4"]) {
      assert.ok(html.includes(tag));
    }
  });

  test("ArticleDetail은 요약이 없으면 LLM 분석 박스를 표시하지 않는다", () => {
    const html = renderToStaticMarkup(
      React.createElement(ArticleDetail, {
        selected: makeArticle({ summary: null }),
        isCompact: false,
        emptyMessage: "기사를 선택하세요",
      }),
    );

    assert.equal(html.includes("LLM 분석"), false);
  });

  test("ArticleCard는 미리보기가 95자를 넘을 때만 말줄임표(…)를 붙여 자르고 요약을 본문보다 우선한다", () => {
    const exact95 = "가".repeat(95);
    const over95 = "나".repeat(96);

    const exactHtml = renderToStaticMarkup(
      React.createElement(ArticleCard, {
        article: makeArticle({ summary: exact95, content: "본문 대신 요약이 우선되어야 함" }),
        selected: false,
        onSelect: () => {},
      }),
    );
    assert.ok(exactHtml.includes(exact95));
    assert.equal(exactHtml.includes("…"), false);
    assert.equal(exactHtml.includes("본문 대신 요약이 우선되어야 함"), false);

    const overHtml = renderToStaticMarkup(
      React.createElement(ArticleCard, {
        article: makeArticle({ summary: null, content: over95 }),
        selected: false,
        onSelect: () => {},
      }),
    );
    assert.ok(overHtml.includes(`${"나".repeat(95)}…`));
    assert.equal(overHtml.includes(over95), false);
  });

  test("ArticleCard는 태그를 최대 3개까지 표시하고 선택 여부를 aria-pressed로 나타낸다", () => {
    const selectedHtml = renderToStaticMarkup(
      React.createElement(ArticleCard, {
        article: makeArticle({ tags: ["태그1", "태그2", "태그3", "태그4", "태그5"] }),
        selected: true,
        onSelect: () => {},
      }),
    );

    assert.ok(selectedHtml.includes('aria-pressed="true"'));
    assert.ok(selectedHtml.includes("태그1"));
    assert.ok(selectedHtml.includes("태그2"));
    assert.ok(selectedHtml.includes("태그3"));
    assert.equal(selectedHtml.includes("태그4"), false);
    assert.equal(selectedHtml.includes("태그5"), false);

    const unselectedHtml = renderToStaticMarkup(
      React.createElement(ArticleCard, {
        article: makeArticle({ tags: [] }),
        selected: false,
        onSelect: () => {},
      }),
    );
    assert.ok(unselectedHtml.includes('aria-pressed="false"'));
  });

  test("Sidebar와 Topbar·ReadingHeader는 화면 폭과 필터 상태에 맞는 제목·토글·목록 복귀 헤더를 표시한다", () => {
    const sidebarCompactClosed = renderToStaticMarkup(
      React.createElement(Sidebar, {
        isCompact: true,
        filtersOpen: false,
        onToggleFilters: () => {},
        view: "briefing",
        onViewChange: () => {},
        sourceItems: [
          { source: "", count: 12 },
          ...SOURCE_FILTERS.map((source) => ({ source, count: 1 })),
        ],
        selectedSource: "",
        onSourceClick: () => {},
      }),
    );
    getButtonTag(sidebarCompactClosed, "필터");
    assert.ok(sidebarCompactClosed.includes('id="news-filters" hidden=""'));
    assert.ok(sidebarCompactClosed.includes("전체"));
    assert.ok(sidebarCompactClosed.includes("dev.to"));

    const sidebarCompactOpen = renderToStaticMarkup(
      React.createElement(Sidebar, {
        isCompact: true,
        filtersOpen: true,
        onToggleFilters: () => {},
        view: "articles",
        onViewChange: () => {},
        sourceItems: [{ source: "", count: 0 }],
        selectedSource: "",
        onSourceClick: () => {},
      }),
    );
    getButtonTag(sidebarCompactOpen, "필터 닫기");

    const topbarWideFiltered = renderToStaticMarkup(
      React.createElement(Topbar, {
        isCompact: false,
        selected: null,
        view: "articles",
        selectedSource: "GeekNews",
        query: "",
        onQueryChange: () => {},
        onSearchSubmit: () => {},
      }),
    );
    assert.ok(topbarWideFiltered.includes("기사 피드"));
    assert.ok(topbarWideFiltered.includes("· GeekNews"));
    assert.ok(topbarWideFiltered.includes('placeholder="기사 제목, 본문으로 검색..."'));

    const topbarCompact = renderToStaticMarkup(
      React.createElement(Topbar, {
        isCompact: true,
        selected: null,
        view: "articles",
        selectedSource: "GeekNews",
        query: "",
        onQueryChange: () => {},
        onSearchSubmit: () => {},
      }),
    );
    assert.equal(topbarCompact.includes("기사 피드"), false);

    const readingHeaderHtml = renderToStaticMarkup(
      React.createElement(ReadingHeader, {
        selected: makeArticle({ source: "arXiv", major_category: "AI 연구" }),
        onBack: () => {},
      }),
    );
    assert.ok(readingHeaderHtml.includes("← 목록"));
    assert.ok(readingHeaderHtml.includes("arXiv · AI 연구"));
  });
});
