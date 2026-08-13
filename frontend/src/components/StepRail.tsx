/**
 * 智能体执行流程图组件
 * 按 LangGraph 节点拓扑展示各步骤状态（17 节点，与后端 graph.py 对齐）
 */
import { Check, Circle, LoaderCircle, RotateCw, X } from "lucide-react";
import { cn } from "../lib/format";
import type { ProgressStatus, StepState } from "../types/agent";

type FlowStatus = ProgressStatus | "pending";

type FlowNode = {
  step: string;
  x: number;
  y: number;
  w?: number;
  /** 英文 sublabel（mono 小字，对应后端节点名） */
  eng?: string;
  /** 条件触发节点（如 dream，未触发时虚线展示） */
  dashed?: boolean;
};

const nodes: FlowNode[] = [
  { step: "分析意图", x: 410, y: 20, eng: "classify_intent" },
  { step: "澄清追问", x: 150, y: 122, eng: "ask_clarification" },
  { step: "抽取关键词", x: 410, y: 122, eng: "extract_keywords" },
  { step: "召回字段信息", x: 150, y: 214, eng: "recall_column" },
  { step: "召回指标信息", x: 410, y: 214, eng: "recall_metric" },
  { step: "召回字段取值", x: 670, y: 214, eng: "recall_value" },
  { step: "合并召回信息", x: 410, y: 316, eng: "merge_retrieved_info" },
  { step: "过滤指标信息", x: 290, y: 420, eng: "filter_metric" },
  { step: "过滤表信息", x: 530, y: 420, eng: "filter_table" },
  { step: "增加额外上下文", x: 410, y: 524, w: 176, eng: "add_extra_context" },
  { step: "压缩对话记忆", x: 410, y: 628, w: 176, eng: "dream", dashed: true },
  { step: "生成SQL", x: 410, y: 732, eng: "generate_sql" },
  { step: "校验SQL", x: 410, y: 836, eng: "validate_sql" },
  { step: "校正SQL", x: 670, y: 836, eng: "correct_sql" },
  { step: "语义校验", x: 410, y: 940, eng: "semantic_validate" },
  { step: "执行SQL", x: 410, y: 1044, eng: "run_sql" },
  { step: "生成结果解读", x: 410, y: 1148, eng: "summarize_result" },
];

const connectors = [
  // 分析意图 → 澄清追问 (意图模糊)
  "M410 68 L410 90 L150 90 L150 116",
  // 分析意图 → 抽取关键词 (主路径)
  "M410 68 L410 116",
  // 抽取关键词 → 三路召回
  "M410 170 L410 186 L150 186 L150 208",
  "M410 170 L410 208",
  "M410 170 L410 186 L670 186 L670 208",
  // 三路召回 → 合并
  "M150 262 L150 280 L410 280 L410 310",
  "M410 262 L410 310",
  "M670 262 L670 280 L410 280 L410 310",
  // 合并 → 过滤
  "M410 364 L410 384 L290 384 L290 414",
  "M410 364 L410 384 L530 384 L530 414",
  // 过滤 → 增加上下文
  "M290 468 L290 488 L410 488 L410 518",
  "M530 468 L530 488 L410 488 L410 518",
  // 增加上下文 → 压缩对话记忆
  "M410 572 L410 622",
  // 压缩对话记忆 → 生成SQL
  "M410 676 L410 726",
  // 生成SQL → 校验SQL
  "M410 780 L410 830",
  // 校验SQL → 语义校验 (无误)
  "M410 884 L410 934",
  // 校验SQL → 校正SQL (有误)
  "M488 860 L586 860",
  // 校正SQL → 语义校验 (回主链)
  "M670 884 L670 902 L410 902 L410 934",
  // 语义校验 → 执行SQL (校验通过)
  "M410 988 L410 1038",
  // 语义校验 → 校正SQL (校验失败 — 右出直上，对准SQL的L)
  "M488 988 L710 988 L710 884",
  // 执行SQL → 生成结果解读
  "M410 1092 L410 1142",
];

const branchLabels = [
  { text: "意图模糊", x: 270, y: 82 },
  { text: "有误", x: 530, y: 852 },
  { text: "无误", x: 366, y: 906 },
  { text: "校验失败", x: 540, y: 978 },
  { text: "校验通过", x: 340, y: 1004 },
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

  if (status === "retry") {
    return <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />;
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
  const dashedPending = node.dashed && status === "pending";

  return (
    <div
      className="absolute -translate-x-1/2"
      style={{ left: node.x, top: node.y, width }}
    >
      <div
        className={cn(
          "flex h-12 items-center gap-2.5 rounded-md border px-3 transition",
          status === "pending" &&
            (dashedPending
              ? "border-dashed border-ink/20 bg-white/40 text-ink/40"
              : "border-ink/10 bg-white/55 text-ink/45"),
          status === "running" && "border-brass/45 bg-brass/15 text-ink",
          status === "retry" && "border-brass/45 bg-brass/15 text-ink",
          status === "success" && "border-moss/25 bg-moss/10 text-ink",
          status === "error" && "border-tomato/35 bg-tomato/10 text-tomato",
        )}
      >
        <span
          className={cn(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full",
            status === "pending" && "bg-ink/5 text-ink/35",
            status === "running" && "bg-brass/20 text-brass",
            status === "retry" && "bg-brass/20 text-brass",
            status === "success" && "bg-moss/15 text-moss",
            status === "error" && "bg-tomato/15 text-tomato",
          )}
        >
          <NodeIcon status={status} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate text-[13px] font-semibold">{node.step}</span>
          {node.eng && (
            <span className="truncate font-mono text-[10px] text-ink/40">{node.eng}</span>
          )}
        </span>
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
        <div className="font-mono text-[11px] uppercase tracking-wider text-ink/45">LangGraph</div>
      </div>

      <div className="overflow-x-auto">
        <div className="relative mx-auto h-[1200px] w-[820px]">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 820 1200"
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
                <path d="M0 0 L8 4 L0 8 Z" fill="rgba(20,17,14,0.45)" />
              </marker>
            </defs>
            {connectors.map((path) => (
              <path
                key={path}
                d={path}
                stroke="rgba(20,17,14,0.35)"
                strokeWidth="1.5"
                markerEnd="url(#flow-arrow)"
              />
            ))}
            {branchLabels.map((label) => (
              <g key={label.text}>
                <rect
                  x={label.x - 28}
                  y={label.y - 13}
                  width={56}
                  height={20}
                  rx={4}
                  fill="#faf8f4"
                  opacity={0.92}
                />
                <text
                  x={label.x}
                  y={label.y}
                  fill="rgba(20,17,14,0.5)"
                  fontSize="11"
                  fontWeight="500"
                  letterSpacing="0.06em"
                  textAnchor="middle"
                  dominantBaseline="central"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {label.text}
                </text>
              </g>
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
