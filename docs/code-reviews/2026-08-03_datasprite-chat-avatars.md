# 消息气泡头像换 DiceBear 在线头像 code-review

**日期：** 2026-08-03
**范围：** 消息气泡头像素材替换（lucide 线条图标 → DiceBear 在线头像图片）

## 背景

宝觉得 lucide 线条图标头像「感觉一般」，问 DaisyUI 有无头像可选 → 说明 avatar 是容器非图库，经 AskUserQuestion 选「在线头像图片 🎭」：DiceBear 免费在线头像服务（无需 key）。

## 改动文件

| 文件 | 改动内容 | 原因 |
|:---|:---|:---|
| `frontend/src/components/MessageBubble.tsx` | 新增 `ChatAvatar` 小组件（img + onError 回退图标圆底）；助手头像 → DiceBear bottts 机器人（`seed=DataSprite`）；用户头像 → DiceBear notionists 人形（`seed=Nakko`）；`rounded-full ring-1 ring-ink/10` 圆形裁剪 + 线框描边 | 替换头像素材为真实图片，区分度更高，品牌感强；固定 seed 保证头像稳定 |

## 审查发现与处理

1. **低危（已处理）**：头像依赖第三方在线服务 DiceBear，离线时 img 裂图。
   → `ChatAvatar` 内 `onError` 置 failed state，回退到原图标圆底（助手 Sparkles / 用户 CircleUserRound）。实测离线兜底逻辑就位。

2. **低危（可接受）**：外部网络依赖增加首屏请求。`loading="lazy"` 已加，仅可视消息加载，影响可控。

## 验证结果

- `pnpm test`：10 通过
- `pnpm lint`（tsc --noEmit）：0 错误
- `pnpm build`：成功
- Playwright 实测：两处 `.chat-image img` 均 `loaded=true`（naturalWidth 150），bottts 助手 / notionists 用户加载成功；父容器 `w-9 rounded-full` 圆角 2.23e7px + `overflow:hidden`，36×36 正圆裁剪 + ring 描边；`objectFit: cover`

## 提交

`style: 消息气泡头像换 DiceBear 在线头像 — 助手 bottts / 用户 notionists（失败回退图标）`
