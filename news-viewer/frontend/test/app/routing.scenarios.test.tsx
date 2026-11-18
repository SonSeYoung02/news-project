import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { describe, expect, it } from "vitest";
import App from "../../src/app/App.tsx";
import {
  createMockArticle,
  createMockBriefing,
  setViewportCompact,
  setupMockFetch,
} from "../helpers/mockApi.ts";

function renderRoutedApp(initialEntries: string[] = ["/"]) {
  let currentLocation = { pathname: "", search: "" };
  let routerNavigate!: ReturnType<typeof useNavigate>;

  function RouterProbe() {
    currentLocation = useLocation();
    routerNavigate = useNavigate();
    return null;
  }

  const utils = render(
    <MemoryRouter initialEntries={initialEntries}>
      <RouterProbe />
      <App />
    </MemoryRouter>,
  );

  return {
    ...utils,
    getUrl: () => `${currentLocation.pathname}${currentLocation.search}`,
    goBack: () => {
      act(() => {
        routerNavigate(-1);
      });
    },
    goForward: () => {
      act(() => {
        routerNavigate(1);
      });
    },
  };
}

describe("URL 라우팅과 브라우저 뒤로·앞으로 가기 시나리오", () => {
  it("필터·보기 변경 후 브라우저 뒤로·앞으로 가기를 누르면 이전 필터와 선택 기사가 복원된다", async () => {
    setupMockFetch({
      briefing: createMockBriefing({
        articles: [
          createMockArticle({ id: 101, source: "GeekNews", title: "브리핑 기사 101" }),
        ],
      }),
      articles: [
        createMockArticle({ id: 1, source: "GeekNews", title: "GeekNews 기사 1" }),
        createMockArticle({ id: 2, source: "arXiv", title: "arXiv 기사 2" }),
      ],
    });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/"]);
    const sidebar = view.container.querySelector("aside") as HTMLElement;
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(view.getUrl()).toBe("/briefing/101");
      expect(within(detailPanel).getByRole("heading", { name: "브리핑 기사 101" })).toBeInTheDocument();
    });

    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/1");
      expect(within(detailPanel).getByRole("heading", { name: "GeekNews 기사 1" })).toBeInTheDocument();
    });

    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/1?source=GeekNews");
      expect(screen.getByText("출처: GeekNews")).toBeInTheDocument();
    });

    await user.click(within(sidebar).getByRole("button", { name: /^arXiv/ }));
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/2?source=arXiv");
      expect(screen.getByText("출처: arXiv")).toBeInTheDocument();
      expect(within(detailPanel).getByRole("heading", { name: "arXiv 기사 2" })).toBeInTheDocument();
    });

    // 브라우저 뒤로 가기 1회: 이전 GeekNews 필터 화면으로 복원
    view.goBack();
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/1?source=GeekNews");
      expect(screen.getByText("출처: GeekNews")).toBeInTheDocument();
      expect(within(detailPanel).getByRole("heading", { name: "GeekNews 기사 1" })).toBeInTheDocument();
    });

    // 브라우저 뒤로 가기 2회: 전체 기사 목록(필터 없음)으로 복원
    view.goBack();
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/1");
      expect(screen.queryByText("적용된 필터:")).not.toBeInTheDocument();
    });

    // 브라우저 뒤로 가기 3회: 브리핑 화면으로 복원 (데스크톱 자동 선택 replace로 막히지 않음)
    view.goBack();
    await waitFor(() => {
      expect(view.getUrl()).toBe("/briefing/101");
      expect(within(detailPanel).getByRole("heading", { name: "브리핑 기사 101" })).toBeInTheDocument();
    });

    // 브라우저 앞으로 가기: 전체 기사 화면 재진입
    view.goForward();
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles/1");
      expect(within(detailPanel).getByRole("heading", { name: "GeekNews 기사 1" })).toBeInTheDocument();
    });
  });

  it("모바일에서 브리핑 → 전체 기사 → 상세 진입 후 앱 내 뒤로 버튼은 히스토리를 쌓지 않고 목록으로 돌아간다", async () => {
    setViewportCompact(true);
    setupMockFetch({
      briefing: createMockBriefing({
        articles: [createMockArticle({ id: 101, title: "모바일 브리핑 기사" })],
      }),
      articles: [
        createMockArticle({ id: 1, source: "GeekNews", title: "모바일 피드 기사 1" }),
        createMockArticle({ id: 2, source: "GeekNews", title: "모바일 피드 기사 2" }),
      ],
    });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/briefing"]);
    const sidebar = view.container.querySelector("aside") as HTMLElement;

    await waitFor(() => {
      expect(screen.getByText("모바일 브리핑 기사")).toBeInTheDocument();
    });

    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    await waitFor(() => {
      expect(view.getUrl()).toBe("/articles");
      expect(screen.getByText("모바일 피드 기사 2")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /모바일 피드 기사 2/ }));
    expect(view.getUrl()).toBe("/articles/2");
    expect(screen.getByRole("banner")).toHaveTextContent("← 목록");

    // 앱 내 ← 목록 버튼은 navigate(-1)로 동작해 /articles 로 복귀하며 새 히스토리를 쌓지 않는다
    await user.click(screen.getByRole("button", { name: "기사 목록으로 돌아가기" }));
    expect(view.getUrl()).toBe("/articles");
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();

    // 직전 엔트리가 /briefing 이므로 뒤로 가기 시 /articles/2 가 아니라 /briefing 으로 돌아간다
    view.goBack();
    await waitFor(() => {
      expect(view.getUrl()).toBe("/briefing");
      expect(screen.getByText("모바일 브리핑 기사")).toBeInTheDocument();
    });
  });

  it("모바일 상세 URL에서 브라우저 뒤로 가기를 누르면 쿼리가 유지된 목록으로 복귀한다", async () => {
    setViewportCompact(true);
    const pagedArticles = Array.from({ length: 25 }, (_, i) =>
      createMockArticle({
        id: i + 1,
        source: "GeekNews",
        title: `AI 검색 결과 ${i + 1}`,
        summary: "AI 요약",
      }),
    );
    setupMockFetch({ articles: pagedArticles });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/articles?source=GeekNews&q=AI&page=2"]);

    await waitFor(() => {
      expect(screen.getByText("AI 검색 결과 21")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /AI 검색 결과 22/ }));
    expect(view.getUrl()).toBe("/articles/22?source=GeekNews&q=AI&page=2");
    expect(screen.getByRole("banner")).toBeInTheDocument();

    view.goBack();
    expect(view.getUrl()).toBe("/articles?source=GeekNews&q=AI&page=2");
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.getByText("AI 검색 결과 21")).toBeInTheDocument();
  });

  it("목록에 없는 상세 URL로 직접 진입하면 단건 API를 조회하고, 앱 내 뒤로 버튼은 쿼리를 유지한 목록 URL로 이동한다", async () => {
    setViewportCompact(true);
    const mock = setupMockFetch({
      articles: [createMockArticle({ id: 1, source: "GeekNews", title: "1페이지 기사" })],
      articleById: (id) =>
        id === 777
          ? createMockArticle({
              id: 777,
              source: "GeekNews",
              major_category: "AI",
              title: "직접 진입 단건 조회 기사 777",
              content: "단건 API 본문",
            })
          : { status: 404 },
    });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/articles/777?source=GeekNews&page=2"]);
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(
        within(detailPanel).getByRole("heading", { name: "직접 진입 단건 조회 기사 777" }),
      ).toBeInTheDocument();
    });
    expect(mock.calls).toContain("/api/articles/777");
    expect(screen.getByRole("banner")).toHaveTextContent("GeekNews · AI");

    // 직접 진입이므로 ← 목록 클릭 시 쿼리가 유지된 목록 URL로 이동한다
    await user.click(screen.getByRole("button", { name: "기사 목록으로 돌아가기" }));
    expect(view.getUrl()).toBe("/articles?source=GeekNews&page=2");
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("존재하지 않는 기사(404)나 단건 조회 오류 URL로 직접 진입하면 한국어 안내 메시지를 표시한다", async () => {
    setViewportCompact(true);
    const mock = setupMockFetch({
      articles: [],
      articleById: { status: 404 },
    });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/articles/999999?source=GeekNews"]);
    const detailPanel = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(within(detailPanel).getByText("요청한 기사를 찾을 수 없습니다.")).toBeInTheDocument();
    });
    expect(detailPanel).not.toHaveStyle({ display: "none" });
    expect(screen.getByRole("banner")).toHaveTextContent("기사 상세");

    await user.click(screen.getByRole("button", { name: "기사 목록으로 돌아가기" }));
    expect(view.getUrl()).toBe("/articles?source=GeekNews");

    // 500 오류 확인
    view.unmount();
    mock.setArticleById({ status: 500 });
    renderRoutedApp(["/articles/888888"]);
    await waitFor(() => {
      expect(
        within(screen.getByLabelText("기사 상세")).getByText(
          "기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("정의되지 않은 경로와 잘못된 ID 경로는 /briefing으로 이동하고 잘못된 page 쿼리는 1페이지로 보정한다", async () => {
    const mock = setupMockFetch({
      briefing: createMockBriefing({
        articles: [createMockArticle({ id: 101, title: "리다이렉트 후 브리핑 기사" })],
      }),
    });

    const unknownView = renderRoutedApp(["/not-a-route"]);
    await waitFor(() => {
      expect(unknownView.getUrl()).toBe("/briefing/101");
      expect(
        within(screen.getByLabelText("기사 상세")).getByRole("heading", { name: "리다이렉트 후 브리핑 기사" }),
      ).toBeInTheDocument();
    });
    unknownView.unmount();

    const invalidIdView = renderRoutedApp(["/articles/abc"]);
    await waitFor(() => {
      expect(invalidIdView.getUrl()).toBe("/briefing/101");
    });
    invalidIdView.unmount();

    renderRoutedApp(["/articles?page=abc&source=&q="]);
    await waitFor(() => {
      expect(mock.calls).toContain("/api/articles?page=1&size=20");
    });
  });

  it("라우트와 기사 조회 상태에 맞게 브라우저 탭 제목(document.title)을 갱신한다", async () => {
    setViewportCompact(true);
    const mock = setupMockFetch({
      briefing: createMockBriefing({
        articles: [createMockArticle({ id: 101, title: "모바일 브리핑 기사" })],
      }),
      articles: [
        createMockArticle({ id: 1, source: "GeekNews", title: "GeekNews 에이전트 기사", content: "에이전트 본문" }),
        createMockArticle({ id: 2, source: "arXiv", title: "arXiv 논문 기사", content: "에이전트 논문" }),
      ],
      articleById: { status: 404 },
    });
    const user = userEvent.setup();

    const view = renderRoutedApp(["/briefing"]);
    await waitFor(() => {
      expect(document.title).toBe("오늘의 AI 브리핑 - 뉴스 뷰어");
    });

    const sidebar = view.container.querySelector("aside") as HTMLElement;
    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    await user.click(within(sidebar).getByRole("button", { name: "전체 기사" }));
    await waitFor(() => {
      expect(document.title).toBe("기사 피드 - 뉴스 뷰어");
    });

    await user.click(within(sidebar).getByRole("button", { name: "필터" }));
    await user.click(within(sidebar).getByRole("button", { name: /^GeekNews/ }));
    await waitFor(() => {
      expect(document.title).toBe("GeekNews - 기사 피드 - 뉴스 뷰어");
    });

    const searchInput = screen.getByPlaceholderText("기사 제목, 본문으로 검색...");
    await user.type(searchInput, "에이전트{Enter}");
    await waitFor(() => {
      expect(document.title).toBe("GeekNews · '에이전트' - 기사 피드 - 뉴스 뷰어");
    });

    await user.click(screen.getByRole("button", { name: /GeekNews 에이전트 기사/ }));
    await waitFor(() => {
      expect(document.title).toBe("GeekNews 에이전트 기사 - 뉴스 뷰어");
    });

    view.goBack();
    await waitFor(() => {
      expect(document.title).toBe("GeekNews · '에이전트' - 기사 피드 - 뉴스 뷰어");
    });

    view.unmount();
    const notFoundView = renderRoutedApp(["/articles/999999"]);
    await waitFor(() => {
      expect(document.title).toBe("기사를 찾을 수 없음 - 뉴스 뷰어");
    });
    notFoundView.unmount();

    mock.setArticleById({ status: 500 });
    renderRoutedApp(["/articles/888888"]);
    await waitFor(() => {
      expect(document.title).toBe("기사를 불러오지 못함 - 뉴스 뷰어");
    });
  });

  it("없는 기사(404)와 조회 오류 상세 화면에서 목록으로 돌아가기 및 다시 시도로 복구한다", async () => {
    // 1. 데스크톱 404: 안내 문구 + 목록으로 돌아가기(다시 시도 없음) -> 쿼리 유지한 목록으로 이동 후 첫 기사 자동 선택
    const pagedArticles = Array.from({ length: 22 }, (_, i) =>
      createMockArticle({
        id: i + 1,
        source: "GeekNews",
        title: `GeekNews AI 기사 ${i + 1}`,
        content: "AI 본문",
      }),
    );
    const mock = setupMockFetch({
      articles: pagedArticles,
      articleById: { status: 404 },
    });
    const user = userEvent.setup();

    const desktop404View = renderRoutedApp(["/articles/999999?source=GeekNews&q=AI&page=2"]);
    const desktopDetail = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(within(desktopDetail).getByText("요청한 기사를 찾을 수 없습니다.")).toBeInTheDocument();
    });
    expect(within(desktopDetail).queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();

    await user.click(within(desktopDetail).getByRole("button", { name: "목록으로 돌아가기" }));
    await waitFor(() => {
      expect(desktop404View.getUrl()).toBe("/articles/21?source=GeekNews&q=AI&page=2");
    });
    desktop404View.unmount();

    // 2. 모바일 네트워크/500 오류: 다시 시도 클릭 시 단건 재조회 성공, 다른 404에서 목록으로 돌아가기 시 쿼리 유지 목록 복귀
    setViewportCompact(true);
    mock.setArticleById(new Error("Network error"));
    const mobileErrView = renderRoutedApp(["/articles/777?source=GeekNews&q=AI&page=2"]);
    const mobileDetail = screen.getByLabelText("기사 상세");

    await waitFor(() => {
      expect(
        within(mobileDetail).getByText("기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요."),
      ).toBeInTheDocument();
    });
    expect(within(mobileDetail).getByRole("button", { name: "목록으로 돌아가기" })).toBeInTheDocument();

    mock.setArticleById(
      createMockArticle({
        id: 777,
        source: "GeekNews",
        title: "재시도로 불러온 기사 777",
        content: "복구된 본문",
      }),
    );
    await user.click(within(mobileDetail).getByRole("button", { name: "다시 시도" }));
    await waitFor(() => {
      expect(within(mobileDetail).getByRole("heading", { name: "재시도로 불러온 기사 777" })).toBeInTheDocument();
    });
    mobileErrView.unmount();

    mock.setArticleById({ status: 404 });
    const mobile404View = renderRoutedApp(["/articles/999999?source=GeekNews&q=AI&page=2"]);
    const mobile404Detail = screen.getByLabelText("기사 상세");
    await waitFor(() => {
      expect(within(mobile404Detail).getByText("요청한 기사를 찾을 수 없습니다.")).toBeInTheDocument();
    });
    await user.click(within(mobile404Detail).getByRole("button", { name: "목록으로 돌아가기" }));
    expect(mobile404View.getUrl()).toBe("/articles?source=GeekNews&q=AI&page=2");
  });
});
