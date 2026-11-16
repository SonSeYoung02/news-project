import type { Article } from "../../api/types.ts";

// 화면 보기: 오늘의 AI 브리핑 / 전체 기사
export type View = "briefing" | "articles";

export interface ArticleState {
  articles: Article[];
  total: number;
  loading: boolean;
  error: string;
  selected: Article | null;
  requestId: number;
}

// setSelected 계약: 기사 객체(또는 null) 또는 이전 선택을 받는 갱신 함수
export type SelectedUpdater = Article | null | ((prev: Article | null) => Article | null);

export type ArticleAction =
  | { type: "START_FETCH"; requestId?: number; view?: View }
  | {
      type: "FETCH_SUCCESS";
      requestId?: number;
      articles?: Article[];
      total?: number;
      isCompact?: boolean;
      view?: View;
    }
  | { type: "FETCH_ERROR"; requestId?: number; error?: string }
  | { type: "SELECT_ARTICLE"; payload?: SelectedUpdater; article?: Article | null }
  | { type: "RESIZE_VIEWPORT"; isCompact: boolean; view?: View };

export const initialArticleState: ArticleState = {
  articles: [],
  total: 0,
  loading: true,
  error: "",
  selected: null,
  requestId: 0,
};

export function articleReducer(state: ArticleState, action: ArticleAction): ArticleState {
  switch (action.type) {
    case "START_FETCH":
      return {
        ...state,
        loading: true,
        selected: action.view === "briefing" ? state.selected : null,
        error: "",
        requestId: action.requestId ?? state.requestId + 1,
      };

    case "FETCH_SUCCESS": {
      // Discard stale responses from superseded requests
      if (action.requestId !== undefined && action.requestId !== state.requestId) {
        return state;
      }
      const articles = action.articles || [];
      let nextSelected: Article | null = null;
      if (action.view === "briefing") {
        nextSelected = state.selected;
      } else if (articles.length > 0) {
        const current = state.selected;
        if (current && articles.some((a) => a.id === current.id)) {
          nextSelected = current;
        } else if (!action.isCompact) {
          nextSelected = articles[0];
        }
      }
      return {
        ...state,
        articles,
        total: action.total ?? 0,
        loading: false,
        error: "",
        selected: nextSelected,
      };
    }

    case "FETCH_ERROR": {
      // Discard stale error responses
      if (action.requestId !== undefined && action.requestId !== state.requestId) {
        return state;
      }
      return {
        ...state,
        articles: [],
        total: 0,
        loading: false,
        error: action.error || "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
        selected: null,
      };
    }

    case "SELECT_ARTICLE": {
      const nextSelected =
        typeof action.payload === "function"
          ? action.payload(state.selected)
          : action.payload !== undefined
          ? action.payload
          : action.article;
      return {
        ...state,
        selected: nextSelected ?? null,
      };
    }

    case "RESIZE_VIEWPORT": {
      if (!action.isCompact && (!action.view || action.view === "articles")) {
        // Transitioned to desktop: if no article is selected and not loading, auto-select first article
        if (!state.loading && state.articles.length > 0 && !state.selected) {
          return {
            ...state,
            selected: state.articles[0],
          };
        }
      }
      // If an article is already selected, retain it across both mobile and desktop transitions
      return state;
    }

    default:
      return state;
  }
}
