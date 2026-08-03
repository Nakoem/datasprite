/**
 * 聊天消息气泡组件
 * 组合展示用户问题、智能体回复、执行流程和结果表格
 * 改用 DaisyUI chat 组件：chat-start/chat-end + chat-bubble
 */
import { AlertTriangle, Bot, Copy, RefreshCw, UserRound } from "lucide-react";
import { ChartView } from "./ChartView";
import { ClarificationPanel } from "./ClarificationPanel";
import { SourceCard } from "./SourceCard";
import { StepRail } from "./StepRail";
import { SummaryCard } from "./SummaryCard";
import { cn, formatTime, toClipboardText } from "../lib/format";
import { showToast } from "../lib/toast";
import type { ChatMessage } from "../types/agent";

type MessageBubbleProps = {
  message: ChatMessage;
  onClarificationSelect?: (question: string) => void;
  onRetry?: () => void;
};

export function MessageBubble({ message, onClarificationSelect, onRetry }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const hasResult = message.result !== undefined;

  const copy = async () => {
    const text = message.result ? toClipboardText(message.result) : message.content;
    try {
      await navigator.clipboard.writeText(text);
      showToast("已复制到剪贴板");
    } catch {
      showToast("复制失败，请重试", "error");
    }
  };

  return (
    <article className={cn("group chat", isUser ? "chat-end" : "chat-start")}>
      {!isUser && (
        <div className="chat-image avatar">
          <div className="grid h-9 w-9 place-items-center rounded-full bg-ink text-parchment">
            <Bot className="h-4 w-4" aria-hidden="true" />
          </div>
        </div>
      )}

      <div
        className={cn(
          "chat-bubble shadow-line",
          isUser
            ? "chat-bubble-primary text-primary-content"
            : "border border-ink/10 bg-white/80 text-ink backdrop-blur",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
          {!isUser && message.status !== "streaming" && (
            <button
              type="button"
              onClick={copy}
              className="btn btn-circle btn-ghost btn-xs shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100"
              title="复制"
              aria-label="复制"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>

        {message.error && (
          <div className="alert alert-error alert-soft mt-3 py-3 text-sm">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">查询未成功</p>
              <p className="mt-1 opacity-75">{message.error}</p>
            </div>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="btn btn-sm btn-outline btn-error"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                重试
              </button>
            )}
          </div>
        )}

        {!isUser && message.clarification && onClarificationSelect && (
          <ClarificationPanel
            questions={message.clarification}
            onSelect={onClarificationSelect}
          />
        )}

        {!isUser && (
          <SummaryCard
            summary={message.summary}
            metricDefinitions={message.metricDefinitions}
          />
        )}
        {!isUser && <SourceCard columnSources={message.columnSources} />}

        {/* 骨架屏：流式执行中还没出结果时给个占位 */}
        {!isUser && isStreaming && !hasResult && (
          <div className="mt-4 space-y-3">
            <div className="skeleton h-5 w-2/3 rounded" />
            <div className="flex h-48 w-full items-center justify-center rounded border border-dashed border-ink/15 bg-ink/[0.02]">
              <div className="flex flex-col items-center gap-3">
                <span className="loading loading-spinner loading-md text-moss/50" />
                <span className="text-xs text-ink/35">正在分析数据…</span>
              </div>
            </div>
            <div className="skeleton h-4 w-1/3 rounded" />
          </div>
        )}

        {!isUser && <StepRail steps={message.steps} />}
        {!isUser && message.result !== undefined && <ChartView data={message.result} query={message.content} />}
      </div>

      <div className={cn("chat-footer opacity-60", isUser && "text-right")}>
        <time className="text-xs">{formatTime(message.createdAt)}</time>
      </div>

      {isUser && (
        <div className="chat-image avatar">
          <div className="grid h-9 w-9 place-items-center rounded-full bg-moss text-white">
            <UserRound className="h-4 w-4" aria-hidden="true" />
          </div>
        </div>
      )}
    </article>
  );
}
