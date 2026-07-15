/**
 * 结果解读卡片
 *
 * 在查询结果图表上方展示 AI 生成的一句话数据洞察，
 * 以及本次查询涉及的指标口径说明（可折叠展开）。
 * 面向非技术业务用户，帮助他们理解数据含义。
 */
import { ChevronDown, Lightbulb } from "lucide-react";
import { useState } from "react";

type MetricDef = {
  name: string;
  description: string;
};

type SummaryCardProps = {
  summary: string | null | undefined;
  metricDefinitions?: MetricDef[];
};

export function SummaryCard({ summary, metricDefinitions }: SummaryCardProps) {
  const [metricsOpen, setMetricsOpen] = useState(false);
  const hasSummary = typeof summary === "string" && summary.length > 0;
  const hasMetrics = metricDefinitions && metricDefinitions.length > 0;

  // 既没摘要也没口径说明 → 不渲染
  if (!hasSummary && !hasMetrics) return null;

  return (
    <div className="mt-4 space-y-0">
      {/* ── AI 摘要 ── */}
      {hasSummary && (
        <div className="border border-moss/20 bg-moss/8 px-4 py-3">
          <div className="mb-1.5 flex items-center gap-2 text-sm text-ink/70">
            <Lightbulb className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
            <span>分析摘要</span>
          </div>
          <p className="text-sm leading-6 text-ink/80">{summary}</p>
        </div>
      )}

      {/* ── 口径说明（可折叠） ── */}
      {hasMetrics && (
        <div className="border border-ink/10 bg-white/70">
          <button
            type="button"
            onClick={() => setMetricsOpen((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-ink/65 transition hover:text-ink/85 focus:outline-none focus:ring-2 focus:ring-moss/40"
            aria-expanded={metricsOpen}
          >
            <span>
              口径说明
              <span className="ml-1.5 text-xs text-ink/40">（{metricDefinitions.length}项）</span>
            </span>
            <ChevronDown
              className={`h-4 w-4 shrink-0 transition ${metricsOpen ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
          </button>
          {metricsOpen && (
            <dl className="border-t border-ink/10 px-4 py-3 space-y-2.5">
              {metricDefinitions.map((m) => (
                <div key={m.name}>
                  <dt className="text-sm font-semibold text-ink/80">{m.name}</dt>
                  <dd className="mt-0.5 text-sm leading-6 text-ink/55">
                    {m.description || "暂无描述"}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
