/**
 * 智能图表视图组件
 *
 * 自动检测查询结果的数据形状 → 选择最佳图表类型 → 渲染图表 + 表格双视图切换。
 *
 * 支持的图表类型：
 * - area（面积图）：时间序列 + 单度量 — 量感趋势
 * - line（折线图）：时间序列 + 多度量 — 对比趋势
 * - bar（柱状图）：分类对比 — 单度量/多度量不同量级
 * - stackedBar（堆叠柱）：分类 + 多度量同量级 — 整体部分
 * - pie（饼图）：占比分布 — ≤6 段
 * - heatmap（热力图）：二维交叉 + 单度量 — 交叉分析
 * - table（表格）：不适合出图时回落
 *
 * 标记规范（dataviz marks & anatomy）：
 * - 柱 ≤24px、顶角 4px 圆角、底部直角靠基线
 * - 线 2px、圆角端点
 * - 面积填充 ~10% 透明度 wash
 * - 网格线实线 1px、下沉色
 * - 2px 表面间距分隔相邻标记
 * - Tooltip 增强不关守（值可 table view 获取）
 */

import { useMemo, useState, useCallback } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  LabelList,
} from "recharts";
import {
  BarChart3,
  LineChartIcon,
  PieChartIcon,
  Table2,
  AreaChartIcon,
  Layers,
  Grid3X3,
} from "lucide-react";

import { detectChartType, normalizeRows } from "../lib/chartDetector";
import { CHROME, categorical, EMPHASIS, SEQUENTIAL } from "../lib/chartColors";
import { ResultTable } from "./ResultTable";
import type { ChartHint } from "../types/agent";

// ── 视图模式 ──

type ViewMode = "chart" | "table";

// ═══════════════════════════════════════════════════════════════
// 工具
// ═══════════════════════════════════════════════════════════════

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "number") {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
    return v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }
  return String(v);
}

// ── 图标映射 ──

const CHART_ICON: Record<string, React.FC<{ className?: string }>> = {
  area: AreaChartIcon,
  line: LineChartIcon,
  bar: BarChart3,
  stackedBar: Layers,
  pie: PieChartIcon,
  heatmap: Grid3X3,
  table: Table2,
};

/** 度量值 → sequential 色阶（用于热力图） */
function heatmapColor(value: number, min: number, max: number): string {
  if (max === min) return SEQUENTIAL[3];
  const t = (value - min) / (max - min);
  const idx = Math.round(t * (SEQUENTIAL.length - 1));
  return SEQUENTIAL[Math.max(0, Math.min(idx, SEQUENTIAL.length - 1))];
}

// ═══════════════════════════════════════════════════════════════
// Tooltip（dataviz interaction spec）
// ═══════════════════════════════════════════════════════════════

function MarkTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-ink/10 bg-white/95 px-3 py-2 text-sm shadow-line backdrop-blur">
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2">
          <span
            className="inline-block h-[2px] w-3 shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-ink/55">{entry.name}</span>
          <span className="ml-auto pl-4 font-semibold tabular-nums text-ink">
            {formatValue(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function LineTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-ink/10 bg-white/95 px-3 py-2 text-sm shadow-line backdrop-blur">
      <p className="mb-1 text-xs font-semibold text-ink/55">{label}</p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2">
          <span
            className="inline-block h-[2px] w-3 shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-ink/55">{entry.name}</span>
          <span className="ml-auto pl-4 font-semibold tabular-nums text-ink">
            {formatValue(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// 通用外壳
// ═══════════════════════════════════════════════════════════════

function ChartShell({
  hint,
  children,
}: {
  hint: ChartHint;
  children: React.ReactNode;
}) {
  const title = hint.dimensionCol
    ? `${hint.measureCols.join(" / ")} 按 ${hint.dimensionCol}${hint.dimensionCol2 ? ` × ${hint.dimensionCol2}` : ""}`
    : hint.measureCols.join(" / ");
  return (
    <section className="overflow-hidden border border-ink/10 bg-white/70 shadow-line">
      <div className="flex items-center justify-between border-b border-ink/10 px-4 py-3">
        <span className="text-sm font-semibold text-ink">{title}</span>
      </div>
      <div className="px-2 pb-2 pt-3" style={{ height: 320 }}>
        {children}
      </div>
    </section>
  );
}

/** 图表通用数据：chartData（行）+ dataKeys（系列键） */
function useChartData(
  data: unknown,
  hint: ChartHint,
): {
  chartData: Array<Record<string, unknown>>;
  dataKeys: string[];
} {
  return useMemo(() => {
    const rows = normalizeRows(data);
    const { dimensionCol, measureCols, dimensionCol2 } = hint;

    if (!dimensionCol) {
      return { chartData: rows, dataKeys: measureCols };
    }

    if (!dimensionCol2) {
      // 单系列：一维 + 度量
      const chartData = rows.map((row) => ({
        name: String(row[dimensionCol] ?? ""),
        ...Object.fromEntries(
          measureCols.map((m) => [m, Number(row[m]) || 0]),
        ),
      }));
      return { chartData, dataKeys: measureCols };
    }

    // 多系列：按 dimensionCol2 透视，每组一个 series
    const xVals = [...new Set(rows.map((r) => String(r[dimensionCol] ?? "")))];
    const seriesNames = [...new Set(rows.map((r) => String(r[dimensionCol2] ?? "")))];

    // 查找表：{ xVal: { seriesName: { measure: value } } }
    const lookup: Record<string, Record<string, Record<string, number>>> = {};
    for (const row of rows) {
      const x = String(row[dimensionCol] ?? "");
      const s = String(row[dimensionCol2] ?? "");
      lookup[x] ??= {};
      lookup[x][s] ??= {};
      for (const m of measureCols) {
        lookup[x][s][m] = Number(row[m]) || 0;
      }
    }

    const chartData = xVals.map((x) => {
      const point: Record<string, unknown> = { name: x };
      for (const s of seriesNames) {
        for (const m of measureCols) {
          const key = measureCols.length === 1 ? s : `${s}·${m}`;
          point[key] = lookup[x]?.[s]?.[m] ?? 0;
        }
      }
      return point;
    });

    const dataKeys =
      measureCols.length === 1
        ? seriesNames
        : seriesNames.flatMap((s) => measureCols.map((m) => `${s}·${m}`));

    return { chartData, dataKeys };
  }, [data, hint]);
}

// ═══════════════════════════════════════════════════════════════
// 各图表组件
// ═══════════════════════════════════════════════════════════════

/** 柱状图 — 分类对比（支持多系列分组） */
function BarChartView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const { chartData, dataKeys } = useChartData(data, hint);
  const { dimensionCol } = hint;
  if (!dimensionCol) return null;

  const maxLabelLen = Math.max(
    ...chartData.map((r) => String(r.name ?? "").length),
  );
  const isHorizontal = maxLabelLen > 6 || chartData.length > 8;
  const showLegend = dataKeys.length > 1;
  const showLabels = chartData.length <= 6 && dataKeys.length <= 2;

  return (
    <ChartShell hint={hint}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout={isHorizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
          barCategoryGap="20%"
        >
          <CartesianGrid
            strokeDasharray="none"
            stroke={CHROME.gridline}
            strokeWidth={1}
            horizontal={!isHorizontal}
            vertical={isHorizontal}
          />
          <XAxis
            type={isHorizontal ? "number" : "category"}
            dataKey={isHorizontal ? undefined : "name"}
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
          />
          <YAxis
            type={isHorizontal ? "category" : "number"}
            dataKey={isHorizontal ? "name" : undefined}
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
            width={isHorizontal ? 100 : 56}
          />
          <Tooltip content={<MarkTooltip />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
          {showLegend && (
            <Legend wrapperStyle={{ fontSize: 12, color: CHROME.inkSecondary }} iconType="rect" />
          )}
          {dataKeys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              fill={dataKeys.length === 1 ? EMPHASIS.light : categorical(i)}
              radius={isHorizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
              maxBarSize={24}
              isAnimationActive={false}
            >
              {showLabels && (
                <LabelList
                  dataKey={key}
                  position={isHorizontal ? "right" : "top"}
                  style={{ fontSize: 12, fill: CHROME.inkSecondary, fontWeight: 500 }}
                  formatter={(v: number) => formatValue(v)}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

/** 堆叠柱状图 — 整体-部分 */
function StackedBarChartView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const { chartData, dataKeys } = useChartData(data, hint);
  const { dimensionCol } = hint;
  if (!dimensionCol) return null;

  const maxLabelLen = Math.max(
    ...chartData.map((r) => String(r.name ?? "").length),
  );
  const isHorizontal = maxLabelLen > 6 || chartData.length > 8;

  return (
    <ChartShell hint={hint}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout={isHorizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
          barCategoryGap="20%"
        >
          <CartesianGrid
            strokeDasharray="none"
            stroke={CHROME.gridline}
            strokeWidth={1}
            horizontal={!isHorizontal}
            vertical={isHorizontal}
          />
          <XAxis
            type={isHorizontal ? "number" : "category"}
            dataKey={isHorizontal ? undefined : "name"}
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
          />
          <YAxis
            type={isHorizontal ? "category" : "number"}
            dataKey={isHorizontal ? "name" : undefined}
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
            width={isHorizontal ? 100 : 56}
          />
          <Tooltip content={<MarkTooltip />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
          <Legend wrapperStyle={{ fontSize: 12, color: CHROME.inkSecondary }} iconType="rect" />
          {dataKeys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              stackId="stack"
              fill={categorical(i)}
              radius={
                // 只有最顶层有顶部圆角，其他层直角
                i === dataKeys.length - 1
                  ? isHorizontal
                    ? [0, 4, 4, 0]
                    : [4, 4, 0, 0]
                  : 0
              }
              maxBarSize={28}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

/** 折线图 — 时间趋势（多度量 / 多系列对比） */
function LineChartView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const { chartData, dataKeys } = useChartData(data, hint);
  const { dimensionCol } = hint;
  if (!dimensionCol) return null;

  const showLegend = dataKeys.length > 1;

  return (
    <ChartShell hint={hint}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid
            strokeDasharray="none"
            stroke={CHROME.gridline}
            strokeWidth={1}
          />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
            width={56}
          />
          <Tooltip content={<LineTooltip />} />
          {showLegend && (
            <Legend wrapperStyle={{ fontSize: 12, color: CHROME.inkSecondary }} iconType="line" />
          )}
          {dataKeys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              name={key}
              stroke={dataKeys.length === 1 ? EMPHASIS.light : categorical(i)}
              strokeWidth={2}
              dot={{
                r: 4,
                fill: dataKeys.length === 1 ? EMPHASIS.light : categorical(i),
                stroke: CHROME.surface,
                strokeWidth: 2,
              }}
              activeDot={{ r: 5, stroke: CHROME.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

/** 面积图 — 时间趋势（单度量，量感强） */
function AreaChartView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const { chartData, dataKeys } = useChartData(data, hint);
  const { dimensionCol } = hint;
  if (!dimensionCol) return null;

  return (
    <ChartShell hint={hint}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid
            strokeDasharray="none"
            stroke={CHROME.gridline}
            strokeWidth={1}
          />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: CHROME.inkMuted }}
            axisLine={{ stroke: CHROME.baseline, strokeWidth: 1 }}
            tickLine={false}
            width={56}
          />
          <Tooltip content={<LineTooltip />} />
          {dataKeys.map((key, i) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              name={key}
              stroke={dataKeys.length === 1 ? EMPHASIS.light : categorical(i)}
              fill={dataKeys.length === 1 ? EMPHASIS.area : categorical(i) + "18"}
              strokeWidth={2}
              dot={{
                r: 4,
                fill: dataKeys.length === 1 ? EMPHASIS.light : categorical(i),
                stroke: CHROME.surface,
                strokeWidth: 2,
              }}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

/** 饼图 — 占比分布 */
function PieChartView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const rows = useMemo(() => normalizeRows(data), [data]);
  const { dimensionCol, measureCols } = hint;
  if (!dimensionCol || !measureCols[0]) return null;

  const chartData = rows.map((row) => ({
    name: String(row[dimensionCol] ?? ""),
    value: Number(row[measureCols[0]]) || 0,
  }));

  const total = chartData.reduce((s, d) => s + d.value, 0);

  const renderLabel = useCallback(
    ({ cx, cy, midAngle, outerRadius, name, percent }: {
      cx: number; cy: number; midAngle: number; outerRadius: number; name: string; percent: number;
    }) => {
      const RADIAN = Math.PI / 180;
      const radius = outerRadius * 1.28;
      const x = cx + radius * Math.cos(-midAngle * RADIAN);
      const y = cy + radius * Math.sin(-midAngle * RADIAN);
      return (
        <text
          x={x}
          y={y}
          fill={CHROME.inkSecondary}
          textAnchor={x > cx ? "start" : "end"}
          dominantBaseline="central"
          style={{ fontSize: 12 }}
        >
          <tspan x={x} dy="-0.4em" fill={CHROME.ink}>{name}</tspan>
          <tspan x={x} dy="1.2em">{`${((percent ?? 0) * 100).toFixed(1)}%`}</tspan>
        </text>
      );
    },
    [],
  );

  return (
    <ChartShell hint={hint}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={90}
            innerRadius={0}
            isAnimationActive={false}
            paddingAngle={2}
            label={renderLabel}
          >
            {chartData.map((_, i) => (
              <Cell
                key={i}
                fill={categorical(i)}
                stroke={CHROME.surface}
                strokeWidth={2}
              />
            ))}
          </Pie>
          <Tooltip content={<MarkTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12, color: CHROME.inkSecondary }} iconType="line" />
        </PieChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

/** 热力图 — 二维交叉分析 */
function HeatmapView({ data, hint }: { data: unknown; hint: ChartHint }) {
  const rows = useMemo(() => normalizeRows(data), [data]);
  const dim1 = hint.dimensionCol;
  const dim2 = hint.dimensionCol2;
  const measureColName = hint.measureCols[0];

  if (!dim1 || !dim2 || !measureColName) return null;

  // 构建矩阵
  const rowKeys = [...new Set(rows.map((r) => String(r[dim1] ?? "")))];
  const colKeys = [...new Set(rows.map((r) => String(r[dim2] ?? "")))];

  const matrix: Record<string, Record<string, number>> = {};
  for (const r of rows) {
    const rk = String(r[dim1] ?? "");
    const ck = String(r[dim2] ?? "");
    if (!matrix[rk]) matrix[rk] = {};
    matrix[rk][ck] = Number(r[measureColName]) || 0;
  }

  // 找 min/max 用于色阶
  const allValues = rows.map((r) => Number(r[measureColName]) || 0);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);

  return (
    <ChartShell hint={hint}>
      <div className="overflow-auto" style={{ maxHeight: 280 }}>
        <table className="border-separate border-spacing-[2px] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white/70 px-2 py-1 text-ink/55 font-medium">
                {dim1} \ {dim2}
              </th>
              {colKeys.map((ck) => (
                <th key={ck} className="px-3 py-1 font-medium text-ink/55">
                  {ck}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowKeys.map((rk) => (
              <tr key={rk}>
                <td className="sticky left-0 bg-white/70 px-2 py-1 font-medium text-ink/70">
                  {rk}
                </td>
                {colKeys.map((ck) => {
                  const val = matrix[rk]?.[ck];
                  return (
                    <td
                      key={ck}
                      className="px-3 py-1 text-center tabular-nums font-medium"
                      style={{
                        backgroundColor: val !== undefined ? heatmapColor(val, min, max) : "transparent",
                        color: val !== undefined && (val - min) / (max - min || 1) > 0.5 ? "#fff" : CHROME.ink,
                      }}
                      title={val !== undefined ? `${rk} × ${ck}: ${formatValue(val)}` : "-"}
                    >
                      {val !== undefined ? formatValue(val) : "-"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartShell>
  );
}

// ═══════════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════════

export function ChartView({ data, query }: { data: unknown; query?: string }) {
  const hint = useMemo(() => detectChartType(data, query), [data, query]);
  const [view, setView] = useState<ViewMode>(
    hint.chartType && hint.chartType !== "table" ? "chart" : "table",
  );

  const switchView = useCallback((v: ViewMode) => setView(v), []);

  const canChart = hint.chartType && hint.chartType !== "table";
  const Icon = canChart ? CHART_ICON[hint.chartType!] : Table2;

  return (
    <section className="mt-4">
      {/* 视图切换 tabs */}
      <div className="mb-2 flex items-center gap-1">
        {canChart && (
          <button
            type="button"
            onClick={() => switchView("chart")}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-moss/40 ${
              view === "chart"
                ? "bg-moss/12 text-moss"
                : "text-ink/45 hover:text-ink/70"
            }`}
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            图表
          </button>
        )}
        <button
          type="button"
          onClick={() => switchView("table")}
          className={`inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-moss/40 ${
            view === "table" || !canChart
              ? canChart
                ? "bg-moss/12 text-moss"
                : "text-ink/45"
              : "text-ink/45 hover:text-ink/70"
          }`}
        >
          <Table2 className="h-3.5 w-3.5" />
          表格
        </button>
        {hint.reason && (
          <span className="ml-2 text-xs text-ink/35">{hint.reason}</span>
        )}
      </div>

      {/* 内容 */}
      {view === "chart" && canChart ? (
        hint.chartType === "bar" ? (
          <BarChartView data={data} hint={hint} />
        ) : hint.chartType === "stackedBar" ? (
          <StackedBarChartView data={data} hint={hint} />
        ) : hint.chartType === "line" ? (
          <LineChartView data={data} hint={hint} />
        ) : hint.chartType === "area" ? (
          <AreaChartView data={data} hint={hint} />
        ) : hint.chartType === "pie" ? (
          <PieChartView data={data} hint={hint} />
        ) : hint.chartType === "heatmap" ? (
          <HeatmapView data={data} hint={hint} />
        ) : (
          <ResultTable data={data} />
        )
      ) : (
        <ResultTable data={data} />
      )}
    </section>
  );
}
