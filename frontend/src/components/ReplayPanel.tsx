/**
 * Checkpoint 回放面板
 *
 * 时间线滑块 + State 快照查看 + 字段级 Diff 对比，
 * 用于调试 LangGraph 工作流执行过程。
 * 多条查询时按 query 分组展示，避免时间线重叠。
 */
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Layers,
  Play,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchCheckpointDetail,
  fetchCheckpointDiff,
  fetchCheckpoints,
} from "../lib/agentApi";
import { formatTime } from "../lib/format";
import type {
  CheckpointDetail,
  CheckpointDiffResponse,
  CheckpointSummary,
} from "../types/agent";
import { StateJsonTree } from "./StateJsonTree";

type ReplayPanelProps = {
  conversationId: string;
};

type LoadState = "loading" | "loaded" | "error" | "empty";
type PanelTab = "state" | "diff";

type QueryGroup = {
  query: string;
  startIndex: number;
  checkpoints: CheckpointSummary[];
};

export function ReplayPanel({ conversationId }: ReplayPanelProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [checkpoints, setCheckpoints] = useState<CheckpointSummary[]>([]);
  const [error, setError] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [detail, setDetail] = useState<CheckpointDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Diff 相关状态
  const [tab, setTab] = useState<PanelTab>("state");
  const [baseIndex, setBaseIndex] = useState(0);
  const [diff, setDiff] = useState<CheckpointDiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  // 分组折叠：undefined = 按默认折叠（多查询默认全折叠）
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const isGroupOpen = (gi: number) =>
    isMultiQuery ? (collapsed[gi] ?? false) : true;

  const loadList = useCallback(async () => {
    setLoadState("loading");
    try {
      const result = await fetchCheckpoints(conversationId);
      if (result.checkpoints.length === 0) {
        setLoadState("empty");
      } else {
        setCheckpoints(result.checkpoints);
        setSelectedIndex(result.checkpoints.length - 1);
        setBaseIndex(0);
        setLoadState("loaded");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
      setLoadState("error");
    }
  }, [conversationId]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // 按 query 字段分组（query=null 的初始步骤归入第一条查询）
  const queryGroups = useMemo<QueryGroup[]>(() => {
    const groups: QueryGroup[] = [];
    let current: CheckpointSummary[] = [];
    let lastQuery: string | null = null;

    for (let i = 0; i < checkpoints.length; i++) {
      const cp = checkpoints[i];
      const q = cp.query || null;
      // query 从 null→有值 或 有值→不同值 时切新组
      if (q && q !== lastQuery) {
        if (current.length > 0) {
          groups.push({
            query: lastQuery ?? "",
            startIndex: i - current.length,
            checkpoints: current,
          });
        }
        current = [cp];
        lastQuery = q;
      } else {
        current.push(cp);
      }
    }
    if (current.length > 0) {
      groups.push({
        query: lastQuery ?? "",
        startIndex: checkpoints.length - current.length,
        checkpoints: current,
      });
    }

    // 合并 query 为空的第一组到下一组（__start__ 归入第一条查询）
    if (groups.length > 1 && !groups[0].query) {
      const emptyGroup = groups.shift()!;
      groups[0].checkpoints = [...emptyGroup.checkpoints, ...groups[0].checkpoints];
      groups[0].startIndex = emptyGroup.startIndex;
    }

    return groups;
  }, [checkpoints]);

  // 滑块变化 → 加载详情
  useEffect(() => {
    if (checkpoints.length === 0) return;
    const cp = checkpoints[selectedIndex];
    if (!cp) return;

    setDetailLoading(true);
    setDetail(null);
    fetchCheckpointDetail(conversationId, cp.checkpoint_id)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, [conversationId, checkpoints, selectedIndex]);

  // Diff tab 激活时加载 diff
  useEffect(() => {
    if (tab !== "diff") return;
    if (checkpoints.length === 0) return;

    const baseCp = checkpoints[baseIndex];
    const targetCp = checkpoints[selectedIndex];
    if (!baseCp || !targetCp) return;

    setDiffLoading(true);
    setDiff(null);
    fetchCheckpointDiff(
      conversationId,
      targetCp.checkpoint_id,
      baseCp.checkpoint_id,
    )
      .then(setDiff)
      .catch((err) => {
        console.error("Diff 请求失败", err);
        setDiff(null);
      })
      .finally(() => setDiffLoading(false));
  }, [conversationId, checkpoints, selectedIndex, baseIndex, tab]);

  const shortLabel = (label: string) => label.split(" | ")[0];

  const selected = useMemo(
    () => checkpoints[selectedIndex] ?? null,
    [checkpoints, selectedIndex],
  );

  const toggleGroup = (gi: number) =>
    setCollapsed((prev) => ({ ...prev, [gi]: !prev[gi] }));

  // ── 加载 / 错误 / 空状态 ──

  if (loadState === "loading") {
    return (
      <div className="flex items-center justify-center py-24">
        <RefreshCw className="h-6 w-6 animate-spin text-ink/30" />
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16">
        <AlertTriangle className="h-10 w-10 text-tomato/60" />
        <p className="text-sm text-ink/60">{error}</p>
        <button
          type="button"
          onClick={loadList}
          className="inline-flex items-center gap-2 text-sm text-moss hover:underline"
        >
          <RefreshCw className="h-4 w-4" />
          重试
        </button>
      </div>
    );
  }

  if (loadState === "empty") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <GitBranch className="h-10 w-10 text-ink/25" />
        <p className="text-sm text-ink/50">暂无 checkpoint 数据</p>
        <p className="text-xs text-ink/35">
          请先执行一次查询后再来回放
        </p>
      </div>
    );
  }

  const isMultiQuery = queryGroups.length > 1;

  // ── 正常渲染 ──

  return (
    <div className="flex flex-col h-full">
      {/* 顶部：全局滑块 + 当前选中摘要 */}
      <div className="border-b border-ink/10 bg-white/80 px-6 py-4">
        <div className="flex items-center gap-3 mb-2">
          <Play className="h-4 w-4 text-moss" />
          <span className="text-sm font-semibold text-ink/70">
            Checkpoint 时间线
          </span>
          <span className="text-xs text-ink/40">
            {checkpoints.length} 步 · {queryGroups.length} 次查询
          </span>
        </div>

        {/* 全局滑块（多查询时用） */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={selectedIndex <= 0}
            onClick={() => setSelectedIndex((v) => Math.max(0, v - 1))}
            className="p-1 text-ink/40 hover:text-ink/70 disabled:opacity-25"
            aria-label="上一个 checkpoint"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <input
            type="range"
            min={0}
            max={checkpoints.length - 1}
            value={selectedIndex}
            onChange={(e) => setSelectedIndex(Number(e.target.value))}
            className="flex-1 accent-moss"
            aria-label="选择 checkpoint 位置"
          />
          <button
            type="button"
            disabled={selectedIndex >= checkpoints.length - 1}
            onClick={() =>
              setSelectedIndex((v) =>
                Math.min(checkpoints.length - 1, v + 1),
              )
            }
            className="p-1 text-ink/40 hover:text-ink/70 disabled:opacity-25"
            aria-label="下一个 checkpoint"
          >
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>

        {/* 当前选中摘要 */}
        {selected && (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink/45">
            <span className="font-medium text-ink/60">
              #{selected.step_number}
            </span>
            <span>{shortLabel(selected.step_label)}</span>
            {selected.timestamp && (
              <span>
                {formatTime(new Date(selected.timestamp).getTime())}
              </span>
            )}
            {selected.has_sql && (
              <span className="text-moss font-medium">含 SQL</span>
            )}
            {selected.has_result && (
              <span className="text-moss font-medium">含结果</span>
            )}
          </div>
        )}
      </div>

      {/* 按查询分组的时间线 */}
      <div className="border-b border-ink/10 bg-white/60 px-6 py-3 space-y-1 max-h-64 overflow-auto">
        {queryGroups.map((group, gi) => {
          const cps = group.checkpoints;
          const isOpen = isGroupOpen(gi);

          return (
            <div key={gi} className={isMultiQuery ? "border border-ink/8 bg-white/70" : ""}>
              {/* 分组标题 — 单查询时省略 */}
              {isMultiQuery && (
                <button
                  type="button"
                  onClick={() => toggleGroup(gi)}
                  className="w-full flex items-center gap-2 px-3 py-2 hover:bg-ink/[0.03] transition text-left"
                >
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5 text-ink/35 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-ink/35 shrink-0" />
                  )}
                  <span className="text-xs font-semibold text-ink/60">
                    查询 #{gi + 1}
                  </span>
                  <span className="text-xs text-ink/50 truncate max-w-[320px]">
                    {group.query}
                  </span>
                  <span className="text-[10px] text-ink/35 ml-auto shrink-0">
                    {cps.length} 步
                  </span>
                </button>
              )}

              {/* 步骤标签行 */}
              {isOpen && (
                <div className={isMultiQuery ? "px-3 pb-2.5" : ""}>
                  <div className="flex flex-wrap gap-x-1 gap-y-0.5">
                    {cps.map((cp, ci) => {
                      const actualIdx = group.startIndex + ci;
                      const isActive = actualIdx === selectedIndex;
                      return (
                        <button
                          key={cp.checkpoint_id}
                          type="button"
                          onClick={() =>
                            setSelectedIndex(actualIdx)
                          }
                          className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded transition ${
                            isActive
                              ? "bg-moss/15 text-moss font-semibold"
                              : "text-ink/40 hover:bg-ink/5 hover:text-ink/60"
                          }`}
                        >
                          {shortLabel(cp.step_label)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 内容区：State / Diff */}
      <div className="flex-1 overflow-auto">
        <div className="flex items-center border-b border-ink/10 bg-white/60 px-6">
          <button
            type="button"
            onClick={() => setTab("state")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 transition ${
              tab === "state"
                ? "border-moss text-moss"
                : "border-transparent text-ink/45 hover:text-ink/65"
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            State
          </button>
          <button
            type="button"
            onClick={() => setTab("diff")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 transition ${
              tab === "diff"
                ? "border-moss text-moss"
                : "border-transparent text-ink/45 hover:text-ink/65"
            }`}
          >
            <GitBranch className="h-3.5 w-3.5" />
            Diff
          </button>
        </div>

        {/* State */}
        {tab === "state" && (
          <div className="p-6">
            {detailLoading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="h-5 w-5 animate-spin text-ink/25" />
              </div>
            ) : detail ? (
              <div className="space-y-3">
                <StateJsonTree data={detail.state} maxDepth={2} />
              </div>
            ) : (
              <p className="text-sm text-ink/40 text-center py-12">
                无法加载 checkpoint state
              </p>
            )}
          </div>
        )}

        {/* Diff */}
        {tab === "diff" && (
          <div className="p-6">
            <div className="flex items-center gap-4 mb-4 text-xs">
              <label className="flex items-center gap-1.5 text-ink/55">
                Base:
                <select
                  value={baseIndex}
                  onChange={(e) => setBaseIndex(Number(e.target.value))}
                  className="border border-ink/15 bg-white px-2 py-1 text-xs focus:outline-none focus:border-moss"
                >
                  {checkpoints.map((cp, i) => (
                    <option key={cp.checkpoint_id} value={i}>
                      #{cp.step_number} {shortLabel(cp.step_label)}
                    </option>
                  ))}
                </select>
              </label>
              <span className="text-ink/30">→</span>
              <label className="flex items-center gap-1.5 text-ink/55">
                Target:
                <select
                  value={selectedIndex}
                  onChange={(e) => setSelectedIndex(Number(e.target.value))}
                  className="border border-ink/15 bg-white px-2 py-1 text-xs focus:outline-none focus:border-moss"
                >
                  {checkpoints.map((cp, i) => (
                    <option key={cp.checkpoint_id} value={i}>
                      #{cp.step_number} {shortLabel(cp.step_label)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {diffLoading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="h-5 w-5 animate-spin text-ink/25" />
              </div>
            ) : diff ? (
              <div className="space-y-2">
                {diff.diffs.map((d) => (
                  <div
                    key={d.field}
                    className={`border px-4 py-2.5 ${
                      d.changed
                        ? "border-moss/30 bg-moss/[0.04]"
                        : "border-ink/10 bg-white/60"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-ink/70">
                        {d.field}
                      </span>
                      {d.changed ? (
                        <span className="text-[10px] text-moss font-medium">
                          已变更
                        </span>
                      ) : (
                        <span className="text-[10px] text-ink/35">
                          未变更
                        </span>
                      )}
                    </div>
                    {d.changed && (
                      <div className="grid grid-cols-2 gap-3 text-[11px] font-mono">
                        <div>
                          <span className="text-tomato/70">- Before:</span>
                          <pre className="mt-0.5 text-ink/50 line-clamp-3">
                            {JSON.stringify(d.before, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <span className="text-moss">+ After:</span>
                          <pre className="mt-0.5 text-ink/70 line-clamp-3">
                            {JSON.stringify(d.after, null, 2)}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink/40 text-center py-12">
                无法加载 diff 数据
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
