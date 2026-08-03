/**
 * 数据来源引用卡片
 *
 * 展示本次查询涉及的数据表及字段详情，
 * 让用户了解查询结果中每个数据点的来源。
 * 外层"数据来源"折叠 + 内层每表字段折叠（原生 checkbox 开合）。
 * 改用 DaisyUI collapse + badge-outline。
 */
import { Database } from "lucide-react";
import type { TableSource } from "../types/agent";

type SourceCardProps = {
  columnSources?: TableSource[];
};

const ROLE_LABEL: Record<string, string> = {
  fact: "事实表",
  dim: "维度表",
  dimension: "维度表",
};

export function SourceCard({ columnSources }: SourceCardProps) {
  const hasSources = columnSources && columnSources.length > 0;

  if (!hasSources) return null;

  return (
    <div className="collapse collapse-arrow mt-4 rounded-lg border border-ink/10 bg-white/70">
      <input type="checkbox" className="peer" />
      <div className="collapse-title flex items-center gap-2 text-sm text-ink/65">
        <Database className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
        数据来源
        <span className="text-xs text-ink/40">（{columnSources.length}个表）</span>
      </div>

      <div className="collapse-content px-3 pb-2">
        <div className="divide-y divide-ink/5">
          {columnSources.map((table) => {
            const roleLabel = ROLE_LABEL[table.role] || table.role;

            return (
              <div
                key={table.name}
                className="collapse collapse-sm collapse-arrow rounded-none border-0 py-0"
              >
                <input type="checkbox" className="peer" />
                <div className="collapse-title px-2 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-ink/80">
                        {table.name}
                      </span>
                      {roleLabel && (
                        <span className="badge badge-outline badge-sm shrink-0 border-ink/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink/45">
                          {roleLabel}
                        </span>
                      )}
                    </div>
                    {table.description && (
                      <p className="mt-0.5 truncate text-xs text-ink/50">
                        {table.description}
                      </p>
                    )}
                  </div>
                </div>

                <div className="collapse-content space-y-1.5 px-2 pb-2 pt-1">
                  {table.columns.length === 0 ? (
                    <p className="text-xs text-ink/40">暂无字段信息</p>
                  ) : (
                    table.columns.map((col) => (
                      <div
                        key={col.name}
                        className="flex items-start gap-3 rounded-sm bg-white/60 px-2.5 py-1.5"
                      >
                        <code className="shrink-0 font-mono text-xs font-semibold text-moss">
                          {col.name}
                        </code>
                        <span className="text-[10px] uppercase text-ink/35">
                          {col.type}
                        </span>
                        {col.description && (
                          <span className="min-w-0 flex-1 text-xs text-ink/55">
                            {col.description}
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
