/**
 * 结果解读卡片
 *
 * 在查询结果图表上方展示 AI 生成的一句话数据洞察，
 * 以及本次查询涉及的指标口径说明（可折叠展开）。
 * 面向非技术业务用户，帮助他们理解数据含义。
 * 改用 DaisyUI alert-success + collapse（口径说明原生开合）。
 */
import { Calculator, Lightbulb } from "lucide-react";
import { BorderBeam } from "border-beam";

type MetricDef = {
  name: string;
  description: string;
};

type SummaryCardProps = {
  summary: string | null | undefined;
  metricDefinitions?: MetricDef[];
};

export function SummaryCard({ summary, metricDefinitions }: SummaryCardProps) {
  const hasSummary = typeof summary === "string" && summary.length > 0;
  const hasMetrics = metricDefinitions && metricDefinitions.length > 0;

  // 既没摘要也没口径说明 → 不渲染
  if (!hasSummary && !hasMetrics) return null;

  return (
    <div className="mt-4 space-y-3">
      {/* ── AI 摘要 ── */}
      {hasSummary && (
        <BorderBeam
          size="md"
          colorVariant="ocean"
          theme="light"
          strength={0.5}
          className="rounded-sm"
        >
          <div className="alert alert-success alert-soft gap-3">
            <Lightbulb className="h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <div className="mb-1 text-sm font-medium text-ink/70">分析摘要</div>
              <p className="text-sm leading-6 text-ink/80">{summary}</p>
            </div>
          </div>
        </BorderBeam>
      )}

      {/* ── 口径说明（可折叠，原生 checkbox 开合） ── */}
      {hasMetrics && (
        <div className="collapse collapse-arrow rounded-lg border border-ink/10 bg-white/70">
          <input type="checkbox" className="peer" />
          <div className="collapse-title flex items-center gap-2 text-sm text-ink/65">
            <Calculator className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
            口径说明
            <span className="text-xs text-ink/40">（{metricDefinitions.length}项）</span>
          </div>
          <div className="collapse-content px-4 pb-4">
            <dl className="space-y-2.5">
              {metricDefinitions.map((m) => (
                <div key={m.name}>
                  <dt className="text-sm font-semibold text-ink/80">{m.name}</dt>
                  <dd className="mt-0.5 text-sm leading-6 text-ink/55">
                    {m.description || "暂无描述"}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
