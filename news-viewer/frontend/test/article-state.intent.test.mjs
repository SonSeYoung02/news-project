import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { articleReducer, initialArticleState } from "../src/features/articles/articleState.ts";

function makeArticle(id, overrides = {}) {
  return {
    id,
    url: `https://example.com/articles/${id}`,
    source: "GeekNews",
    title: `기사 제목 ${id}`,
    content: `기사 본문 ${id}`,
    published_at: "2026-05-14T12:00:00Z",
    crawled_at: "2026-05-14T12:05:00Z",
    summary: `기사 요약 ${id}`,
    major_category: "AI",
    sub_category: "LLM",
    tags: ["AI", "LLM"],
    original_title: null,
    original_content: null,
    translated_title: null,
    translated_content: null,
    translation_status: null,
    ...overrides,
  };
}

describe("기사 목록 상태와 자동 선택·선택 유지 의도", () => {
  test("넓은 화면에서 기사 피드 로드가 끝나면 첫 번째 기사를 자동 선택한다", () => {
    const first = makeArticle(1);
    const second = makeArticle(2);
    const fetching = articleReducer(initialArticleState, {
      type: "START_FETCH",
      requestId: 1,
      view: "articles",
    });

    const loaded = articleReducer(fetching, {
      type: "FETCH_SUCCESS",
      requestId: 1,
      articles: [first, second],
      total: 2,
      isCompact: false,
      view: "articles",
    });

    assert.equal(loaded.loading, false);
    assert.equal(loaded.total, 2);
    assert.equal(loaded.selected?.id, 1);
  });

  test("넓은 화면에서도 기사 피드 응답 목록이 비어 있으면 선택된 기사를 비운다", () => {
    const fetching = articleReducer(
      { ...initialArticleState, selected: makeArticle(1), requestId: 1 },
      { type: "START_FETCH", requestId: 2, view: "articles" },
    );
    assert.equal(fetching.selected, null);

    const loaded = articleReducer(fetching, {
      type: "FETCH_SUCCESS",
      requestId: 2,
      articles: [],
      total: 0,
      isCompact: false,
      view: "articles",
    });

    assert.equal(loaded.loading, false);
    assert.equal(loaded.articles.length, 0);
    assert.equal(loaded.selected, null);
  });

  test("좁은 화면에서는 기사 피드 로드가 끝나도 첫 번째 기사를 자동 선택하지 않는다", () => {
    const fetching = articleReducer(initialArticleState, {
      type: "START_FETCH",
      requestId: 1,
      view: "articles",
    });

    const loaded = articleReducer(fetching, {
      type: "FETCH_SUCCESS",
      requestId: 1,
      articles: [makeArticle(1), makeArticle(2)],
      total: 2,
      isCompact: true,
      view: "articles",
    });

    assert.equal(loaded.loading, false);
    assert.equal(loaded.articles.length, 2);
    assert.equal(loaded.selected, null);
  });

  test("좁은 화면에서 기존 선택 기사가 새 목록에 없으면 자동 선택 없이 선택을 비운다", () => {
    const state = {
      ...initialArticleState,
      loading: true,
      selected: makeArticle(99),
      requestId: 3,
    };

    const loaded = articleReducer(state, {
      type: "FETCH_SUCCESS",
      requestId: 3,
      articles: [makeArticle(1), makeArticle(2)],
      total: 2,
      isCompact: true,
      view: "articles",
    });

    assert.equal(loaded.selected, null);
  });

  test("새 기사 피드 응답에 기존 선택 기사와 같은 id가 있으면 넓은·좁은 화면 모두 그 선택을 유지한다", () => {
    const selectedArticle = makeArticle(2, { title: "기존 선택 기사" });
    const incomingFirst = makeArticle(1);
    const incomingMatching = makeArticle(2, { title: "새 응답의 동일 id 기사" });

    for (const isCompact of [false, true]) {
      const loadingState = {
        ...initialArticleState,
        loading: true,
        selected: selectedArticle,
        requestId: 4,
      };

      const loaded = articleReducer(loadingState, {
        type: "FETCH_SUCCESS",
        requestId: 4,
        articles: [incomingFirst, incomingMatching],
        total: 2,
        isCompact,
        view: "articles",
      });

      assert.equal(loaded.selected?.id, 2);
      assert.equal(loaded.selected, selectedArticle);
    }
  });

  test("전체 기사 보기에서 새 조회를 시작하면 기존 선택과 오류를 즉시 초기화한다", () => {
    const prevState = {
      ...initialArticleState,
      loading: false,
      error: "이전 오류",
      articles: [makeArticle(1)],
      selected: makeArticle(1),
      requestId: 1,
    };

    const nextState = articleReducer(prevState, {
      type: "START_FETCH",
      requestId: 2,
      view: "articles",
    });

    assert.equal(nextState.loading, true);
    assert.equal(nextState.selected, null);
    assert.equal(nextState.error, "");
    assert.equal(nextState.requestId, 2);
  });

  test("오늘의 AI 브리핑 보기 중에는 기사 피드 조회가 시작되거나 성공 응답이 와도 브리핑 선택을 유지한다", () => {
    const briefingSelected = makeArticle(500, { title: "브리핑 선택 기사" });
    const baseState = {
      ...initialArticleState,
      loading: false,
      articles: [makeArticle(1)],
      selected: briefingSelected,
      requestId: 1,
    };

    const fetching = articleReducer(baseState, {
      type: "START_FETCH",
      requestId: 2,
      view: "briefing",
    });
    assert.equal(fetching.loading, true);
    assert.equal(fetching.selected, briefingSelected);

    const loaded = articleReducer(fetching, {
      type: "FETCH_SUCCESS",
      requestId: 2,
      articles: [makeArticle(10), makeArticle(20)],
      total: 2,
      isCompact: false,
      view: "briefing",
    });
    assert.equal(loaded.loading, false);
    assert.equal(loaded.articles.length, 2);
    assert.equal(loaded.selected, briefingSelected);
  });

  test("오늘의 AI 브리핑 보기 중에는 기사 피드 요청이 실패해도 브리핑 선택을 유지한다", () => {
    const briefingSelected = makeArticle(500, { title: "브리핑 선택 기사" });
    const baseState = {
      ...initialArticleState,
      loading: false,
      articles: [makeArticle(1)],
      total: 1,
      selected: briefingSelected,
      requestId: 1,
    };

    const fetching = articleReducer(baseState, {
      type: "START_FETCH",
      requestId: 2,
      view: "briefing",
    });
    assert.equal(fetching.loading, true);
    assert.equal(fetching.selected, briefingSelected);

    const failed = articleReducer(fetching, {
      type: "FETCH_ERROR",
      requestId: 2,
      error: "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
      view: "briefing",
    });
    assert.equal(failed.loading, false);
    assert.deepEqual(failed.articles, []);
    assert.equal(failed.total, 0);
    assert.equal(failed.error, "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.");
    assert.equal(failed.selected, briefingSelected);
  });

  test("더 최신 요청이 시작된 뒤 늦게 도착한 이전 성공·실패 응답은 무시한다", () => {
    const waitingLatest = {
      ...initialArticleState,
      loading: true,
      articles: [makeArticle(1)],
      total: 1,
      selected: null,
      error: "",
      requestId: 5,
    };

    const afterLateSuccess = articleReducer(waitingLatest, {
      type: "FETCH_SUCCESS",
      requestId: 4,
      articles: [makeArticle(99)],
      total: 99,
      isCompact: false,
      view: "articles",
    });
    assert.equal(afterLateSuccess, waitingLatest);

    const afterLateError = articleReducer(waitingLatest, {
      type: "FETCH_ERROR",
      requestId: 4,
      error: "늦게 도착한 이전 요청 오류",
    });
    assert.equal(afterLateError, waitingLatest);
  });

  test("기사 피드 조회가 실패하면 목록과 선택을 비우고 기본 오류 문구를 설정한다", () => {
    const loadingState = {
      ...initialArticleState,
      loading: true,
      articles: [makeArticle(1), makeArticle(2)],
      total: 2,
      selected: makeArticle(1),
      requestId: 6,
    };

    const failed = articleReducer(loadingState, {
      type: "FETCH_ERROR",
      requestId: 6,
    });

    assert.equal(failed.loading, false);
    assert.deepEqual(failed.articles, []);
    assert.equal(failed.total, 0);
    assert.equal(failed.selected, null);
    assert.equal(failed.error, "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.");
  });

  test("화면 크기가 바뀌어도 이미 선택된 기사는 양방향 모두 해제하거나 덮어쓰지 않고 유지한다", () => {
    const first = makeArticle(1);
    const second = makeArticle(2);
    const initial = {
      ...initialArticleState,
      loading: false,
      articles: [first, second],
      selected: second,
    };

    const toCompact = articleReducer(initial, {
      type: "RESIZE_VIEWPORT",
      isCompact: true,
      view: "articles",
    });
    assert.equal(toCompact.selected?.id, 2);

    const backToWide = articleReducer(toCompact, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    assert.equal(backToWide.selected?.id, 2);
  });

  test("선택 없이 좁은 화면에서 넓은 화면으로 바뀌면 로딩 완료 목록의 첫 기사를 선택하고, 로딩 중에는 자동 선택하지 않는다", () => {
    const first = makeArticle(1);
    const second = makeArticle(2);

    const loadingState = {
      ...initialArticleState,
      loading: true,
      articles: [first, second],
      selected: null,
    };
    const resizedWhileLoading = articleReducer(loadingState, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    assert.equal(resizedWhileLoading.selected, null);

    const readyState = {
      ...loadingState,
      loading: false,
    };
    const resizedAfterLoad = articleReducer(readyState, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "articles",
    });
    assert.equal(resizedAfterLoad.selected?.id, 1);
  });

  test("브리핑 보기에서 선택 없이 넓은 화면으로 바뀌어도 기사 피드 목록을 자동 선택하지 않는다", () => {
    const state = {
      ...initialArticleState,
      loading: false,
      articles: [makeArticle(1)],
      selected: null,
    };

    const resized = articleReducer(state, {
      type: "RESIZE_VIEWPORT",
      isCompact: false,
      view: "briefing",
    });

    assert.equal(resized.selected, null);
  });

  test("사용자가 기사를 선택하거나 목록으로 돌아와 선택을 해제하면 선택 상태가 갱신된다", () => {
    const first = makeArticle(1);
    const second = makeArticle(2);

    const selected = articleReducer(initialArticleState, {
      type: "SELECT_ARTICLE",
      payload: first,
    });
    assert.equal(selected.selected?.id, 1);

    const updated = articleReducer(selected, {
      type: "SELECT_ARTICLE",
      payload: (prev) => (prev?.id === 1 ? second : null),
    });
    assert.equal(updated.selected?.id, 2);

    const cleared = articleReducer(updated, {
      type: "SELECT_ARTICLE",
      payload: null,
    });
    assert.equal(cleared.selected, null);
  });
});
