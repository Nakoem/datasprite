# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

DataSprite 问数精灵 🧚 — NL2SQL 智能数据分析系统。自然语言提问 → LangGraph 工作流生成/校验 SQL → SSE 流式返回结果。

## 常用命令

包管理用 **uv**（有 `uv.lock`，`pyproject.toml` 声明依赖，Python >=3.14）。

```bash
# 后端依赖安装
uv sync

# 启动基础设施（MySQL / Qdrant / Elasticsearch / Embedding 服务）
cd docker && docker compose up -d

# 构建元数据知识库（首次运行必做：把 meta 库灌进 Qdrant + ES）
uv run python app/scripts/build_meta_knowledge.py --config conf/meta_config.yaml

# 启动后端（http://localhost:8000/docs 看 API）
uv run uvicorn main:app --reload --port 8000

# Lint / 格式化（ruff，line-length 88，规则 E/F/I）
uv run ruff check .
uv run ruff format .

# 本地单跑整条工作流（无需起后端，直连各客户端跑一次问数）
uv run python -m app.agent.graph

# 前端（frontend/，React 19 + Vite）
cd frontend && pnpm install
pnpm dev        # http://localhost:5173，/api 已代理到 127.0.0.1:8000
pnpm build      # tsc 类型检查 + vite 构建
pnpm lint       # 仅 tsc --noEmit 类型检查
```

**没有测试框架**。验证改动靠 `python -m app.agent.graph`（跑真实工作流）或调 `/api/query`。

## 环境要求

- `.env` 里必须有 `LLM_API_KEY`（配置用 OmegaConf 的 `${oc.env:LLM_API_KEY}` 注入）
- 数据库口令等基础设施配置写在 `conf/app_config.yaml`（localhost，账号 didilili）

## 架构：一次问数的全链路

请求路径：`main.py` → `query_router` (`POST /api/query`) → `QueryService.query()` → `graph.astream(stream_mode="custom")` → 逐段 `yield "data: {...}\n\n"` SSE。

核心是 **LangGraph 工作流**（`app/agent/graph.py`）。节点间用 `DataAgentState`（TypedDict，会合并）传数据，外部依赖用 `DataAgentContext`（TypedDict，不合并）传递。执行链路：

```
extract_keywords
   ├─▶ recall_column  (Qdrant 向量检索字段)
   ├─▶ recall_value   (ES 全文检索字段取值)
   └─▶ recall_metric  (Qdrant 向量检索指标)
         ▼ (三路召回汇合)
merge_retrieved_info  (按 id 回 Meta MySQL 补齐结构)
   ├─▶ filter_table   (LLM 筛候选表)
   └─▶ filter_metric  (LLM 筛候选指标)
         ▼
add_extra_context  (补日期 + 从 DW MySQL 读方言/版本)
   ▼
generate_sql ─▶ validate_sql ─┬─(error is None)──────────────▶ run_sql ─▶ END
                              └─(有 error 且重试<3)─▶ correct_sql ─(回 validate_sql)
```

**SQL 修正闭环**：`validate_sql` 用 `EXPLAIN` 校验，失败且 `correct_retry_count < MAX_CORRECT_RETRIES`(=3) 时进 `correct_sql` 再回 `validate_sql`；超限则直接 `run_sql` 让错误暴露给用户。条件路由逻辑在 `graph.py` 的 `add_conditional_edges`。

初始 State 只有 `query` 和 `correct_retry_count`，其余字段由各节点逐步写入（`state.py` 里 `total=False`）。

## 分层与依赖注入

严格分层，每层只依赖下一层，禁止跨层直连基础设施：

- `app/api/` — 路由（`routers/`）+ 请求体（`schemas/`）+ **依赖组装**（`dependencies.py`，所有 `Depends` 递归组装 Session/Repository/Client/Service 都收敛在这）+ `lifespan.py`
- `app/services/` — 业务编排。`query_service.py` 组装 State/Context 并消费图流式输出；`meta_knowledge_service.py` 构建知识库
- `app/agent/` — LangGraph 图 + 节点（`nodes/`）+ State/Context/LLM 封装
- `app/repositories/` — 数据访问，按存储分：`mysql/meta`（元数据，含 mapper）、`mysql/dw`（数仓）、`qdrant`（字段/指标向量）、`es`（取值全文）
- `app/clients/` — 单例 `*_client_manager`，`init()`/`close()` 由 `lifespan` 统一管理，请求内不重复初始化
- `app/entities/`（领域实体）vs `app/models/`（SQLAlchemy 表模型）— 两者分开，别混用
- `app/conf/` — OmegaConf 配置加载（读 `conf/*.yaml`）

**客户端生命周期**：应用级资源在 `lifespan` 启动时 `init()` 一次、关闭时 `close()`；请求级 Session 通过 `get_*_session` 依赖用 `async with` 创建并自动清理。新增外部依赖时走 `dependencies.py` 注入，不要在节点或 service 里直接 new 客户端。

## LLM 与提示词

- 模型经 `app/agent/llm.py` 单例初始化：`init_chat_model` + OpenAI 兼容协议，接阿里云 DashScope（qwen3.7-max），`temperature=0` 保稳定
- 提示词是 `prompts/*.prompt` 纯文本文件，通过 `app/prompt/prompt_loader.py` 加载 —— 改提示词直接改这些文件，别硬编码进节点

## 数据模型

数仓是星型模型：1 事实表 + 4 维度表。元数据库（`meta`）存字段/指标/表的结构描述与别名，是召回和补齐的知识来源；数仓库（`dw`）是真实业务数据 + 执行环境（方言/版本）。

## 待办清单

功能进度看 [TODO.md](TODO.md)（14 项，已完 1）。优先级：`P0 可视化图表+结果导出` → `P1 多轮问数+意图澄清+查询历史` → `P2 权限+SQL安全+定时报告` → `P3 知识库混合+评测+缓存+部署`。

## Git

- 远程：https://github.com/Nakoem/datasprite
- 规则：小改先 commit 攒着，多了再一起 push
- commit 前先跑 code-review skill，修完 HIGH/MEDIUM 再提交
