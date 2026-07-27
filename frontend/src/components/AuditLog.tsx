/**
 * 审计日志面板
 *
 * 展示会话中每次问数的执行轨迹：
 * - 用户问题 / 生成 SQL / 执行耗时 / 结果行数
 * - 每个节点的执行步骤和时间戳
 */
import {
  AlertTriangle,
  Clock,
  Database,
  RefreshCw,
  Search,
  Table2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchAuditTrail } from "../lib/agentApi";
import { formatTime } from "../lib/format";
import type { AuditTrailResponse } from "../types/agent";

type AuditLogProps = {
  conversationId: string;
};

type LoadState = "loading" | "loaded" | "error" | "empty";

export function AuditLog({ conversationId }: AuditLogProps) {
  const [state, setState] = useState<LoadState>("loading");
  const [data, setData] = useState<AuditTrailResponse | null>(null);
  const [error, setError] = useState<string>("");

  const load = useCallback(async () => {
    setState("loading");
    try {
      const result = await fetchAuditTrail(conversationId);
      if (result.entries.length === 0) {
        setState("empty");
      } else {
        setData(result);
        setState("loaded");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
      setState("error");
    }
  }, [conversationId]);

  useEffect(() => {
    load();
  }, [load]);

  if (state === "loading") {
    return (
      <div className="p-6 space-y-4">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="border border-ink/10 bg-white/70 p-5 space-y-3 animate-pulse"
          >
            <div className="h-4 w-3/4 bg-ink/10" />
            <div className="h-3 w-1/4 bg-ink/8" />
            <div className="h-20 bg-ink/6" />
          </div>
        ))}
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
        <AlertTriangle className="h-10 w-10 text-tomato/60" />
        <p className="text-sm text-ink/60">{error}</p>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 text-sm text-moss hover:underline focus:outline-none"
        >
          <RefreshCw className="h-4 w-4" />
          重试
        </button>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <Search className="h-10 w-10 text-ink/25" />
        <p className="text-sm text-ink/50">该会话暂无审计数据</p>
        <p className="text-xs text-ink/35">
          请先执行一次查询，审计日志将自动记录
        </p>
      </div>
    );
  }

  const entries = data?.entries ?? [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-2 text-sm text-ink/55">
        <Search className="h-4 w-4" />
        <span>共 {entries.length} 条审计记录</span>
      </div>

      {entries.map((entry, ei) => (
        <div
          key={ei}
          className="border border-ink/10 bg-white/80 overflow-hidden"
        >
          {/* 问题标题 */}
          <div className="bg-ink/[0.03] border-b border-ink/10 px-5 py-3">
            <p className="text-sm font-semibold text-ink/80">
              查询 #{ei + 1}
            </p>
            <p className="mt-1 text-sm text-ink/60">{entry.question}</p>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-ink/45">
              {entry.executionTimeMs != null && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {(entry.executionTimeMs / 1000).toFixed(1)}s
                </span>
              )}
              {entry.resultRowCount != null && (
                <span className="inline-flex items-center gap-1">
                  <Table2 className="h-3.5 w-3.5" />
                  {entry.resultRowCount} 行
                </span>
              )}
              {entry.startedAt && (
                <span>{formatTime(new Date(entry.startedAt).getTime())}</span>
              )}
            </div>
          </div>

          {/* 步骤表格 */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-ink/10 text-left text-ink/45">
                  <th className="px-5 py-2 font-medium w-16">步骤</th>
                  <th className="px-5 py-2 font-medium">节点</th>
                  <th className="px-5 py-2 font-medium w-16">状态</th>
                  <th className="px-5 py-2 font-medium w-36">时间</th>
                </tr>
              </thead>
              <tbody>
                {entry.steps.map((step) => (
                  <tr
                    key={step.stepOrder}
                    className="border-b border-ink/5 hover:bg-ink/[0.02]"
                  >
                    <td className="px-5 py-1.5 text-ink/40">
                      {step.stepOrder}
                    </td>
                    <td className="px-5 py-1.5 text-ink/70">
                      {step.stepName}
                    </td>
                    <td className="px-5 py-1.5">
                      <span className="inline-flex items-center gap-1 text-moss">
                        ✅
                      </span>
                    </td>
                    <td className="px-5 py-1.5 text-ink/40">
                      {step.timestamp
                        ? formatTime(new Date(step.timestamp).getTime())
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 生成 SQL */}
          {entry.sql && (
            <div className="border-t border-ink/10 bg-ink/[0.02] p-5">
              <div className="mb-2 flex items-center gap-2 text-xs text-ink/50">
                <Database className="h-3.5 w-3.5" />
                <span>生成的 SQL</span>
              </div>
              <pre className="overflow-x-auto whitespace-pre text-xs font-mono text-ink/70 leading-relaxed bg-white p-3 border border-ink/10">
                {entry.sql}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
