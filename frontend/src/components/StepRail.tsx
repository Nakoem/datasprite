/**
 * 智能体执行流程图组件
 * 按 LangGraph 节点拓扑展示各步骤状态
 */
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../lib/format";
import type { ProgressStatus, StepState } from "../types/agent";

type FlowStatus = ProgressStatus | "pending";

type FlowNode = {
  step: string;
  x: number;
  y: number;
  w?: number;
};

const nodes: FlowNode[] = [
  { step: "分析意图", x: 410, y: 20 },
  { step: "澄清追问", x: 150, y: 122 },
  { step: "抽取关键词", x: 410, y: 122 },
  { step: "召回字段信息", x: 150, y: 214 },
  { step: "召回指标信息", x: 410, y: 214 },
  { step: "召回字段取值", x: 670, y: 214 },
  { step: "合并召回信息", x: 410, y: 316 },
  { step: "过滤指标信息", x: 290, y: 420 },
  { step: "过滤表信息", x: 530, y: 420 },
  { step: "增加额外上下文", x: 410, y: 524, w: 176 },
  { step: "生成SQL", x: 410, y: 628 },
  { step: "校验SQL", x: 410, y: 732 },
  { step: "校正SQL", x: 670, y: 732 },
  { step: "语义校验", x: 410, y: 826 },
  { step: "执行SQL", x: 410, y: 930 },
  { step: "生成结果解读", x: 410, y: 1034 },
];

const connectors = [
  // 分析意图 → 澄清追问 (意图模糊)
  "M410 60 L410 90 L150 90 L150 116",
  // 分析意图 → 抽取关键词 (主路径)
  "M410 60 L410 116",
  // 抽取关键词 → 三路召回
  "M410 162 L410 186 L150 186 L150 208",
  "M410 162 L410 208",
  "M410 162 L410 186 L670 186 L670 208",
  // 三路召回 → 合并
  "M150 254 L150 280 L410 280 L410 310",
  "M410 254 L410 310",
  "M670 254 L670 280 L410 280 L410 310",
  // 合并 → 过滤
  "M410 356 L410 384 L290 384 L290 414",
  "M410 356 L410 384 L530 384 L530 414",
  // 过滤 → 增加上下文
  "M290 460 L290 488 L410 488 L410 518",
  "M530 460 L530 488 L410 488 L410 518",
  // 增加上下文 → 生成SQL
  "M410 564 L410 622",
  // 生成SQL → 校验SQL
  "M410 668 L410 726",
  // 校验SQL → 语义校验 (无误)
  "M410 772 L410 820",
  // 校验SQL → 校正SQL (有误)
  "M488 752 L586 752",
  // 校正SQL → 语义校验 (回主链)
  "M670 772 L670 798 L410 798 L410 820",
  // 语义校验 → 执行SQL (校验通过)
  "M410 866 L410 924",
  // 语义校验 → 校正SQL (校验失败 — 右出直上，对准SQL的L)
  "M488 866 L710 866 L710 772",
  // 执行SQL → 生成结果解读
  "M410 970 L410 1028",
];

const branchLabels = [
  { text: "意图模糊", x: 270, y: 82 },
    { text: "有误", x: 530, y: 744 },
  { text: "无误", x: 366, y: 800 },
  { text: "校验失败", x: 505, y: 856 },
  { text: "校验通过", x: 340, y: 900 },
];

function getStatusMap(steps: StepState[]) {
  return steps.reduce<Record<string, StepState>>((map, item) => {
    map[item.step] = item;
    return map;
  }, {});
}

function statusFor(step: string, map: Record<string, StepState>): FlowStatus {
  return map[step]?.status ?? "pending";
}

function NodeIcon({ status }: { status: FlowStatus }) {
  if (status === "running") {
    return <LoaderCircle className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />;
  }

  if (status === "success") {
    return <Check className="h-3.5 w-3.5" aria-hidden="true" />;
  }

  if (status === "error") {
    return <X className="h-3.5 w-3.5" aria-hidden="true" />;
  }

  return <Circle className="h-3.5 w-3.5" aria-hidden="true" />;
}

function FlowNodeCard({ node, status }: { node: FlowNode; status: FlowStatus }) {
  const width = node.w ?? 156;

  return (
    <div
      className="absolute -translate-x-1/2"
      style={{ left: node.x, top: node.y, width }}
    >
      <div
        className={cn(
          "flex h-10 items-center gap-2 border px-3 text-sm font-semibold shadow-line transition",
          status === "pending" && "border-ink/10 bg-white/55 text-ink/45",
          status === "running" && "border-brass/45 bg-brass/15 text-ink",
          status === "success" && "border-moss/25 bg-moss/10 text-ink",
          status === "error" && "border-tomato/35 bg-tomato/10 text-tomato",
        )}
      >
        <span
          className={cn(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full",
            status === "pending" && "bg-ink/5 text-ink/35",
            status === "running" && "bg-brass/20 text-brass",
            status === "success" && "bg-moss/15 text-moss",
            status === "error" && "bg-tomato/15 text-tomato",
          )}
        >
          <NodeIcon status={status} />
        </span>
        <span className="min-w-0 flex-1 truncate">{node.step}</span>
      </div>
    </div>
  );
}

export function StepRail({ steps = [] }: { steps?: StepState[] }) {
  if (steps.length === 0) return null;

  const statusMap = getStatusMap(steps);

  return (
    <section className="mt-4 border border-ink/10 bg-white/40 px-3 py-4 shadow-line">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div className="text-sm font-semibold text-ink">执行流程</div>
        <div className="text-xs text-ink/45">LangGraph</div>
      </div>

      <div className="overflow-x-auto">
        <div className="relative mx-auto h-[1100px] w-[820px]">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 820 1100"
            fill="none"
            aria-hidden="true"
          >
            <defs>
              <marker
                id="flow-arrow"
                markerHeight="8"
                markerWidth="8"
                orient="auto"
                refX="6"
                refY="4"
              >
                <path d="M0 0 L8 4 L0 8 Z" fill="rgba(32,32,29,0.58)" />
              </marker>
            </defs>
            {connectors.map((path) => (
              <path
                key={path}
                d={path}
                stroke="rgba(32,32,29,0.5)"
                strokeWidth="1.5"
                markerEnd="url(#flow-arrow)"
              />
            ))}
            {branchLabels.map((label) => (
              <text
                key={label.text}
                x={label.x}
                y={label.y}
                fill="rgba(32,32,29,0.62)"
                fontSize="13"
                fontWeight="600"
              >
                {label.text}
              </text>
            ))}
          </svg>

          {nodes.map((node) => (
            <FlowNodeCard
              key={node.step}
              node={node}
              status={statusFor(node.step, statusMap)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
