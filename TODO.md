# DataSprite 待办清单 🧚

> 功能进度追踪。项目架构/命令看 [CLAUDE.md](CLAUDE.md)。

## 进度：31 / 37

## 作者建议（7项）

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 1 | 权限控制 | 🎨 登录页 | ✅ 已完 |
| 2 | SQL安全（只读/黑名单/超时/行数限制/参数化防注入/密码脱敏）| ✅ 已完 |
| 3 | 多轮问数（会话记忆+追问） | 🎨 会话列表 | ✅ 已完 |
| 4 | 结果解释（AI摘要+口径说明） | 🎨 摘要卡片 | ✅ 已完 |
| 5 | 缓存性能（召回/Embedding/热点缓存） | ❌ | ✅ 已完 |
| 6 | 评测体系（问题集+评估正确率） | ❌ | ✅ 已完 |
| 7 | 部署运维（健康检查/日志落地/监控/告警/链路追踪） | ❌ | ✅ 已完 |

## 雪玲补充（8项）

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 8 | 🔄 SQL修正闭环（correct→validate+N次上限） | ❌ | ✅ 已完 |
| 9 | 📊 可视化图表（6种图表自动检测+多系列） | 🎨 图表组件 | ✅ 已完 |
| 10 | 📥 结果导出 CSV/Excel | 🎨 导出按钮 | ✅ 已完 |
| 11 | 💬 意图澄清（模糊时主动追问） | 🎨 追问气泡 | ✅ 已完 |
| 12 | 📜 查询历史+收藏 | 🎨 侧边栏列表 | ✅ 已完 |
| 13 | ⏰ 定时报告（定时SQL+推送） | 🎨 配置页 | ⬜ |
| 32 | 📱 微信小程序版（Taro框架复用React代码 → 微信内直接问数） | 🎨 小程序端 | ⬜ |
| 35 | 🔧 评测结果集对比优化（时间维度键规范化，修 q12 月度标签格式漂移盲区） | ❌ | ✅ 已完 |
| 36 | 🔄 评测器多轮上下文支持（评测集可带前置上下文，纳入「那华北区呢」等多轮指代样本，2026-08-06 dify 实测沉淀） | ❌ | ✅ 已完 |
| 37 | 🤖 评测候选 AI 审核 + 一键晋升闭环（自动捕获 → LLM 判 promote/filter/defer + 独立SQL硬验证防自评陷阱 → `--apply` 一键晋升可 git 回退） | ❌ | ✅ 已完 |
| 38 | 💰 全链路 Token 归集（一次 /api/ask 到底烧多少 token → 随响应透传给 Dify/飞书，补上成本核算最大盲区）| ❌ | ✅ 已完 |

## nanobot 启发（3项）🆕

> 2026-07-17 读 nanobot 源码后总结的设计模式，对 DataSprite 架构升级有直接参考价值。

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 23 | 📡 多端接入 Channel 抽象层（BaseChannel 接口 + Registry 自动发现 + Manager 生命周期） | 🎨 微信/钉钉接入页 | ⬜ |
| 24 | 🧠 Dream 记忆压缩（token 预算检测 → LLM 摘要 → 追加式历史，防上下文溢出） | ❌ | ✅ 已完 |
| 25 | 🔌 数据源懒加载 Registry（pkgutil 扫描 + 只导入已配置的数据源，节省启动开销） | ❌ | 🕐 延后（当前 6 数据源全必用 + 单环境 docker 一把起，YAGNI；等接入可选数据源/多环境部署再做，2026-08-17 标注） |

> **参考**：nanobot 源码 `channels/base.py` + `channels/registry.py` + `channels/manager.py` + `agent/memory.py`

## 🏗️ 架构升级 — AgentScope SaaS 化（1项）🆕

> 2026-07-22 调研 AgentScope 2.0（阿里开源，生产级Agent框架）。
> 自带：多租户/多会话/权限控制/沙箱隔离/Event流式推送/长期记忆/RAG服务。
> 可省掉手写用户系统+权限+部署运维的大量代码。

```
DataSprite v1.0  (现在)     →  DataSprite v2.0  (未来)
─────────────────────           ─────────────────────
✅ NL2SQL 12节点引擎           ✅ 保留核心引擎
✅ React 前端                  ✅ 换 AgentScope 外壳
⬜ 图表/多轮对话/前端美化       ✅ 多用户 SaaS 化
                                ✅ 权限+沙箱开箱即用
```

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 31 | 🔄 AgentScope 架构迁移（保留 NL2SQL 12节点核心 → 套 AgentScope 企业级外壳 → 多用户 SaaS 化） | 🎨 换 AgentScope Web UI | ⬜ |

> ⚠️ 等 DataSprite v1.0 稳定（图表+多轮对话+前端美化 全搞定）后再评估迁移，AgentScope v2.0 才发布2个月，API可能变动。

## RAG 增强（1项）🆕

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 26 | 🔍 后置 RAG 语义校验+引用补全（①语义核对 ✅ → ②引用补全 ✅） | 🎨 引用标注卡片 | ✅ 已完 |

## 生产交付补全（7项）

| # | 功能 | 涉及前端 | 状态 |
|:--|:---|:--:|:--:|
| 15 | 🛡️ 全局异常处理中间件 | ❌ | ✅ 已完 |
| 16 | 🚦 API 限流（令牌桶） | ❌ | ✅ 已完 |
| 17 | 🔌 连接池调优（overflow/recycle/timeout） | ❌ | ✅ 已完 |
| 18 | 🤖 LLM 调用容错（超时+重试+降级） | ❌ | ✅ 已完 |
| 19 | 🎨 前端边界态收尾（loading动画+错误重试+空列表提示） | 🎨 骨架屏/重试按钮 | ✅ 已完 |
| 20 | 🧪 测试体系 | ❌ | ✅ 已完 |
| 21 | 🔄 CI/CD 流水线 | ❌ | ✅ 已完 |
| 22 | 📨 消息队列异步削峰（Celery + Redis） | ❌ | 🕐 延后（SSE 实时流式与异步队列产品形态互斥 + 低并发无峰值可削 + 已有 #34 超时/#16 限流，YAGNI；等产品转向异步出报告形态再做，2026-08-17 标注） |
| 27 | 📝 SQL全链路审计日志（谁问了什么→生成了什么SQL→执行耗时→结果行数→操作记录，不可篡改） | ❌ | ✅ 已完 |
| 28 | 💾 LangGraph checkpointer 接入（state 持久化 + 断点恢复 + 时间回溯 + 人机协同中断） | ❌ | ✅ 已完 |
| 29 | 🗺️ 前端流程图补齐（4个新节点：意图分类/追问澄清/语义校验/结果摘要） | 🎨 流程Svg | ✅ 已完 |
| 30 | 🎬 Checkpoint 回放面板（时间线拖拽 + State Diff + 逐帧回放，debug 用）→ 跟 #27 审计日志一起做，同源数据 | 🎨 回放面板 | ✅ 已完 |
| 33 | 🔌 封装 API 服务（FastAPI 壳 → `/ask` 接口 → 返回 SQL + 数据 + AI 摘要，可供 Dify/飞书/钉钉等外部系统调用） | ❌ | ✅ 已完 |
| 34 | ⏱️ query_sync 整体超时（`asyncio.wait_for` 防 LLM 假死挂起） | ❌ | ✅ 已完 |

---

## 💰 #38 全链路 Token 归集 — 详细规格（2026-08-31 立项）

> **来源**：feishu-bridge 侧做成本核算时发现的盲区。跨 3 个服务，DataSprite 是主战场。

### 一、问题是什么

飞书智能客服的问数链路是 `飞书 → feishu-bridge → Dify → DataSprite`。
feishu-bridge 记的 token 数**照抄 Dify 返回的 `usage.total_tokens`**，而
**Dify 的 HTTP 请求节点是个黑盒 —— 它不知道 DataSprite 内部烧了多少**。

**实测铁证**（Dify `workflow_node_executions`，run `37a22382`，2026-08-15）：

| 节点 | node_type | token | 耗时 |
|---|---|---:|---:|
| LLM 2（结果解读） | llm | 32,656 | 18.3s |
| 问题分类器 2 | question-classifier | 1,891 | 15.5s |
| 参数提取器 | parameter-extractor | 1,607 | 14.4s |
| 问题分类器 | question-classifier | 1,534 | 7.3s |
| **HTTP 请求（调 DataSprite）** | http-request | **0** | **88.4s** ⚠️ |
| 合计 | | **37,688** | |

**那 88.4 秒里 DataSprite 跑了 6-7 次 LLM 调用，token 无人记录。**
本仓库自有代码 token 记账 = **0 处**（`grep token --include=*.py app` 只命中 .venv 第三方库），
LLM 调用点共 **13 处**（`app/agent/nodes/` 下 classify_intent / generate_sql / correct_sql /
filter_table / filter_metric / recall_column / recall_metric / recall_value / dream 等）。

> 结论：飞书那边记的「问数一次 37,688 token」是**低估值**，真实成本未知。
> 不补这个洞，任何成本核算/报价都是假的。

### 二、方案（三层，只做①就有 80% 价值）

```
① DataSprite 自己数   一次 /api/ask 累计 token（input/output/total）  ← 本项目主体
② 随响应透传          /api/ask 响应加 token_usage 字段 → Dify → feishu-bridge
③ 成本落账            feishu-bridge /stats 汇总真实总量 × 单价 = 钱
```

### 三、技术方案（已勘察，改动很小）

**关键发现：LLM 有单一入口，不必改 13 处。**

- `app/agent/llm.py` 集中用 `init_chat_model(model_provider="openai")` 建实例，
  所有节点 `from app.agent.llm import llm`，**LangChain 的 usage 数据本来就在，只是没人收**
- `app/services/query_service.py:118` 已有 `astream_config = {"configurable": {"thread_id": ...}}`，
  第 119-123 行 `self.compiled_graph.astream(..., config=astream_config, ...)`
  → **LangGraph 会把 config 里的 callbacks 自动下传给图内所有 LLM 调用**

**推荐实现**：

1. 新建 `app/agent/token_meter.py` —— 一个 `BaseCallbackHandler` 子类，
   `on_llm_end` 里从 `response.llm_output["token_usage"]` 或 `AIMessage.usage_metadata`
   累加 `input_tokens / output_tokens / total_tokens`，并按节点名分桶（便于定位大头）
   > ⚠️ **必须每请求 new 一个实例**（不能全局单例，否则并发串账）
2. `query_service.py:118` 的 `astream_config` 加 `"callbacks": [meter]`（**一行**）
3. `_run_graph` 跑完后把 `meter.summary()` 塞进返回结果
4. `query_sync`（:177）/ `/api/ask` 响应加字段：
   ```json
   {"token_usage": {"total": 28450, "input": 24100, "output": 4350,
                    "by_node": {"generate_sql": 8200, "correct_sql": 3100, ...}}}
   ```

**第②层的省事路径（复用现有暗管）**：
Dify 问数分支已在回答尾部拼 `<!--DATA-->{"sql": ..., "chart_image_base64": ...}<!--/DATA-->`，
feishu-bridge 早就在解析它。**只需把 `token_usage` 加进这个 JSON**，零新协议
（与转人工 `<!--HANDOFF-->` 标记同一套路）。

### 四、验收标准

- [x] 跑一次 `/api/ask`，响应里有 `token_usage.total` 且 > 0
  - ✅ **2026-08-31 实测**：单值查询 14,210 / 明细查询 19,427
- [x] `by_node` 能定位到哪个节点最贵（预期 generate_sql / correct_sql 是大头）
  - ✅ 实测大头是 **filter_table（37%！）**，不是 generate_sql —— 表筛选喂了全量候选表 YAML，比 SQL 生成还贵；correct_sql 本次未触发（无修正路径）
- [x] **并发验证**：两个请求同时跑，两边 token 数互不污染（证明不是全局单例）
  - ✅ 双请求并发实测：各自 9 个节点桶、总数 14,210 ≠ 19,427，无串账
- [x] 单值查询 vs 明细查询 的 token 差异被量化（feishu-bridge 侧实测 Dify 部分是 8k vs 36k，差 4.4 倍）
  - ✅ DataSprite 内部为 19,427 / 14,210 = **1.37x**（明细侧 summarize_result +3.5x 是主因：1056 → 3659）
- [ ] 与阿里云百炼控制台的实际用量对得上（±10% 以内）
  - 🕐 机制上用 API 服务端返回的 `llm_output.token_usage`（服务端计数，非本地估算），理论上精确匹配，待宝上控制台核对一次

### 五、做完之后回 feishu-bridge 做②③

feishu-bridge 侧对应条目见该仓库 `智能客服-TODO.md` →「🏭 生产运营风险清单」。
届时可算出这句面试用的话：**「每次问答 ¥X，100 人公司每月 ¥Y，相当于 0.0Z 个客服人力」**。

---

## 优先级

```
P0 生产必备：SQL安全 + 连接池 + 全局异常 + 限流 + 健康检查 + 日志落地
P1 体验升级：多轮问数 + 意图澄清 + 查询历史 + 可视化 + 导出 + 结果解释 + 后置RAG校验 + checkpointer
P2 企业级：  权限控制 + LLM容错 + 定时报告 + 前端边界态 + 数据源懒加载 + 审计日志 + API封装
P3 进阶：    评测体系 + 缓存 + 监控告警 + 测试 + CI/CD + Channel多端 + Dream压缩
```
## Git

- 远程：https://github.com/Nakoem/datasprite
- 规则：小改先 commit 攒着，多了再一起 push
- commit 前先跑 code-review skill，修完 HIGH/MEDIUM 再提交
