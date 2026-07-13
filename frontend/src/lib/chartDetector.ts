/**
 * 图表类型自动检测
 *
 * 从查询结果的列名和数值形状中推断最佳图表类型：
 * - 时间 + 分类维度 + 单度量 → line（多系列折线图）
 * - 时间维度 + 单度量 → area（面积图）
 * - 时间维度 + 多度量 → line（折线图）
 * - 分类维度 + 单度量、≤8 类 → bar（柱状图）
 * - 分类维度 + 多度量、≤10 行 → stackedBar（堆叠柱状图）
 * - 双维度交叉 + 单度量 → heatmap / 分组 bar（热力图/分组柱状图）
 * - 占比数据 → pie（饼图，≤6 段）
 * - 其他 → table（纯表格）
 */

import type { ChartHint, ChartType } from "../types/agent";

// ── 时间列名关键词 ──

const TIME_KEYWORDS = [
  "日期", "时间", "月份", "季度", "年份", "年", "月", "日", "季",
  "date", "time", "month", "quarter", "year", "day",
  "week", "周",
];

// ── 时间值模式 ──

const TIME_VALUE_RE = /^\d{4}[年/-]\d{1,2}|^\d{4}Q[1-4]|^Q[1-4]\s?\d{4}|^\d{4}$/;

// ── 占比检测阈值 ──

const PIE_MAX_SEGMENTS = 6;
const PIE_MAX_ROWS = 12;
/** 列名含这些关键词时视为占比数据 */
const PART_WHOLE_COL_KEYWORDS = ["占比", "比例", "份额", "%", "percent", "share", "ratio"];
/** query 文本含这些关键词时也触发占比检测 */
const PART_WHOLE_QUERY_KEYWORDS = ["占比", "比例", "份额", "百分比", "占多少"];

// ── 其他图表阈值 ──

const STACKED_MAX_ROWS = 10;
const STACKED_MAX_MEASURES = 5;
const HEATMAP_MIN_CELLS = 4;

/** 判断列是否为时间类型 */
function isTimeColumn(name: string, sampleValues: unknown[]): boolean {
  const lower = name.toLowerCase();
  if (TIME_KEYWORDS.some((kw) => lower.includes(kw))) return true;
  const hits = sampleValues.filter(
    (v) => typeof v === "string" && TIME_VALUE_RE.test(v.trim()),
  );
  return hits.length >= Math.min(3, sampleValues.length);
}

/** 判断列是否为数值 */
function isNumericColumn(values: unknown[]): boolean {
  const hits = values.filter(
    (v) => v !== null && v !== undefined && v !== "" && !isNaN(Number(v)),
  );
  return hits.length >= values.length * 0.8;
}

/** 判断列名是否暗示占比数据 */
function isPartToWholeCol(colName: string): boolean {
  const lower = colName.toLowerCase();
  return PART_WHOLE_COL_KEYWORDS.some((kw) => lower.includes(kw));
}

/** 判断用户原始 query 是否问占比 */
function queryAsksPartToWhole(query?: string): boolean {
  if (!query) return false;
  return PART_WHOLE_QUERY_KEYWORDS.some((kw) => query.includes(kw));
}

/** 判断数值是否像占比（所有值在 0~1 或 0~100 区间，且至少有一个非零值） */
function valuesLookLikeRatio(values: number[]): boolean {
  if (values.length === 0) return false;
  const hasNonZero = values.some((v) => v > 0);
  if (!hasNonZero) return false;
  const allIn01 = values.every((v) => v >= 0 && v <= 1);
  const allIn0100 = values.every((v) => v >= 0 && v <= 100);
  return allIn01 || allIn0100;
}

/** 判断多个度量是否大致同量级（不是相差 100 倍以上），用于堆叠柱 */
function measuresSameScale(values: Record<string, number[]>): boolean {
  const avgs = Object.entries(values).map(([, vals]) => {
    if (vals.length === 0) return 0;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  });
  if (avgs.length < 2) return true;
  const maxAvg = Math.max(...avgs);
  const minAvg = Math.min(...avgs);
  if (minAvg === 0) return false;
  return maxAvg / minAvg <= 50; // 两个度量平均相差不超过 50 倍
}

// ── 归一化 ──

type Row = Record<string, unknown>;

function normalizeRows(data: unknown): Row[] {
  if (Array.isArray(data)) {
    return data.map((item, i) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? (item as Row)
        : { 序号: i + 1, 值: item },
    );
  }
  if (data && typeof data === "object") return [data as Row];
  return [{ 值: data ?? "" }];
}

// ── 主入口 ──

/**
 * 分析查询结果，返回图表类型建议。
 *
 * 判断优先级（由具体到通用）：
 * 1. 异常/边界 → table
 * 2. 时间 + 其他维度 + 单度量 → line（多系列折线）
 * 3. 时间维度 + 单度量 → area（面积图）
 * 4. 时间维度 + 多度量 → line（折线图）
 * 5. 占比（列名/query + 值区间）→ pie
 * 6. 双维度交叉 + 单度量 → heatmap / 分组 bar
 * 7. 单维度 + 多度量同量级 → stackedBar
 * 8. 单纬度 + 单度量 → bar
 * 9. 其他 → table
 */
export function detectChartType(data: unknown, query?: string): ChartHint {
  const rows = normalizeRows(data);
  if (rows.length === 0) {
    return { chartType: null, dimensionCol: null, measureCols: [], reason: "无数据" };
  }

  const columns = Object.keys(rows[0]);
  if (columns.length < 2) {
    return { chartType: "table", dimensionCol: null, measureCols: [], reason: "仅单列，不适合出图" };
  }

  // 采样每列的值
  const sampleSize = Math.min(rows.length, 10);
  const sampleRows = rows.slice(0, sampleSize);
  const colValues = (col: string) => sampleRows.map((r) => r[col]);

  // 分类：维度 vs 度量
  const dimCols: string[] = [];
  const measureCols: string[] = [];

  for (const col of columns) {
    if (isNumericColumn(colValues(col))) {
      measureCols.push(col);
    } else {
      dimCols.push(col);
    }
  }

  // 没有度量列 → 纯表格
  if (measureCols.length === 0) {
    return { chartType: "table", dimensionCol: null, measureCols: [], reason: "无度量值列" };
  }

  const primaryDim = dimCols.length > 0 ? dimCols[0] : columns[0];
  const primaryMeasure = measureCols[0];

  // ── 行数过多 → 表格 ──
  if (rows.length > 30) {
    return {
      chartType: "table",
      dimensionCol: primaryDim,
      measureCols,
      reason: `行数过多（${rows.length} 行），表格更清晰`,
    };
  }

  // ── 时间维度 ──
  const timeCol = dimCols.find((c) => isTimeColumn(c, colValues(c)));
  if (timeCol) {
    const otherDims = dimCols.filter((c) => c !== timeCol);
    // 时间 + 其他维度 + 单度量 → 多系列折线图（每条线 = 一个分类）
    if (otherDims.length >= 1 && measureCols.length === 1 && rows.length >= 4) {
      return {
        chartType: "line",
        dimensionCol: timeCol,
        dimensionCol2: otherDims[0],
        measureCols,
      };
    }
    if (measureCols.length === 1) {
      // 单度量 → 面积图（量感更明显）
      return { chartType: "area", dimensionCol: timeCol, measureCols };
    }
    // 多度量 → 折线图（对比清晰）
    return { chartType: "line", dimensionCol: timeCol, measureCols };
  }

  // ── 单度量 ──
  if (measureCols.length === 1 && dimCols.length >= 1) {
    const values = rows.map((r) => Number(r[primaryMeasure])).filter((v) => !isNaN(v));

    // 占比 → 饼图（列名 或 query 含占比关键词 + 值在比例区间）
    const partWhole =
      (isPartToWholeCol(primaryMeasure) || queryAsksPartToWhole(query)) &&
      valuesLookLikeRatio(values);
    if (
      partWhole &&
      rows.length <= PIE_MAX_ROWS &&
      rows.length >= 2 &&
      rows.length <= PIE_MAX_SEGMENTS
    ) {
      return { chartType: "pie", dimensionCol: primaryDim, measureCols };
    }

    // 双维度交叉（2个非时间维度）→ 热力图 / 分组柱状图
    const nonTimeDims = dimCols.filter((c) => !isTimeColumn(c, colValues(c)));
    if (
      nonTimeDims.length >= 2 &&
      rows.length >= HEATMAP_MIN_CELLS &&
      rows.length <= 30
    ) {
      return {
        chartType: "heatmap",
        dimensionCol: nonTimeDims[0],
        dimensionCol2: nonTimeDims[1],
        measureCols: [primaryMeasure],
      };
    }
    // 热力图不满足条件（2~3 行）→ 分组柱状图也能用 dimensionCol2
    if (nonTimeDims.length >= 2 && rows.length >= 2) {
      return {
        chartType: "bar",
        dimensionCol: nonTimeDims[0],
        dimensionCol2: nonTimeDims[1],
        measureCols,
      };
    }
    // 默认 → 柱状图
    return { chartType: "bar", dimensionCol: primaryDim, measureCols };
  }

  // ── 多度量 + 单维度 → 堆叠柱（而非分组柱）──
  if (
    measureCols.length >= 2 &&
    measureCols.length <= STACKED_MAX_MEASURES &&
    dimCols.length >= 1 &&
    rows.length <= STACKED_MAX_ROWS
  ) {
    // 检查度量是否同量级
    const measureValues: Record<string, number[]> = {};
    for (const m of measureCols) {
      measureValues[m] = rows.map((r) => Number(r[m]) || 0);
    }
    if (measuresSameScale(measureValues)) {
      return { chartType: "stackedBar", dimensionCol: primaryDim, measureCols };
    }
    // 不同量级 → 分组柱状图更合适
    return { chartType: "bar", dimensionCol: primaryDim, measureCols };
  }

  // ── 兜底：表格 ──
  return {
    chartType: "table",
    dimensionCol: primaryDim,
    measureCols,
    reason: `列数较多（${columns.length}），纯表格更清晰`,
  };
}

export { normalizeRows, isTimeColumn, isNumericColumn, TIME_KEYWORDS };
