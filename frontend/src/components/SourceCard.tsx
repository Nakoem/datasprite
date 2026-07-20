/**
 * 数据来源引用卡片
 *
 * 展示本次查询涉及的数据表及字段详情，
 * 让用户了解查询结果中每个数据点的来源。
 * 每个表可折叠展开其字段清单。
 */
import { ChevronDown, Database } from "lucide-react";
import { useState } from "react";
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
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});
  const hasSources = columnSources && columnSources.length > 0;

  if (!hasSources) return null;

  const toggleTable = (name: string) => {
    setExpandedTables((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  return (
    <div className="mt-4 border border-ink/10 bg-white/70">
      <button
        type="button"
        onClick={() => setSourcesOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm text-ink/65 transition hover:text-ink/85 focus:outline-none focus:ring-2 focus:ring-moss/40"
        aria-expanded={sourcesOpen}
      >
        <span className="inline-flex items-center gap-2">
          <Database className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
          数据来源
          <span className="text-xs text-ink/40">
            （{columnSources.length}个表）
          </span>
        </span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 transition ${sourcesOpen ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {sourcesOpen && (
        <div className="divide-y divide-ink/5 border-t border-ink/10">
          {columnSources.map((table) => {
          const isOpen = expandedTables[table.name] ?? false;
          const roleLabel = ROLE_LABEL[table.role] || table.role;

          return (
            <div key={table.name} className="px-4 py-2.5">
              <button
                type="button"
                onClick={() => toggleTable(table.name)}
                className="flex w-full items-center justify-between text-left focus:outline-none focus:ring-2 focus:ring-moss/40"
                aria-expanded={isOpen}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-ink/80">
                      {table.name}
                    </span>
                    {roleLabel && (
                      <span className="shrink-0 border border-ink/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-ink/45">
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
                <ChevronDown
                  className={`ml-2 h-4 w-4 shrink-0 text-ink/40 transition ${isOpen ? "rotate-180" : ""}`}
                  aria-hidden="true"
                />
              </button>

              {isOpen && (
                <div className="mt-2.5 space-y-1.5 border-t border-ink/5 pt-2.5">
                  {table.columns.length === 0 ? (
                    <p className="text-xs text-ink/40">暂无字段信息</p>
                  ) : (
                    table.columns.map((col) => (
                      <div
                        key={col.name}
                        className="flex items-start gap-3 rounded-sm bg-white/60 px-2.5 py-1.5"
                      >
                        <code className="shrink-0 text-xs font-mono font-semibold text-moss">
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
              )}
            </div>
          );
          })}
        </div>
      )}
    </div>
  );
}
