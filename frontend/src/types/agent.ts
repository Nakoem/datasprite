/**
 * 智能体类型定义
 * 定义问数智能体前端使用的 SSE 事件、流程步骤、聊天消息和图表类型
 */

// ── SSE 事件 ──

export type ProgressStatus = "running" | "success" | "error";

export type ProgressEvent = {
  type: "progress";
  step: string;
  status: ProgressStatus;
};

export type ResultEvent = {
  type: "result";
  data: unknown;
};

export type ErrorEvent = {
  type: "error";
  message: string;
};

export type ClarificationEvent = {
  type: "clarification";
  questions: string[];
};

export type SummaryEvent = {
  type: "summary";
  summary: string | null;
  metrics: Array<{ name: string; description: string }>;
};

export type AgentEvent = ProgressEvent | ResultEvent | ErrorEvent | ClarificationEvent | SummaryEvent;

// ── 步骤 & 消息 ──

export type StepState = {
  step: string;
  status: ProgressStatus;
  updatedAt: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "streaming" | "done" | "error";
  steps?: StepState[];
  result?: unknown;
  error?: string;
  /** 意图澄清时的追问选项 */
  clarification?: string[];
  /** AI 结果摘要 */
  summary?: string | null;
  /** 指标口径说明 */
  metricDefinitions?: Array<{ name: string; description: string }>;
};

// ── 图表 ──

/** 自动检测的图表类型 */
export type ChartType = "line" | "bar" | "pie" | "stackedBar" | "area" | "heatmap" | "table";

/** 图表检测结果：描述从查询结果中分析出的可视化建议 */
export type ChartHint = {
  /** 推荐图表类型；null 表示数据不适合出图 */
  chartType: ChartType | null;
  /** 维度列名（x 轴 / 分类字段） */
  dimensionCol: string | null;
  /** 度量列名列表（y 轴 / 数值字段）；热力图时只含度量列 */
  measureCols: string[];
  /** 第二维度列名（热力图 Y 轴 / 多系列分组） */
  dimensionCol2?: string;
  /** 不适合出图时的原因说明 */
  reason?: string;
};

// ── 会话历史 ──

/** 会话列表项 */
export type Conversation = {
  id: string;
  title: string;
  createdAt: string | null;
  updatedAt: string | null;
};

/** 会话详情（含消息） */
export type ConversationDetail = {
  id: string;
  title: string;
  createdAt: string | null;
  updatedAt: string | null;
  messages: ChatMessage[];
};
