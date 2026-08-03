# 消息气泡头像最终版 code-review — 用户去头像 + 机器人问数精灵🧚

**日期：** 2026-08-03
**范围：** 消息气泡头像方向定稿：用户无头像，助手用问数精灵 🧚（moss 渐变，与 favicon 同款）放消息卡片左上方
**前置迭代：** lucide 线条图标（被否）→ DiceBear 在线头像（commit 4102e90，被否）→ 本版

## 背景

宝最终定稿：「用户不要头像吧，机器人可以用问数精灵那个图标做头像，然后历史对话里机器人头像放在查询完成卡片的左上方去」。

## 改动文件

| 文件 | 改动内容 | 原因 |
|:---|:---|:---|
| `frontend/src/components/MessageBubble.tsx` | ① 删除 DiceBear 在线方案：`ChatAvatar` 组件、DiceBear URL、onError 兜底逻辑、`useState`/`ReactNode` import ② 用户头像整块移除 ③ 助手头像改 moss 渐变圆底 🧚 emoji，外层加 `self-start` 实现顶部对齐 | ① 去掉第三方在线头像依赖（离线裂图、风格难统一）② 宝不要用户头像 ③ 精灵 emoji 与 favicon / 登录页 logo 视觉统一；`self-start` 让头像贴气泡左上，贴合「查询完成卡片左上方」 |

## 审查发现与处理

1. **中危（已处理）**：DiceBear 在线头像依赖第三方服务，离线时 img 裂图，且风格与品牌（moss 羊皮纸）不统一。
   → 换静态 moss 渐变 + 🧚 emoji，零外部依赖，与 favicon 同款配色。原 ChatAvatar 私有组件无任何残留引用（grep 确认）。

2. **低危（不处理）**：🧚 emoji 在不同平台字体下渲染细节略有差异。通用做法，可接受。

## 验证结果

- `pnpm test`：10 通过
- `pnpm lint`（tsc --noEmit）：0 错误
- `pnpm build`：成功
- Playwright 实测（历史会话「统计 2025 年第一季度各大区的 GMV」）：
  - 用户消息：`hasAvatar: false`（无头像）
  - 助手消息：`hasAvatar: true`，`alignSelf: flex-start`（顶部对齐 = 卡片左上方），moss 渐变 `rgb(94,120,85)`，emoji 🧚，气泡以「查询完成 分析摘要 2025年Q1…」开头
  - 刷新页面后 console：0 errors / 0 warnings（此前 `CircleUserRound is not defined` 均为旧模块 HMR 残留，刷新即清）

## 提交

`style: 消息气泡头像 — 用户去头像，机器人换问数精灵🧚放卡片左上方`
