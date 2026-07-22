/**
 * Composer 组件测试
 *
 * 测试聊天输入区的核心交互：回车提交、Shift+Enter 换行、
 * 流式中断、禁用态。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "../Composer";

function renderComposer(overrides: Partial<Parameters<typeof Composer>[0]> = {}) {
  const props = {
    value: "",
    disabled: false,
    isStreaming: false,
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onStop: vi.fn(),
    ...overrides,
  };
  const view = render(<Composer {...props} />);
  return { ...view, props };
}

describe("Composer", () => {
  it("渲染 textarea 和发送按钮", () => {
    renderComposer();
    expect(
      screen.getByPlaceholderText("问一个电商数据问题..."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("发送")).toBeInTheDocument();
  });

  it("回车提交时调用 onSubmit，不换行", async () => {
    const { props } = renderComposer({ value: "统计销售" });
    const textarea = screen.getByPlaceholderText("问一个电商数据问题...");

    await userEvent.type(textarea, "{Enter}");

    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  it("Shift+Enter 换行，不提交", async () => {
    const user = userEvent.setup();
    const { props } = renderComposer({ value: "统计销售" });
    const textarea = screen.getByPlaceholderText("问一个电商数据问题...");

    await user.type(textarea, "{Shift>}{Enter}{/Shift}");

    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("流式输出中显示停止按钮", () => {
    renderComposer({ isStreaming: true });
    expect(screen.getByLabelText("停止")).toBeInTheDocument();
  });

  it("点击停止按钮调用 onStop", async () => {
    const user = userEvent.setup();
    const { props } = renderComposer({ isStreaming: true });

    await user.click(screen.getByLabelText("停止"));

    expect(props.onStop).toHaveBeenCalledOnce();
  });

  it("禁用时提交按钮不可点击", () => {
    renderComposer({ disabled: true });
    const button = screen.getByLabelText("发送");
    expect(button).toBeDisabled();
  });
});
