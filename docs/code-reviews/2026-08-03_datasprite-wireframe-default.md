# 默认主题改 wireframe + 登录页输入框空白化 code-review

**日期：** 2026-08-03
**范围：** 默认主题 datasprite → wireframe（保留切换器）+ 登录页输入框去文字/去背景 + 主题感知

## 背景

宝一句「感觉线框风要更舒服点」→ 把默认主题从品牌羊皮纸 `datasprite` 切到 DaisyUI `wireframe`（切换器保留）。随后宝要求登录页用户名/密码输入框「默认空白，不要有字也不要有背景」。

## 改动文件

| 文件 | 改动内容 | 原因 |
|:---|:---|:---|
| `frontend/src/App.tsx` | `getInitialTheme()` 反转：默认 wireframe，localStorage 明确存了 `datasprite` 才回品牌 | 默认主题切换 |
| `frontend/index.html` | `data-theme="datasprite"` → `wireframe`；防 FOUC 内联脚本逻辑反转 | 首屏默认 wireframe + 持久化读取方向同步 |
| `frontend/src/components/LoginPage.tsx` | ①外层/卡片/logo 改 `bg-base-200`/`bg-base-100`/`bg-base-content` 主题感知 ②error alert `bg-tomato/10 text-tomato` → `bg-error/10 text-error` ③submit 按钮 `bg-moss text-white hover:bg-soot` → `btn btn-primary text-primary-content` ④输入框去 placeholder + `bg-transparent` 透明底 + `readOnly={!usernameTouched}` 防 autofill + form `autoComplete="off"`、密码 `new-password` | ① 主题感知双主题自适应 ② wireframe 下 error 也线框化 ③ 按钮两种主题下自动适配（datasprite=moss 白字 / wireframe=浅灰深字）④ 输入框默认空白无背景，挡住 Chrome autofill 填入旧账号 |
| `frontend/src/styles.css` | 新增 `input:-webkit-autofill` 系列：box-shadow 透明 inset + text-fill-color 随主题 + transition 9999s | 去掉 Chrome autofill 的淡蓝背景，保持主题透明线框感 |

## 审查发现与处理

1. **中危（已修复）**：初版 `readOnly={username === ""}` + onFocus 手动 `removeAttribute` —— 用户输入后清空内容时 username 变 `""`，input 弹回 readOnly，光标卡住需再点一次；且手动操作 DOM 不符合 React 模式。
   → 改用 `usernameTouched` state：初始 `readOnly={!usernameTouched}` 挡住 autofill，onFocus 置 `touched=true` 永久可编辑。清空后不再卡，React 纯 state 驱动。
   → Playwright 实测：填 admin → 清空（readOnly 仍 false）→ 再填 → 登录成功。

2. **低危（不处理，既有项）**：`index.html` `<meta name="theme-color" content="#FAF8F4">` 硬编码羊皮纸色，wireframe 下移动端状态栏仍是羊皮纸。仅移动端 UI 色，桌面无感，且非本次引入。

3. **低危（可控，不处理）**：autofill 透明覆盖是全局 `input:-webkit-autofill`。项目里 input 仅登录页两处（Composer 是 textarea 不受影响），影响面可控。

## 验证结果

- `pnpm test`：10 通过
- `pnpm lint`（tsc --noEmit）：0 错误
- `pnpm build`：成功
- Playwright 实测：
  - 清 localStorage 刷新 → 默认 `data-theme="wireframe"`，body 纯白
  - 登录页输入框：value 空、无 placeholder、背景全透明（label 与 input 均 `rgba(0,0,0,0)`）
  - Chrome autofill 被挡住：username `autoComplete="off"` + 初始 readOnly，密码 `new-password`
  - readOnly 不卡输入：填→清空→再填→登录成功
  - 切换器：切回 datasprite 恢复羊皮纸 moss、localStorage 持久化、登录页双主题均自适应
  - **排雷**：DaisyUI `.btn` 的 `transition: background-color 0.2s` 导致设主题后立即读 computed 拿到过渡中间态（浅灰 0.87），等 450ms 才见真值（datasprite 下 moss `#5e7855`）—— 非 bug，是读取时序假象

## 提交

`feat: 默认主题改 wireframe + 登录页输入框空白无背景防 autofill`（待提交）
