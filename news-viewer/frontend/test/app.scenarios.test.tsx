import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../src/App.tsx";
import { SOURCE_FILTERS } from "../src/features/articles/useArticles.ts";
import {
  createDeferred,
  createMockArticle,
  createMockBriefing,
  setViewportCompact,
  setupMockFetch,
} from "./helpers/mockApi.ts";

describe("뉴스 뷰어 전체 화면 사용자 시나리오", () => {
  it("최초 진입 시 오늘의 AI 브리핑 보기를 열고 넓은 화면에서는 첫 번째 브리핑 기사를 상세 패널에 자동 표시한다", async () => {
    const briefing = createMockBriefing({
      generated_at: "2026-11-18T09:00:00Z",
      articles: [
        createMockArticle({
          id: 101,
          source: "GeekNews",
          title: "오늘의 브리핑 AI 기사 1",
          summary: "브리핑 핵심 요약 1",
          content: "브리핑 본문 첫 문장",
          major_category: "AI",
          sub_category: "에이전트",
          url: "https://example.com/briefing/101",
          tags: ["AI", "Agent", "LLM", "Briefing"],
        }),
        createMockArticle({
          id: 102,
          source: "arXiv",
          title: "오늘의 브리핑 AI 기사 2",
          summary: "가".repeat(100),
          content: "두 번째 브리핑 본문",
          major_category: "AI 연구",
          sub_category: "추론",
          tags: ["Research", "Reasoning"],
        }),
      ],
    });
    const mock = setupMockFetch({ briefing });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;

    expect(within(sidebar).getByRole("button", { name: "오늘의 AI 브리핑" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(sidebar).getByRole("button", { name: "전체 기사" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    const detailPanel = screen.getByLabelText("기사 상세");
    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { level: 1, name: "오늘의 브리핑 AI 기사 1" })).toBeInTheDocument();
    });

    expect(mock.calls).toContain("/api/briefing");
    expect(screen.getByText("최근 24시간의 AI 소식 최대 5개를 모았습니다.")).toBeInTheDocument();
    expect(
      screen.getByText(
        `조회 시각: ${new Date("2026-11-18T09:00:00Z").toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} (한국 시간)`,
      ),
    ).toBeInTheDocument();

    const listPanel = screen.getByLabelText("오늘의 AI 브리핑 목록");
    const firstCard = within(listPanel).getByRole("button", { name: /오늘의 브리핑 AI 기사 1/ });
    expect(firstCard).toHaveAttribute("aria-pressed", "true");
    // 카드는 태그를 최대 3개만 표시하고 미리보기는 95자 초과 시 말줄임표로 자른다
    expect(within(firstCard).queryByText("Briefing")).not.toBeInTheDocument();
    const secondCard = within(listPanel).getByRole("button", { name: /오늘의 브리핑 AI 기사 2/ });
    expect(within(secondCard).getByText(`${"가".repeat(95)}…`)).toBeInTheDocument();

    expect(within(detailPanel).getByText("LLM 분석")).toBeInTheDocument();
    expect(within(detailPanel).getByText("브리핑 핵심 요약 1")).toBeInTheDocument();
    expect(within(detailPanel).getByText("브리핑 본문 첫 문장")).toBeInTheDocument();
    expect(within(detailPanel).getByText("Briefing")).toBeInTheDocument();
    const originalLink = within(detailPanel).getByRole("link", { name: "원문 보기 ↗" });
    expect(originalLink).toHaveAttribute("href", "https://example.com/briefing/101");
    expect(originalLink).toHaveAttribute("target", "_blank");

    await user.click(secondCard);
    expect(secondCard).toHaveAttribute("aria-pressed", "true");
    expect(firstCard).toHaveAttribute("aria-pressed", "false");
    expect(
      within(detailPanel).getByRole("heading", { level: 1, name: "오늘의 브리핑 AI 기사 2" }),
    ).toBeInTheDocument();
  });

  it("사이드바에서 다른 보기로 전환하면 기존 선택을 해제해 새 보기 첫 기사를 표시하고 같은 보기를 다시 누르면 선택을 유지한다", async () => {
    const mock = setupMockFetch({
      articles: [
        createMockArticle({ id: 1, title: "피드 첫 기사" }),
        createMockArticle({ id: 2, title: "피드 둘째 기사" }),
      ],
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { name: "오늘의 브리핑 AI 기사 1" })).toBeInTheDocument();
    });

    const listPanel = screen.getByLabelText("오늘의 AI 브리핑 목록");
    await user.click(within(listPanel).getByRole("button", { name: /오늘의 브리핑 AI 기사 2/ }));
    expect(within(detailPanel).getByRole("heading", { name: "오늘의 브리핑 AI 기사 2" })).toBeInTheDocument();

    // 이미 선택된 보기를 다시 누르면 선택과 목록을 유지하고 재요청하지 않는다
    const briefingCallCount = mock.calls.filter((url) => url === "/api/briefing").length;
    await user.click(within(sidebar).getByRole("button", { name: "오늘의 AI 브리핑" }));
    expect(within(detailPanel).getByRole("heading", { name: "오늘의 브리핑 AI 기사 2" })).toBeInTheDocument();
    expect(mock.calls.filter((url) => url === "/api/briefing")).toHaveLength(briefingCallCount);

    // 전체 기사 보기로 전환하면 상단바 제목이 바뀌고 첫 피드 기사를 자동 선택한다
    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    expect(screen.getByText("기사 피드")).toBeInTheDocument();
    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { name: "피드 첫 기사" })).toBeInTheDocument();
    });

    await user.click(within(screen.getByLabelText("기사 목록")).getByRole("button", { name: /피드 둘째 기사/ }));
    expect(within(detailPanel).getByRole("heading", { name: "피드 둘째 기사" })).toBeInTheDocument();
    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    expect(within(detailPanel).getByRole("heading", { name: "피드 둘째 기사" })).toBeInTheDocument();

    // 다시 브리핑 보기로 전환하면 브리핑을 새로 불러온다
    await user.click(within(sidebar).getByRole("button", { name: "오늘의 AI 브리핑" }));
    await waitFor(() => {
      expect(mock.calls.filter((url) => url === "/api/briefing").length).toBeGreaterThan(briefingCallCount);
    });
    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { name: "오늘의 브리핑 AI 기사 1" })).toBeInTheDocument();
    });
  });

  it("브리핑 기사가 없으면 최근 24시간에 수집된 AI 기사가 없다는 안내를 표시한다", async () => {
    const deferredBriefing = createDeferred<ReturnType<typeof createMockBriefing>>();
    setupMockFetch({ briefing: deferredBriefing.promise });

    render(<App />);
    const listPanel = screen.getByLabelText("오늘의 AI 브리핑 목록");
    const detailPanel = screen.getByLabelText("기사 상세");
    const refreshButton = screen.getByRole("button", { name: "새로고침" });

    expect(refreshButton).toBeDisabled();
    expect(within(listPanel).getByRole("status")).toHaveTextContent("브리핑을 불러오는 중...");
    expect(within(detailPanel).getByText("브리핑을 불러오는 중...")).toBeInTheDocument();

    deferredBriefing.resolve(createMockBriefing({ articles: [] }));

    await waitFor(() => {
      expect(within(listPanel).getByText("최근 24시간에 수집된 AI 기사가 없습니다.")).toBeInTheDocument();
    });
    expect(within(detailPanel).getByText("최근 24시간에 수집된 AI 기사가 없습니다")).toBeInTheDocument();
    expect(refreshButton).toBeEnabled();
  });

  it("브리핑 조회에 실패하면 오류 메시지와 다시 시도 버튼을 표시하고 클릭 시 브리핑을 다시 불러온다", async () => {
    const mock = setupMockFetch({ briefing: { status: 500 } });
    const user = userEvent.setup();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("브리핑을 불러오지 못했습니다.");
    });
    expect(within(screen.getByLabelText("기사 상세")).getByText("브리핑을 불러오지 못했습니다")).toBeInTheDocument();

    mock.setBriefing(createMockBriefing());
    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    await waitFor(() => {
      expect(
        within(screen.getByLabelText("기사 상세")).getByRole("heading", { name: "오늘의 브리핑 AI 기사 1" }),
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("사이드바에 전체와 8개 고정 출처를 순서대로 표시하고 필터나 검색을 바꿔도 전체 개수는 고정한다", async () => {
    const mock = setupMockFetch({
      sources: [
        { source: "네이버뉴스", count: 12 },
        { source: "GeekNews", count: 8 },
        { source: "arXiv", count: 5 },
      ],
      articles: [
        createMockArticle({ id: 1, source: "GeekNews", title: "GeekNews 기사" }),
        createMockArticle({ id: 2, source: "arXiv", title: "arXiv 기사" }),
      ],
      totalAll: 100,
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;

    await waitFor(() => {
      expect(within(sidebar).getByRole("button", { name: /^전체\s*100$/ })).toBeInTheDocument();
    });

    expect(mock.calls).toContain("/api/sources");
    expect(mock.calls).toContain("/api/articles?page=1&size=1");

    const sidebarButtons = within(sidebar).getAllByRole("button");
    const sourceLabels = sidebarButtons
      .slice(2)
      .map((btn) => btn.firstElementChild?.textContent ?? "");
    expect(sourceLabels).toEqual(["전체", ...SOURCE_FILTERS]);

    const expectedCounts: Record<string, string> = {
      전체: "100",
      네이버뉴스: "12",
      "Google News": "0",
      GeekNews: "8",
      "Reddit AI": "0",
      "GitHub Trending": "0",
      "Hugging Face": "0",
      arXiv: "5",
      "dev.to": "0",
    };
    for (const btn of sidebarButtons.slice(2)) {
      const label = btn.firstElementChild?.textContent ?? "";
      const count = btn.lastElementChild?.textContent ?? "";
      expect(count).toBe(expectedCounts[label]);
    }

    // 출처 필터와 검색으로 목록 total이 바뀌어도 사이드바 '전체' 개수는 100으로 고정된다
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(screen.getByText("출처: GeekNews")).toBeInTheDocument();
    });
    expect(within(sidebar).getByRole("button", { name: /^전체\s*100$/ })).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText("기사 제목, 본문으로 검색...");
    await user.type(searchInput, "존재하지않는검색어");
    await user.click(screen.getByRole("button", { name: "검색" }));

    await waitFor(() => {
      expect(screen.getByText("‘존재하지않는검색어’에 대한 검색 결과가 없습니다")).toBeInTheDocument();
    });
    expect(within(sidebar).getByRole("button", { name: /^전체\s*100$/ })).toBeInTheDocument();
  });

  it("사이드바 메타데이터 조회에 실패하면 필터 오류 알림을 표시한다", async () => {
    setupMockFetch({ sources: { status: 500 } });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "필터 정보를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
      );
    });
  });

  it("사이드바에서 출처를 선택하면 전체 기사 보기로 전환해 해당 출처의 1페이지를 조회하고 다시 누르거나 필터 초기화를 누르면 해제한다", async () => {
    const mock = setupMockFetch({
      articles: [
        createMockArticle({ id: 1, source: "GeekNews", title: "GeekNews 전용 기사" }),
        createMockArticle({ id: 2, source: "arXiv", title: "arXiv 전용 기사" }),
      ],
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;
    const listPanel = screen.getByLabelText("오늘의 AI 브리핑 목록");

    await waitFor(() => {
      expect(within(sidebar).getByRole("button", { name: /^GeekNews/ })).toBeInTheDocument();
    });

    listPanel.scrollTop = 180;
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));

    const articlesListPanel = screen.getByLabelText("기사 목록");
    await waitFor(() => {
      expect(within(articlesListPanel).getByText("GeekNews 전용 기사")).toBeInTheDocument();
    });
    expect(articlesListPanel.scrollTop).toBe(0);
    expect(screen.getByText("기사 피드")).toBeInTheDocument();
    expect(screen.getByText("· GeekNews")).toBeInTheDocument();
    expect(screen.getByText("적용된 필터:")).toBeInTheDocument();
    expect(screen.getByText("출처: GeekNews")).toBeInTheDocument();
    expect(mock.calls).toContain("/api/articles?page=1&size=20&source=GeekNews");
    expect(within(articlesListPanel).queryByText("arXiv 전용 기사")).not.toBeInTheDocument();

    // 활성 필터 칩을 누르면 출처 필터를 해제하고 1페이지를 다시 조회한다
    await user.click(screen.getByRole("button", { name: "출처: GeekNews 필터 해제" }));
    await waitFor(() => {
      expect(within(articlesListPanel).getByText("arXiv 전용 기사")).toBeInTheDocument();
    });
    expect(screen.queryByText("적용된 필터:")).not.toBeInTheDocument();
    expect(screen.queryByText("· GeekNews")).not.toBeInTheDocument();

    // 선택된 출처를 사이드바에서 다시 눌러도 필터가 해제된다
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(screen.getByText("출처: GeekNews")).toBeInTheDocument();
    });
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(within(articlesListPanel).getByText("arXiv 전용 기사")).toBeInTheDocument();
    });
    expect(screen.queryByText("적용된 필터:")).not.toBeInTheDocument();

    // 필터 초기화 버튼으로도 해제된다
    await user.click(within(sidebar).getByRole("button", { name: /^arXiv/ }));
    await waitFor(() => {
      expect(screen.getByText("출처: arXiv")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "필터 초기화" }));
    await waitFor(() => {
      expect(within(articlesListPanel).getByText("GeekNews 전용 기사")).toBeInTheDocument();
    });
    expect(screen.queryByText("적용된 필터:")).not.toBeInTheDocument();
  });

  it("전체 기사 보기에서 기사 피드 조회에 실패하면 목록과 선택을 비우고 오류 알림을 표시한다", async () => {
    setupMockFetch({
      articles: (query) => {
        if (query.size === 1) {
          return { total: 10, page: 1, size: 1, articles: [] };
        }
        return { status: 500 };
      },
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;

    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
      );
    });
    expect(within(screen.getByLabelText("기사 상세")).getByText("기사를 불러오지 못했습니다")).toBeInTheDocument();
    expect(within(screen.getByLabelText("기사 목록")).queryAllByRole("button")).toHaveLength(0);
  });

  it("검색어는 입력 중에는 조회하지 않고 제출할 때만 전체 기사 보기 1페이지로 조회하며 결과가 없으면 검색어 초기화 버튼으로 복구한다", async () => {
    const mock = setupMockFetch({
      articles: [
        createMockArticle({ id: 1, title: "트랜스포머 아키텍처 해설", content: "딥러닝 기초" }),
        createMockArticle({ id: 2, title: "데이터베이스 인덱싱", content: "B-Tree 구조" }),
      ],
    });
    const user = userEvent.setup();

    render(<App />);
    await waitFor(() => {
      expect(within(screen.getByLabelText("기사 상세")).getByRole("heading", { name: "오늘의 브리핑 AI 기사 1" })).toBeInTheDocument();
    });

    const beforeTypingFeedCalls = mock.calls.filter((u) => u.startsWith("/api/articles")).length;
    const searchInput = screen.getByPlaceholderText("기사 제목, 본문으로 검색...");

    await user.type(searchInput, "없는키워드");
    expect(mock.calls.filter((u) => u.startsWith("/api/articles"))).toHaveLength(beforeTypingFeedCalls);

    await user.click(screen.getByRole("button", { name: "검색" }));

    await waitFor(() => {
      expect(screen.getByText("‘없는키워드’에 대한 검색 결과가 없습니다")).toBeInTheDocument();
    });
    expect(
      screen.getByText("단어의 철자가 정확한지 확인하거나 다른 검색어로 검색해 보세요."),
    ).toBeInTheDocument();
    expect(within(screen.getByLabelText("기사 상세")).getByText("검색 결과가 없습니다")).toBeInTheDocument();
    expect(
      mock.calls.some((u) => u === `/api/articles?page=1&size=20&q=${encodeURIComponent("없는키워드")}`),
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: "검색어 초기화" }));

    const listPanel = screen.getByLabelText("기사 목록");
    await waitFor(() => {
      expect(within(listPanel).getByText("트랜스포머 아키텍처 해설")).toBeInTheDocument();
    });
    expect(searchInput).toHaveValue("");
    expect(within(listPanel).getByText("데이터베이스 인덱싱")).toBeInTheDocument();

    // 검색어 없이 결과가 비어 있는 경우 안내 문구 확인
    mock.setArticles([]);
    await user.type(searchInput, "임시{Enter}");
    await waitFor(() => {
      expect(screen.getByText("‘임시’에 대한 검색 결과가 없습니다")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "검색어 초기화" }));
    await waitFor(() => {
      expect(screen.getByText("기사가 없습니다")).toBeInTheDocument();
    });
    expect(within(screen.getByLabelText("기사 상세")).getByText("표시할 기사가 없습니다")).toBeInTheDocument();
  });

  it("페이지가 2페이지 이상일 때만 페이지네이션을 표시하고 다른 페이지로 이동한 뒤 출처 필터를 바꾸면 1페이지로 돌아간다", async () => {
    const manyArticles = Array.from({ length: 45 }, (_, idx) =>
      createMockArticle({
        id: idx + 1,
        source: idx < 25 ? "GeekNews" : "arXiv",
        title: `페이지네이션 기사 ${idx + 1}`,
      }),
    );
    const mock = setupMockFetch({ articles: manyArticles });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;

    // 전체 기사 보기로 이동: 45건 -> 3페이지
    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    await waitFor(() => {
      expect(screen.getByText("1 / 3")).toBeInTheDocument();
    });

    const prevButton = screen.getByRole("button", { name: "이전" });
    const nextButton = screen.getByRole("button", { name: "다음" });
    expect(prevButton).toBeDisabled();
    expect(nextButton).toBeEnabled();

    const listPanel = screen.getByLabelText("기사 목록");
    listPanel.scrollTop = 260;

    await user.click(nextButton);
    await waitFor(() => {
      expect(screen.getByText("2 / 3")).toBeInTheDocument();
    });
    expect(listPanel.scrollTop).toBe(0);
    expect(prevButton).toBeEnabled();
    expect(nextButton).toBeEnabled();
    expect(within(listPanel).getByText("페이지네이션 기사 21")).toBeInTheDocument();

    await user.click(nextButton);
    await waitFor(() => {
      expect(screen.getByText("3 / 3")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();

    // 3페이지에서 출처 필터를 바꾸면 1페이지로 돌아간다
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(screen.getByText("1 / 2")).toBeInTheDocument();
    });
    expect(mock.calls).toContain("/api/articles?page=1&size=20&source=GeekNews");

    // 2페이지로 이동한 뒤 검색 제출 시에도 1페이지로 돌아간다
    await user.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => {
      expect(screen.getByText("2 / 2")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("기사 제목, 본문으로 검색...");
    await user.type(searchInput, "페이지네이션 기사 1{Enter}");
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "다음" })).not.toBeInTheDocument();
    });
    expect(mock.calls.at(-1)).toContain("page=1");
  });

  it("브리핑 보기 중 백그라운드 기사 피드 응답이 늦게 도착해도 선택을 유지하고, 필터 전환 시 동일 ID 기사가 있으면 선택을 유지한다", async () => {
    const delayedInitialFeed = createDeferred<{
      total: number;
      page: number;
      size: number;
      articles: ReturnType<typeof createMockArticle>[];
    }>();
    const sharedBriefingArticle = createMockArticle({
      id: 101,
      source: "GeekNews",
      title: "브리핑과 피드 공통 기사",
      content: "공통 기사 본문",
    });

    setupMockFetch({
      briefing: createMockBriefing({ articles: [sharedBriefingArticle] }),
      articles: (query) => {
        if (query.size === 1) {
          return { total: 2, page: 1, size: 1, articles: [] };
        }
        if (!query.source) {
          return delayedInitialFeed.promise;
        }
        return {
          total: 2,
          page: 1,
          size: 20,
          articles: [
            createMockArticle({ id: 201, source: "GeekNews", title: "피드 앞선 다른 기사" }),
            sharedBriefingArticle,
          ],
        };
      },
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { name: "브리핑과 피드 공통 기사" })).toBeInTheDocument();
    });

    // 브리핑 보기 중에 초기 백그라운드 /api/articles 응답이 뒤늦게 도착해도 브리핑 선택을 유지한다
    delayedInitialFeed.resolve({
      total: 1,
      page: 1,
      size: 20,
      articles: [createMockArticle({ id: 999, title: "덮어쓰면 안 되는 백그라운드 기사" })],
    });
    await waitFor(() => {
      expect(within(detailPanel).getByRole("heading", { name: "브리핑과 피드 공통 기사" })).toBeInTheDocument();
    });

    // 브리핑 보기에서 출처 필터를 눌러 전체 기사 보기로 전환할 때 새 목록에 id=101이 있으면 선택을 유지한다
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(screen.getByText("피드 앞선 다른 기사")).toBeInTheDocument();
    });
    expect(within(detailPanel).getByRole("heading", { name: "브리핑과 피드 공통 기사" })).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("기사 목록")).getByRole("button", { name: /브리핑과 피드 공통 기사/ }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("빠르게 연속으로 출처를 바꿀 때 이전 요청을 취소하고 늦게 도착한 이전 응답은 무시한다", async () => {
    const geekNewsDeferred = createDeferred<{
      total: number;
      page: number;
      size: number;
      articles: ReturnType<typeof createMockArticle>[];
    }>();
    const arxivDeferred = createDeferred<{
      total: number;
      page: number;
      size: number;
      articles: ReturnType<typeof createMockArticle>[];
    }>();

    const mock = setupMockFetch({
      articles: (query) => {
        if (query.size === 1) {
          return { total: 2, page: 1, size: 1, articles: [] };
        }
        if (query.source === "GeekNews") return geekNewsDeferred.promise;
        if (query.source === "arXiv") return arxivDeferred.promise;
        return { total: 1, page: 1, size: 20, articles: [createMockArticle({ id: 1, title: "초기 기사" })] };
      },
    });
    const user = userEvent.setup();

    const { container, unmount } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;

    await waitFor(() => {
      expect(within(sidebar).getByRole("button", { name: /^GeekNews/ })).toBeInTheDocument();
    });

    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    const geekNewsReq = mock.requests.find((r) => r.searchParams.get("source") === "GeekNews");
    expect(geekNewsReq?.signal?.aborted).toBe(false);

    await user.click(within(sidebar).getByRole("button", { name: /^arXiv/ }));
    expect(geekNewsReq?.signal?.aborted).toBe(true);

    arxivDeferred.resolve({
      total: 1,
      page: 1,
      size: 20,
      articles: [createMockArticle({ id: 20, source: "arXiv", title: "최신 arXiv 결과" })],
    });

    const articlesListPanel = screen.getByLabelText("기사 목록");
    await waitFor(() => {
      expect(within(articlesListPanel).getByText("최신 arXiv 결과")).toBeInTheDocument();
    });

    // 뒤늦게 도착한 이전 GeekNews 응답이 화면을 덮어쓰지 않아야 한다
    geekNewsDeferred.resolve({
      total: 1,
      page: 1,
      size: 20,
      articles: [createMockArticle({ id: 10, source: "GeekNews", title: "폐기되어야 할 구형 GeekNews 결과" })],
    });

    await waitFor(() => {
      expect(within(articlesListPanel).getByText("최신 arXiv 결과")).toBeInTheDocument();
    });
    expect(within(articlesListPanel).queryByText("폐기되어야 할 구형 GeekNews 결과")).not.toBeInTheDocument();

    // 새 요청 중 화면을 떠나면 진행 중인 요청이 취소된다
    await user.click(within(sidebar).getByRole("button", { name: /^네이버뉴스/ }));
    const naverReq = mock.requests.find((r) => r.searchParams.get("source") === "네이버뉴스");
    expect(naverReq?.signal?.aborted).toBe(false);
    unmount();
    expect(naverReq?.signal?.aborted).toBe(true);
  });

  it("좁은 화면에서는 목록 로드 시 기사를 자동 선택하지 않고 카드를 누르면 읽기 헤더와 상세 패널로 전환하며 목록 버튼으로 스크롤 위치를 복원한다", async () => {
    setViewportCompact(true);
    setupMockFetch({
      briefing: createMockBriefing({
        articles: [
          createMockArticle({
            id: 101,
            source: "GeekNews",
            major_category: "AI",
            title: "모바일 브리핑 첫 기사",
            content: "모바일 상세 본문",
          }),
          createMockArticle({
            id: 102,
            source: "arXiv",
            major_category: "AI 연구",
            title: "모바일 브리핑 둘째 기사",
          }),
        ],
      }),
    });
    const user = userEvent.setup();

    render(<App />);

    const listPanel = screen.getByLabelText("오늘의 AI 브리핑 목록");
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(within(listPanel).getByRole("button", { name: /모바일 브리핑 첫 기사/ })).toBeInTheDocument();
    });

    // 좁은 화면에서는 상단바 제목을 생략하고, 자동 선택 없이 목록만 표시한다
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(listPanel).toHaveStyle({ display: "block" });
    expect(detailPanel).toHaveStyle({ display: "none" });
    expect(
      within(listPanel).getByRole("button", { name: /모바일 브리핑 첫 기사/ }),
    ).toHaveAttribute("aria-pressed", "false");

    // 스크롤 위치를 저장한 뒤 카드를 누르면 목록을 숨기고 읽기 헤더와 상세 패널을 표시한다
    listPanel.scrollTop = 320;
    await user.click(within(listPanel).getByRole("button", { name: /모바일 브리핑 첫 기사/ }));

    expect(listPanel).toHaveStyle({ display: "none" });
    expect(detailPanel).not.toHaveStyle({ display: "none" });
    const readingHeader = screen.getByRole("banner");
    expect(within(readingHeader).getByRole("button", { name: "기사 목록으로 돌아가기" })).toHaveTextContent(
      "← 목록",
    );
    expect(within(readingHeader).getByText("GeekNews · AI")).toBeInTheDocument();
    expect(
      within(detailPanel).getByRole("heading", { level: 1, name: "모바일 브리핑 첫 기사" }),
    ).toBeInTheDocument();

    // ← 목록 클릭 시 선택을 해제하고 저장된 스크롤 위치로 복원한다
    await user.click(within(readingHeader).getByRole("button", { name: "기사 목록으로 돌아가기" }));

    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(detailPanel).toHaveStyle({ display: "none" });
    await waitFor(() => {
      expect(listPanel.scrollTop).toBe(320);
    });
  });

  it("좁은 화면에서 필터 토글을 열어 출처를 선택하거나 넓은 화면으로 전환하면 필터 영역이 자동으로 닫히고 경계 전환 시 선택 규칙을 지킨다", async () => {
    setViewportCompact(true);
    const pendingFeed = createDeferred<{
      total: number;
      page: number;
      size: number;
      articles: ReturnType<typeof createMockArticle>[];
    }>();

    setupMockFetch({
      articles: (query) => {
        if (query.size === 1) {
          return { total: 2, page: 1, size: 1, articles: [] };
        }
        if (query.source === "arXiv") {
          return pendingFeed.promise;
        }
        return {
          total: 2,
          page: 1,
          size: 20,
          articles: [
            createMockArticle({ id: 1, source: "GeekNews", title: "전환 테스트 기사 1" }),
            createMockArticle({ id: 2, source: "GeekNews", title: "전환 테스트 기사 2" }),
          ],
        };
      },
    });
    const user = userEvent.setup();

    const { container } = render(<App />);
    const sidebar = container.querySelector("aside") as HTMLElement;
    const filtersRegion = container.querySelector("#news-filters") as HTMLElement;

    expect(filtersRegion).toHaveAttribute("hidden");
    const toggleBtn = within(sidebar).getByRole("button", { name: "필터" });
    expect(toggleBtn).toHaveAttribute("aria-expanded", "false");

    // 필터 열기 -> 출처 선택 시 필터 영역이 자동으로 닫힌다
    await user.click(toggleBtn);
    expect(filtersRegion).not.toHaveAttribute("hidden");
    expect(within(sidebar).getByRole("button", { name: "필터 닫기" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    expect(filtersRegion).toHaveAttribute("hidden");
    await waitFor(() => {
      expect(screen.getByText("전환 테스트 기사 1")).toBeInTheDocument();
    });

    // 적용된 출처 칩을 누를 때도 필터가 열려 있었다면 닫힌다
    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    expect(filtersRegion).not.toHaveAttribute("hidden");
    await user.click(screen.getByRole("button", { name: "출처: GeekNews 필터 해제" }));
    expect(filtersRegion).toHaveAttribute("hidden");

    // 로딩 중 좁은 화면 -> 넓은 화면 전환 시 이전 목록 기사를 성급히 자동 선택하지 않는다
    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    await user.click(within(sidebar).getByRole("button", { name: /^arXiv/ }));
    expect(screen.getByText("불러오는 중...")).toBeInTheDocument();

    setViewportCompact(false);
    expect(filtersRegion).not.toHaveAttribute("hidden");
    expect(screen.getByText("기사 피드")).toBeInTheDocument();
    expect(within(screen.getByLabelText("기사 상세")).getByText("기사를 불러오는 중...")).toBeInTheDocument();

    pendingFeed.resolve({
      total: 1,
      page: 1,
      size: 20,
      articles: [createMockArticle({ id: 30, source: "arXiv", major_category: "AI 연구", title: "arXiv 로딩 완료 기사" })],
    });

    const detailPanel = screen.getByLabelText("기사 상세");
    await waitFor(() => {
      expect(
        within(detailPanel).getByRole("heading", { level: 1, name: "arXiv 로딩 완료 기사" }),
      ).toBeInTheDocument();
    });

    // 선택된 기사가 있는 상태에서 넓은 화면 -> 좁은 화면으로 바뀌면 필터는 닫혀 있고 읽기 헤더와 상세 패널을 유지한다
    setViewportCompact(true);
    expect(filtersRegion).toHaveAttribute("hidden");
    expect(within(sidebar).getByRole("button", { name: "필터" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("banner")).toHaveTextContent("arXiv · AI 연구");
    expect(
      within(detailPanel).getByRole("heading", { level: 1, name: "arXiv 로딩 완료 기사" }),
    ).toBeInTheDocument();

    // 선택 해제 후 좁은 화면에서 필터를 연 채 넓은 화면으로 전환하면 필터 토글이 초기화되고 첫 기사가 자동 선택된다
    await user.click(screen.getByRole("button", { name: "기사 목록으로 돌아가기" }));
    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    expect(filtersRegion).not.toHaveAttribute("hidden");

    setViewportCompact(false);
    await waitFor(() => {
      expect(
        within(detailPanel).getByRole("heading", { level: 1, name: "arXiv 로딩 완료 기사" }),
      ).toBeInTheDocument();
    });
    setViewportCompact(true);
    expect(filtersRegion).toHaveAttribute("hidden");
  });
});
