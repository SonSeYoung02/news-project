import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ArticleList from "../../../../src/domains/article/ui/ArticleList.tsx";
import { createMockArticle } from "../../../helpers/mockApi.ts";

describe("기사 목록 적용된 필터 바", () => {
  it("출처 없이 검색어만 적용되면 적용된 필터 바에 검색 칩을 표시하고 클릭 시 검색 해제 콜백을 호출한다", async () => {
    const onResetSearch = vi.fn();
    const user = userEvent.setup();

    render(
      <ArticleList
        articles={[createMockArticle({ id: 1, title: "검색 결과 기사" })]}
        loading={false}
        error=""
        search="에이전트"
        selectedSource=""
        selectedId={undefined}
        onSelectArticle={vi.fn()}
        onRemoveSource={vi.fn()}
        onResetFilters={vi.fn()}
        onResetSearch={onResetSearch}
        page={1}
        totalPages={1}
        onPageChange={vi.fn()}
      />,
    );

    expect(screen.getByText("적용된 필터:")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^출처:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "필터 초기화" })).not.toBeInTheDocument();

    const searchChip = screen.getByRole("button", { name: "검색: 에이전트 필터 해제" });
    expect(searchChip).toHaveTextContent("검색: 에이전트");
    await user.click(searchChip);
    expect(onResetSearch).toHaveBeenCalledTimes(1);
  });

  it("출처와 검색어가 함께 적용되면 출처 칩 옆에 검색 칩과 필터 초기화 버튼을 모두 표시한다", async () => {
    const onRemoveSource = vi.fn();
    const onResetSearch = vi.fn();
    const onResetFilters = vi.fn();
    const user = userEvent.setup();

    render(
      <ArticleList
        articles={[createMockArticle({ id: 1, source: "GeekNews", title: "검색 결과 기사" })]}
        loading={false}
        error=""
        search="LLM"
        selectedSource="GeekNews"
        selectedId={undefined}
        onSelectArticle={vi.fn()}
        onRemoveSource={onRemoveSource}
        onResetFilters={onResetFilters}
        onResetSearch={onResetSearch}
        page={1}
        totalPages={1}
        onPageChange={vi.fn()}
      />,
    );

    expect(screen.getByText("적용된 필터:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "출처: GeekNews 필터 해제" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "검색: LLM 필터 해제" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "필터 초기화" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "검색: LLM 필터 해제" }));
    expect(onResetSearch).toHaveBeenCalledTimes(1);
    expect(onRemoveSource).not.toHaveBeenCalled();
    expect(onResetFilters).not.toHaveBeenCalled();
  });
});
