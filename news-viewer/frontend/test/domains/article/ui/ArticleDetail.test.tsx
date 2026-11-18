import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ArticleDetail from "../../../../src/domains/article/ui/ArticleDetail.tsx";

describe("기사 상세 패널 오류 및 빈 상태 복구 수단", () => {
  it("없는 기사(404) 상태에서는 안내 문구와 목록으로 돌아가기 버튼만 표시한다", async () => {
    const onBackToList = vi.fn();
    const onRetry = vi.fn();
    const user = userEvent.setup();

    render(
      <ArticleDetail
        selected={null}
        isCompact={true}
        emptyMessage="요청한 기사를 찾을 수 없습니다."
        forceShowOnCompact={true}
        errorKind="not_found"
        onBackToList={onBackToList}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("요청한 기사를 찾을 수 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();

    const backButton = screen.getByRole("button", { name: "목록으로 돌아가기" });
    await user.click(backButton);
    expect(onBackToList).toHaveBeenCalledTimes(1);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("단건 조회 오류 상태에서는 다시 시도와 목록으로 돌아가기 버튼을 모두 제공한다", async () => {
    const onBackToList = vi.fn();
    const onRetry = vi.fn();
    const user = userEvent.setup();

    render(
      <ArticleDetail
        selected={null}
        isCompact={false}
        emptyMessage="기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요."
        errorKind="error"
        onBackToList={onBackToList}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("기사를 불러오지 못했습니다. 서버 연결을 확인해 주세요.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "목록으로 돌아가기" }));
    expect(onBackToList).toHaveBeenCalledTimes(1);
  });

  it("일반 빈 상태(선택 대기·로딩)에서는 복구 버튼을 표시하지 않는다", () => {
    render(
      <ArticleDetail
        selected={null}
        isCompact={false}
        emptyMessage="기사를 선택하세요"
        errorKind="none"
        onBackToList={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("기사를 선택하세요")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "목록으로 돌아가기" })).not.toBeInTheDocument();
  });
});
