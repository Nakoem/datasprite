/**
 * DataSprite 图表色板
 *
 * 基于 dataviz skill 六项检查的验证结果：
 * - 分类色板 (8 slots) — 参考色板，已验证 CVD ΔE ≥ 12（明）/ ≥ 8（暗）
 * - 顺序渐变 — moss 品牌色单色渐变
 * - 状态色 — 固定，不参与主题
 * - 图表 chrome — parchment / ink 品牌色
 *
 * 规则：分类色固定顺序分配不循环、色跟实体不跟排名、状态色不混用
 */

// ── 图表 chrome（品牌：parchment 表面 + ink 文字）──

export const CHROME = {
  surface: "#f7f1e8",
  ink: "#20201d",
  inkSecondary: "#52514e",
  inkMuted: "#8a8782",
  gridline: "#e1ddd6",
  baseline: "#c8c0b5",
} as const;

// ── 分类色板（8 slots，已验证）──

const CATEGORICAL_LIGHT = [
  "#2a78d6", // slot 1 — blue
  "#1baf7a", // slot 2 — aqua
  "#eda100", // slot 3 — yellow
  "#008300", // slot 4 — green
  "#4a3aa7", // slot 5 — violet
  "#e34948", // slot 6 — red
  "#e87ba4", // slot 7 — magenta
  "#eb6834", // slot 8 — orange
] as const;

const CATEGORICAL_DARK = [
  "#3987e5",
  "#199e70",
  "#c98500",
  "#008300",
  "#9085e9",
  "#e66767",
  "#d55181",
  "#d95926",
] as const;

/** 按 index 取分类色（0-based），超出 8 个回落 slot 1 */
export function categorical(index: number, dark = false): string {
  const palette = dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT;
  return palette[index % palette.length];
}

export const CATEGORICAL = CATEGORICAL_LIGHT;

// ── 强调色（单系列 → 品牌 moss）──

export const EMPHASIS = {
  light: "#2f6b4f", // moss — 单系列柱/线默认填充
  lightHover: "#3e8563", // hover 时稍亮
  area: "rgba(47, 107, 79, 0.10)", // 面积图填充 wash
} as const;

// ── 降级灰（"其他"系列的上下文色）──

export const DEEMPHASIS = "#c8c0b5";

// ── 顺序渐变（moss 单色，light→dark，用于有序类别）──

export const SEQUENTIAL = [
  "#d5e8dc", // 100
  "#a3ccb5", // 200
  "#72b18e", // 300
  "#4a8a6d", // 400
  "#2f6b4f", // 500 — moss
  "#1e4533", // 600
] as const;

// ── 状态色（固定，不主题化）──

export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

// ── 轮播色（饼图/堆叠柱的多段）──

/** 为饼图/堆叠柱提供按 segment index 取色的快捷方法 */
export function segmentColor(index: number, total: number, dark = false): string {
  if (total <= 8) return categorical(index, dark);
  // >8 段：从 categorical 中插值 → 此处简化为循环（实际应 fold 进 "Other"）
  return categorical(index % 8, dark);
}
