# 主题切换器 — datasprite ↔ wireframe code-review

**日期：** 2026-08-03
**范围：** 品牌羊皮纸主题 ↔ DaisyUI wireframe 线框主题切换

## 背景

宝想让 DaisyUI 内置 `wireframe` 线框主题可预览/切换。经过 AskUserQuestion 确认做成**主题切换器**：品牌羊皮纸保持默认，侧栏按钮随时切换。

## 改动文件

| 文件 | 改动内容 | 原因 |
|:---|:---|:---|
| `frontend/src/styles.css` | 品牌色从 unlayered `:root` 重构为 `@plugin "daisyui/theme"` 定义 `datasprite` 主题（default: true）；`themes: wireframe` 启用内置线框主题；body 背景改 `var(--color-base-100)` 随主题 | unlayered :root 优先级高于 `[data-theme="wireframe"]` 会盖掉线框色，改为 DaisyUI 主题才能用 `html[data-theme]` 平等切换（`:where(:root)` 特异性 0，wireframe 选择器特异性更高自然覆盖） |
| `frontend/src/styles.css` | 补 `--radius-*`/`--border`/`--depth`/`--noise` 变量 | `themes: wireframe` 移除了默认 light 主题，datasprite 若不定义半径变量会导致品牌主题圆角丢失（实测气泡变 0px） |
| `frontend/index.html` | `html` 加 `data-theme="datasprite"`；`<head>` 内联脚本按 localStorage 提前设主题 | 默认品牌主题 + 首屏防 FOUC 闪跳 |
| `frontend/src/App.tsx` | 新增 `AppTheme` 类型、`getInitialTheme`、主题 state + useEffect 写 `html[data-theme]` 与 localStorage、侧栏 `tooltip` + 切换按钮、根容器/header 背景 `bg-parchment` → `bg-base-100` | 切换器主体 + 背景随主题 |
| `Composer.tsx` / `MessageBubble.tsx` / `ConversationList.tsx` | `text-white` → `text-primary-content` / `text-error-content` | wireframe 下 primary 是浅灰 oklch(0.87)，白字看不清；语义色在品牌下仍是白字（值不变），wireframe 下自动深字修复对比度 |

## 审查发现与处理

1. **低危（已修复）**：持久化主题存在 localStorage，但首屏由 index.html 的 `data-theme="datasprite"` 渲染，wireframe 用户刷新会先闪品牌色（FOUC）。
   → `<head>` 加内联脚本，document 解析前按 localStorage 设置 `data-theme`，实测刷新后无闪跳。

2. **低危（已修复）**：切换 `themes` 从默认 `light --default` 改为 `wireframe` 后，datasprite 主题缺 `--radius-*` 变量，Playwright 实测气泡圆角从 `4px 4px 0px` 变 `0px`。
   → 按 DaisyUI 默认补齐 radius/border/depth/noise 变量，圆角恢复。

## 验证结果

- `pnpm test`：10 通过
- `pnpm lint`（tsc --noEmit）：0 错误
- `pnpm build`：成功
- Playwright 实测：
  - 默认加载 → `data-theme="datasprite"`，primary=#5e7855 moss、底=#faf8f4 羊皮纸、气泡 moss 绿+白字+圆角 4px
  - 侧栏按钮「羊皮纸主题/切换」→ 点击 → `data-theme="wireframe"`，primary=oklch(87%) 浅灰、底纯白、radius 0 方角、气泡浅灰底+深字（对比度修复生效）
  - localStorage `datasprite-theme=wireframe` 持久化，刷新后仍 wireframe（含防 FOUC 脚本）
  - 再点切回 datasprite 恢复品牌色
  - console 0 错误

## 提交

`151ebe0 feat: 主题切换器 — datasprite 品牌羊皮纸 ↔ wireframe 线框`
