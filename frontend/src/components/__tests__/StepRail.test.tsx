/**
 * StepRail 组件测试
 *
 * 测试执行流程图的渲染、空态、状态图标。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StepRail } from "../StepRail";
import type { StepState } from "../../types/agent";

const ALL_STEPS: StepState[] = [
  { step: "抽取关键词", status: "success", updatedAt: Date.now() },
  { step: "召回字段信息", status: "success", updatedAt: Date.now() },
  { step: "召回指标信息", status: "success", updatedAt: Date.now() },
  { step: "召回字段取值", status: "success", updatedAt: Date.now() },
  { step: "合并召回信息", status: "success", updatedAt: Date.now() },
  { step: "过滤指标信息", status: "running", updatedAt: Date.now() },
];

const ERROR_STEPS: StepState[] = [
  { step: "抽取关键词", status: "success", updatedAt: Date.now() },
  { step: "生成SQL", status: "error", updatedAt: Date.now() },
];

describe("StepRail", () => {
  it("空步骤时返回 null，不渲染任何内容", () => {
    const { container } = render(<StepRail steps={[]} />);
    expect(container.innerHTML).toBe("");
  });

  it("渲染所有 12 个流程节点", () => {
    render(<StepRail steps={ALL_STEPS} />);

    const nodeNames = [
      "抽取关键词", "召回字段信息", "召回指标信息", "召回字段取值",
      "合并召回信息", "过滤指标信息", "过滤表信息", "增加额外上下文",
      "生成SQL", "校验SQL", "校正SQL", "执行SQL",
    ];

    for (const name of nodeNames) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("显示执行流程标题", () => {
    render(<StepRail steps={ALL_STEPS} />);
    expect(screen.getByText("执行流程")).toBeInTheDocument();
    expect(screen.getByText("LangGraph")).toBeInTheDocument();
  });

  it("error 步骤正确渲染，未传步骤以 pending 显示", () => {
    render(<StepRail steps={ERROR_STEPS} />);

    // success 步骤存在
    expect(screen.getByText("抽取关键词")).toBeInTheDocument();
    // error 步骤存在
    expect(screen.getByText("生成SQL")).toBeInTheDocument();
    // 未传的步骤也渲染（以 pending 状态）
    expect(screen.getByText("校验SQL")).toBeInTheDocument();
  });
});
