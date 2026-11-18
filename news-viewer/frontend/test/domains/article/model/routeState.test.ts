import { describe, expect, it } from "vitest";
import {
  buildRouteUrl,
  changePageRoute,
  createDetailNavigationState,
  createFilterTransitionState,
  getDetailEmptyMessage,
  getDocumentTitle,
  getListUrl,
  getPreferredArticleId,
  isDefinedRoute,
  parseArticleId,
  parsePage,
  parseRouteState,
  pickAutoSelectedArticleId,
  resetFiltersRoute,
  resetSearchRoute,
  resolveArticleDetailError,
  resolveArticleDetailErrorKind,
  selectArticleRoute,
  backToListRoute,
  shouldAutoSelectFirstArticle,
  shouldNavigateBackInHistory,
  submitSearchRoute,
  switchViewRoute,
  toggleSourceRoute,
} from "../../../../src/domains/article/model/routeState.ts";

describe("URL과 화면 상태 변환·라우트 이동 규칙", () => {
  it("루트(/)와 정의되지 않은 경로는 기본 브리핑 상태로 해석하고 정의되지 않은 라우트로 판정한다", () => {
    expect(isDefinedRoute("/")).toBe(false);
    expect(isDefinedRoute("/unknown")).toBe(false);
    expect(isDefinedRoute("/articles/1/extra")).toBe(false);
    expect(isDefinedRoute("/articles/abc")).toBe(false);
    expect(isDefinedRoute("/briefing/0")).toBe(false);
    expect(isDefinedRoute("/briefing/-3")).toBe(false);

    expect(parseRouteState("/")).toEqual({
      view: "briefing",
      articleId: null,
      source: "",
      search: "",
      page: 1,
    });
    expect(parseRouteState("/unknown/path", "?page=3")).toEqual({
      view: "briefing",
      articleId: null,
      source: "",
      search: "",
      page: 1,
    });
  });

  it("정의된 브리핑·기사 목록·상세 URL을 화면 상태로 정확히 파싱한다", () => {
    expect(isDefinedRoute("/briefing")).toBe(true);
    expect(isDefinedRoute("/briefing/12")).toBe(true);
    expect(isDefinedRoute("/articles")).toBe(true);
    expect(isDefinedRoute("/articles/45")).toBe(true);
    expect(parseArticleId("45")).toBe(45);
    expect(parseArticleId("0")).toBeNull();
    expect(parseArticleId("abc")).toBeNull();

    expect(parseRouteState("/briefing", "")).toEqual({
      view: "briefing",
      articleId: null,
      source: "",
      search: "",
      page: 1,
    });
    expect(parseRouteState("/briefing/12", "")).toEqual({
      view: "briefing",
      articleId: 12,
      source: "",
      search: "",
      page: 1,
    });
    expect(
      parseRouteState("/articles/45", "?source=GeekNews&q=AI+%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8&page=3"),
    ).toEqual({
      view: "articles",
      articleId: 45,
      source: "GeekNews",
      search: "AI 에이전트",
      page: 3,
    });
  });

  it("잘못된 page 값은 1페이지로 본다", () => {
    for (const rawQuery of ["", "?page=0", "?page=-2", "?page=abc", "?page=1.5", "?page=2px", "?page="]) {
      expect(parseRouteState("/articles", rawQuery).page).toBe(1);
    }
    expect(parsePage("2")).toBe(2);
    expect(parsePage("0")).toBe(1);
    expect(parsePage(-5)).toBe(1);
  });

  it("기본값은 URL 쿼리에서 생략한다", () => {
    expect(
      buildRouteUrl({
        view: "articles",
        articleId: null,
        source: "",
        search: "",
        page: 1,
      }),
    ).toBe("/articles");

    expect(
      buildRouteUrl({
        view: "articles",
        articleId: 7,
        source: "",
        search: "",
        page: 1,
      }),
    ).toBe("/articles/7");

    expect(
      buildRouteUrl({
        view: "articles",
        articleId: null,
        source: "GeekNews",
        search: "",
        page: 1,
      }),
    ).toBe("/articles?source=GeekNews");

    expect(
      buildRouteUrl({
        view: "articles",
        articleId: 7,
        source: "GeekNews",
        search: "LLM",
        page: 2,
      }),
    ).toBe("/articles/7?source=GeekNews&q=LLM&page=2");

    expect(
      buildRouteUrl({
        view: "briefing",
        articleId: 5,
        source: "GeekNews",
        search: "LLM",
        page: 2,
      }),
    ).toBe("/briefing/5");
  });

  it("출처 필터를 바꾸면 1페이지 URL로 이동한다", () => {
    const page3 = parseRouteState("/articles/15", "?source=GeekNews&q=AI&page=3");

    expect(buildRouteUrl(toggleSourceRoute(page3, "arXiv"))).toBe("/articles?source=arXiv&q=AI");
    expect(buildRouteUrl(toggleSourceRoute(page3, "GeekNews"))).toBe("/articles?q=AI");

    const fromBriefing = parseRouteState("/briefing/5", "");
    expect(buildRouteUrl(toggleSourceRoute(fromBriefing, "GeekNews"))).toBe("/articles?source=GeekNews");
  });

  it("검색을 제출하거나 초기화하면 1페이지 목록 URL로 이동하고 필터 초기화는 검색어를 유지한다", () => {
    const articlesPage2 = parseRouteState("/articles/20", "?source=arXiv&q=%EA%B8%B0%EC%A1%B4&page=2");

    expect(buildRouteUrl(submitSearchRoute(articlesPage2, "새 검색어"))).toBe(
      "/articles?source=arXiv&q=%EC%83%88+%EA%B2%80%EC%83%89%EC%96%B4",
    );
    expect(buildRouteUrl(submitSearchRoute(articlesPage2, "   "))).toBe("/articles?source=arXiv");
    expect(buildRouteUrl(resetSearchRoute(articlesPage2))).toBe("/articles?source=arXiv");
    expect(buildRouteUrl(resetFiltersRoute(articlesPage2))).toBe("/articles?q=%EA%B8%B0%EC%A1%B4");

    const briefing = parseRouteState("/briefing/3", "");
    expect(buildRouteUrl(submitSearchRoute(briefing, "에이전트"))).toBe(
      "/articles?q=%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8",
    );
  });

  it("페이지 이동 시 선택 기사를 비우고 1 미만 페이지 요청은 1페이지로 보정한다", () => {
    const current = parseRouteState("/articles/42", "?source=GeekNews&page=2");

    expect(buildRouteUrl(changePageRoute(current, 3))).toBe("/articles?source=GeekNews&page=3");
    expect(buildRouteUrl(changePageRoute(current, 0))).toBe("/articles?source=GeekNews");
  });

  it("기사 선택과 앱 내 뒤로 이동은 목록 필터·검색·페이지 쿼리를 유지한다", () => {
    const listState = parseRouteState("/articles", "?source=GeekNews&q=LLM&page=2");
    const detailState = selectArticleRoute(listState, 99);

    expect(buildRouteUrl(detailState)).toBe("/articles/99?source=GeekNews&q=LLM&page=2");
    expect(getListUrl(detailState)).toBe("/articles?source=GeekNews&q=LLM&page=2");
    expect(buildRouteUrl(backToListRoute(detailState))).toBe("/articles?source=GeekNews&q=LLM&page=2");

    const briefingList = parseRouteState("/briefing", "");
    const briefingDetail = selectArticleRoute(briefingList, 12);
    expect(buildRouteUrl(briefingDetail)).toBe("/briefing/12");
    expect(buildRouteUrl(backToListRoute(briefingDetail))).toBe("/briefing");
  });

  it("같은 보기를 다시 선택하면 null을 반환해 현재 URL을 유지하고 다른 보기로 바꾸면 기본 URL로 이동한다", () => {
    const articlesDetail = parseRouteState("/articles/10", "?source=GeekNews&page=2");
    expect(switchViewRoute(articlesDetail, "articles")).toBeNull();
    const toBriefing = switchViewRoute(articlesDetail, "briefing");
    expect(toBriefing && buildRouteUrl(toBriefing)).toBe("/briefing");

    const briefingDetail = parseRouteState("/briefing/10", "");
    expect(switchViewRoute(briefingDetail, "briefing")).toBeNull();
    const toArticles = switchViewRoute(briefingDetail, "articles");
    expect(toArticles && buildRouteUrl(toArticles)).toBe("/articles");
  });

  it("목록 화면에서 진입한 상세 화면만 히스토리 뒤로 가기(navigate(-1)) 대상으로 판정한다", () => {
    const listState = parseRouteState("/articles", "?source=GeekNews&page=2");
    const detailState = parseRouteState("/articles/99", "?source=GeekNews&page=2");

    const navStateFromList = createDetailNavigationState(listState);
    expect(shouldNavigateBackInHistory(navStateFromList, detailState)).toBe(true);
    expect(shouldNavigateBackInHistory(null, detailState)).toBe(false);
    expect(createDetailNavigationState(detailState)).toBeUndefined();
    expect(shouldNavigateBackInHistory({ fromListUrl: "/articles?page=1" }, detailState)).toBe(false);
  });

  it("브리핑에서 필터 전환 시 기존 선택 기사 ID가 새 목록에 있으면 우선 선택하고 없으면 첫 기사를 선택한다", () => {
    const briefingDetail = parseRouteState("/briefing/101", "");
    const transitionState = createFilterTransitionState(briefingDetail);
    expect(getPreferredArticleId(transitionState)).toBe(101);
    expect(pickAutoSelectedArticleId([201, 101], getPreferredArticleId(transitionState))).toBe(101);
    expect(pickAutoSelectedArticleId([201, 202], getPreferredArticleId(transitionState))).toBe(201);
    expect(pickAutoSelectedArticleId([], 101)).toBeNull();

    const articlesDetail = parseRouteState("/articles/101", "");
    expect(createFilterTransitionState(articlesDetail)).toBeUndefined();
  });

  it("단건 조회 오류 메시지와 데스크톱 자동 선택 조건을 정확히 판정한다", () => {
    expect(resolveArticleDetailError(Object.assign(new Error("HTTP 404"), { status: 404 }))).toBe(
      "요청한 기사를 찾을 수 없습니다.",
    );
    expect(resolveArticleDetailError(Object.assign(new Error("HTTP 500"), { status: 500 }))).toBe(
      "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
    );
    expect(resolveArticleDetailErrorKind(Object.assign(new Error("HTTP 404"), { status: 404 }))).toBe("not_found");
    expect(resolveArticleDetailErrorKind(Object.assign(new Error("HTTP 500"), { status: 500 }))).toBe("error");
    expect(resolveArticleDetailErrorKind(new Error("Network failure"))).toBe("error");

    expect(
      getDetailEmptyMessage({
        view: "articles",
        articleId: 999,
        listLoading: false,
        listError: "",
        detailLoading: false,
        detailError: "요청한 기사를 찾을 수 없습니다.",
        itemCount: 5,
        search: "",
      }),
    ).toBe("요청한 기사를 찾을 수 없습니다.");

    expect(
      getDetailEmptyMessage({
        view: "articles",
        articleId: 999,
        listLoading: false,
        listError: "",
        detailLoading: true,
        detailError: "",
        itemCount: 5,
        search: "",
      }),
    ).toBe("기사를 불러오는 중...");

    expect(
      shouldAutoSelectFirstArticle({
        articleId: null,
        isCompact: false,
        listReady: true,
        listError: "",
        articleCount: 3,
      }),
    ).toBe(true);
    expect(
      shouldAutoSelectFirstArticle({
        articleId: 10,
        isCompact: false,
        listReady: true,
        listError: "",
        articleCount: 3,
      }),
    ).toBe(false);
    expect(
      shouldAutoSelectFirstArticle({
        articleId: null,
        isCompact: true,
        listReady: true,
        listError: "",
        articleCount: 3,
      }),
    ).toBe(false);
    expect(
      shouldAutoSelectFirstArticle({
        articleId: null,
        isCompact: false,
        listReady: false,
        listError: "",
        articleCount: 3,
      }),
    ).toBe(false);
  });

  it("현재 라우트와 기사 조회 상태에 따라 브라우저 탭 제목을 생성한다", () => {
    expect(
      getDocumentTitle({
        route: parseRouteState("/briefing", ""),
      }),
    ).toBe("오늘의 AI 브리핑 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles", ""),
      }),
    ).toBe("기사 피드 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles", "?source=GeekNews"),
      }),
    ).toBe("GeekNews - 기사 피드 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles", "?q=%EA%B2%80%EC%83%89%EC%96%B4"),
      }),
    ).toBe("'검색어' - 기사 피드 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles", "?source=GeekNews&q=%EA%B2%80%EC%83%89%EC%96%B4&page=2"),
      }),
    ).toBe("GeekNews · '검색어' - 기사 피드 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles/42", "?source=GeekNews"),
        articleTitle: "AI 에이전트 실전 적용기",
      }),
    ).toBe("AI 에이전트 실전 적용기 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/briefing/7", ""),
        articleTitle: "오늘의 브리핑 대표 기사",
      }),
    ).toBe("오늘의 브리핑 대표 기사 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles/999", ""),
        articleTitle: null,
        detailErrorKind: "not_found",
      }),
    ).toBe("기사를 찾을 수 없음 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles/888", ""),
        articleTitle: null,
        detailErrorKind: "error",
      }),
    ).toBe("기사를 불러오지 못함 - 뉴스 뷰어");

    expect(
      getDocumentTitle({
        route: parseRouteState("/articles/777", ""),
        articleTitle: null,
        detailErrorKind: "none",
      }),
    ).toBe("뉴스 뷰어");
  });
});
