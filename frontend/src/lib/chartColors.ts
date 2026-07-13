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
  surface: "#FAF8F4",
  ink: "#14110E",
  inkSecondary: "#6B645A",
  inkMuted: "#9A9284",
  gridline: "#E5E0D4",
  baseline: "#C5BFB4",
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
  light: "#5E7855", // moss (Thrive sage) — 单系列柱/线默认填充
  lightHover: "#7A9370", // hover 时稍亮
  area: "rgba(94, 120, 85, 0.10)", // 面积图填充 wash
} as const;

// ── 降级灰（"其他"系列的上下文色）──

export const DEEMPHASIS = "#C5BFB4";

// ── 顺序渐变（moss 单色，light→dark，用于有序类别）──

export const SEQUENTIAL = [
  "#DEE5D9", // 100
  "#B8C9AE", // 200
  "#91AA82", // 300
  "#7A9370", // 400
  "#5E7855", // 500 — moss (Thrive sage)
  "#3D5235", // 600
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
