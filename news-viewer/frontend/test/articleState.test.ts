import { describe, expect, it } from "vitest";
import { articleReducer, initialArticleState } from "../src/features/articles/articleState.ts";
import { createMockArticle } from "./helpers/mockApi.ts";

describe("기사 목록 및 선택 상태 리듀서", () => {
  it("전체 기사 보기에서 새 조회를 시작하면 로딩 상태로 전환하고 이전 선택과 오류를 비운다", () => {
    const first = createMockArticle({ id: 1, title: "기사 1" });
    const second = createMockArticle({ id: 2, title: "기사 2" });
    const previousState = {
      ...initialArticleState,
      loading: false,
      articles: [first, second],
      selected: first,
      error: "이전 에러",
      requestId: 1,
    };

    const nextState = articleReducer(previousState, {
      type: "START_FETCH",
      requestId: 2,
      view: "articles",
    });

    expect(nextState.loading).toBe(true);
    expect(nextState.selected).toBeNull();
    expect(nextState.error).toBe("");
    expect(nextState.requestId).toBe(2);

    const autoIncremented = articleReducer(nextState, { type: "START_FETCH", view: "articles" });
    expect(autoIncremented.requestId).toBe(3);
  });

  it("브리핑 보기 중에 백그라운드 기사 조회가 시작되어도 현재 선택된 브리핑 기사를 유지한다", () => {
    const briefingSelected = createMockArticle({ id: 101, title: "브리핑 기사" });
    const baseState = {
      ...initialArticleState,
      loading: false,
      articles: [createMockArticle({ id: 1 })],
      selected: briefingSelected,
      requestId: 1,
    };

    const fetching = articleReducer(baseState, {
      type: "START_FETCH",
      requestId: 2,
      view: "briefing",
    });

    expect(fetching.loading).toBe(true);
    expect(fetching.selected).toBe(briefingSelected);

    const loaded = articleReducer(fetching, {
      type: "FETCH_SUCCESS",
      requestId: 2,
      articles: [createMockArticle({ id: 10 }), createMockArticle({ id: 20 })],
      total: 2,
      isCompact: false,
      view: "briefing",
    });

    expect(loaded.loading).toBe(false);
    expect(loaded.articles).toHaveLength(2);
    expect(loaded.selected).toBe(briefingSelected);
  });

  it("조회 결과가 0건이면 데스크톱에서도 선택된 기사를 비운다", () => {
    const loadingState = {
      ...initialArticleState,
      loading: true,
      articles: [createMockArticle({ id: 1, title: "이전 기사" })],
      selected: null,
      requestId: 3,
    };

    const nextState = articleReducer(loadingState, {
      type: "FETCH_SUCCESS",
      requestId: 3,
      articles: [],
      total: 0,
      isCompact: false,
      view: "articles",
    });

    expect(nextState.loading).toBe(false);
    expect(nextState.articles).toHaveLength(0);
    expect(nextState.total).toBe(0);
    expect(nextState.selected).toBeNull();
  });

  it("빠르게 연속 조회할 때 늦게 도착한 이전 요청의 성공 응답은 무시한다", () => {
    const currentState = {
      ...initialArticleState,
      loading: true,
      articles: [],
      total: 0,
      selected: null,
      requestId: 5,
    };

    const afterStaleResponse = articleReducer(currentState, {
      type: "FETCH_SUCCESS",
      requestId: 4,
      articles: [createMockArticle({ id: 99, title: "구 요청 기사" })],
      total: 100,
      isCompact: false,
      view: "articles",
    });

    expect(afterStaleResponse).toBe(currentState);
    expect(afterStaleResponse.articles).toHaveLength(0);
    expect(afterStaleResponse.selected).toBeNull();
    expect(afterStaleResponse.loading).toBe(true);
    expect(afterStaleResponse.requestId).toBe(5);

    const finalState = articleReducer(afterStaleResponse, {
      type: "FETCH_SUCCESS",
      requestId: 5,
      articles: [],
      total: 0,
      isCompact: false,
      view: "articles",
    });

    expect(finalState.loading).toBe(false);
    expect(finalState.articles).toHaveLength(0);
    expect(finalState.selected).toBeNull();
  });

  it("빠르게 연속 조회할 때 늦게 도착한 이전 요청의 오류 응답은 무시하고 현재 요청의 오류만 반영한다", () => {
    const loadingState = {
      ...initialArticleState,
      loading: true,
      articles: [createMockArticle({ id: 1, title: "이전 기사" })],
      selected: null,
      requestId: 7,
    };

    const staleError = articleReducer(loadingState, {
      type: "FETCH_ERROR",
      requestId: 6,
      error: "오래된 에러",
    });
    expect(staleError.error).toBe("");
    expect(staleError.loading).toBe(true);
    expect(staleError).toBe(loadingState);

    const currentError = articleReducer(loadingState, {
      type: "FETCH_ERROR",
      requestId: 7,
      error: "서버 에러",
    });
    expect(currentError.loading).toBe(false);
    expect(currentError.articles).toHaveLength(0);
    expect(currentError.total).toBe(0);
    expect(currentError.selected).toBeNull();
    expect(currentError.error).toBe("서버 에러");

    const defaultError = articleReducer(loadingState, {
      type: "FETCH_ERROR",
      requestId: 7,
    });
    expect(defaultError.error).toBe("기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.");
  });

  it("기사 선택 액션은 기사 객체, 상태 갱신 함수, 선택 해제(null)를 모두 처리한다", () => {
    const articleA = createMockArticle({ id: 10, title: "기사 A" });
    const articleB = createMockArticle({ id: 20, title: "기사 B" });

    const state1 = articleReducer(initialArticleState, {
      type: "SELECT_ARTICLE",
      payload: articleA,
    });
    expect(state1.selected?.id).toBe(10);

    const state2 = articleReducer(state1, {
      type: "SELECT_ARTICLE",
      payload: (prev) => (prev?.id === 10 ? articleB : null),
    });
    expect(state2.selected?.id).toBe(20);

    const state3 = articleReducer(state2, {
      type: "SELECT_ARTICLE",
      payload: null,
    });
    expect(state3.selected).toBeNull();
  });

  it("화면 크기가 모바일과 데스크톱 사이에서 바뀌어도 이미 선택된 기사는 유지하고, 로딩 중이 아닐 때만 데스크톱 전환 시 첫 기사를 자동 선택한다", () => {
    const article1 = createMockArticle({ id: 1, title: "기사 1번" });
    const article3 = createMockArticle({ id: 3, title: "기사 3번" });

    const mobileWithSelection = {
      ...initialArticleState,
      articles: [article1, article3],
      selected: article3,
      loading: false,
    };
    const toDesktop = articleReducer(mobileWithSelection, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    expect(toDesktop.selected?.id).toBe(3);

    const toMobile = articleReducer(toDesktop, {
      type: "RESIZE_VIEWPORT",
      isCompact: true,
      view: "articles",
    });
    expect(toMobile.selected?.id).toBe(3);

    const mobileNoSelection = {
      ...initialArticleState,
      articles: [article1, article3],
      selected: null,
      loading: false,
    };
    const toDesktopAutoSelect = articleReducer(mobileNoSelection, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    expect(toDesktopAutoSelect.selected?.id).toBe(1);

    const mobileLoading = {
      ...initialArticleState,
      articles: [article1, article3],
      selected: null,
      loading: true,
    };
    const toDesktopWhileLoading = articleReducer(mobileLoading, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    expect(toDesktopWhileLoading.selected).toBeNull();

    const toDesktopInBriefing = articleReducer(mobileNoSelection, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "briefing",
    });
    expect(toDesktopInBriefing.selected).toBeNull();
  });

  it("조회 응답 도착 시점의 화면 폭이 모바일이면 자동 선택하지 않고 데스크톱이면 첫 기사를 자동 선택한다", () => {
    const article1 = createMockArticle({ id: 1, title: "기사 1" });
    const article2 = createMockArticle({ id: 2, title: "기사 2" });
    const loadingState = {
      ...initialArticleState,
      loading: true,
      requestId: 10,
    };

    const mobileArrival = articleReducer(loadingState, {
      type: "FETCH_SUCCESS",
      requestId: 10,
      articles: [article1],
      total: 1,
      isCompact: true,
      view: "articles",
    });
    expect(mobileArrival.selected).toBeNull();

    const desktopArrival = articleReducer(loadingState, {
      type: "FETCH_SUCCESS",
      requestId: 10,
      articles: [article1, article2],
      total: 2,
      isCompact: false,
      view: "articles",
    });
    expect(desktopArrival.selected?.id).toBe(1);

    const retainedArrival = articleReducer(
      { ...loadingState, selected: article2 },
      {
        type: "FETCH_SUCCESS",
        requestId: 10,
        articles: [article1, createMockArticle({ id: 2, title: "갱신된 기사 2" })],
        total: 2,
        isCompact: true,
        view: "articles",
      },
    );
    expect(retainedArrival.selected).toBe(article2);
  });
});
