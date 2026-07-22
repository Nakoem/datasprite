# Code Review: #20 测试体系 + #21 CI/CD 流水线

> **日期**: 2026-07-22 | **审查人**: 雪玲 | **commit**: `6c518df`
> **改动规模**: 19 files, +1912 / -5 lines

---

## 改动摘要

### 改动文件

| 文件 | 改动内容 | 原因 |
|:---|:---|:---|
| `pyproject.toml` | +pytest, pytest-asyncio, pytest-mock | 后端测试框架 |
| `tests/conftest.py` | 新建 — FakeLLM + 6 Fake仓储 + 缓存mock | 测试基础设施，所有测试复用 |
| `tests/test_nodes/test_extract_keywords.py` | 新建 — 3测试 | 最简节点（纯 jieba），验证管道通 |
| `tests/test_nodes/test_validate_sql.py` | 新建 — 3测试 | SQL 安全边界（语法错/基础设施错） |
| `tests/test_nodes/test_generate_sql.py` | 新建 — 1测试 | LLM 节点模式模板 |
| `tests/test_nodes/test_semantic_validate.py` | 新建 — 3测试 | 保守透传逻辑（宁放过不误杀） |
| `tests/test_nodes/test_correct_sql.py` | 新建 — 1测试 | 重试计数器递增 + error 清除 |
| `tests/test_graph_integration.py` | 新建 — 2集成测试 | 全图 happy path + SQL 修正重试闭环 |
| `frontend/package.json` | +vitest, testing-library, jsdom | 前端测试依赖 |
| `frontend/vite.config.ts` | +test 配置块 | vitest + jsdom 环境 |
| `frontend/src/test-setup.ts` | 新建 — jest-dom + auto cleanup | 前端测试基础设施 |
| `frontend/src/components/__tests__/Composer.test.tsx` | 新建 — 6测试 | 回车提交/Shift换行/停止/禁用 |
| `frontend/src/components/__tests__/StepRail.test.tsx` | 新建 — 4测试 | 空态/节点渲染/标题/状态样式 |
| `.github/workflows/ci.yml` | 新建 | push/PR → lint+test 自动运行 |
| `TODO.md` | 18/32→20/32, #20 #21→✅ | 进度追踪 |

### 未提交的文件（确认不相关）
`.playwright-mcp/`, `*.png`, `frontend/public/` — 非本次改动产生，未纳入 commit。

---

## 逐项检查

### 1. 改动范围是否超出指令 ✅
所有改动严格在 #20（测试体系）和 #21（CI/CD）范围内，无范围外变更。

### 2. 是否改了不该改的文件 ✅
- `uv.lock` / `pnpm-lock.yaml` — 依赖变更自动更新，正常
- 无 `.env` / `__pycache__` / 配置文件误入
- `.gitignore` 已覆盖无关文件

### 3. 接口和数据结构是否保持兼容 ✅
- 所有改动纯新增，无 API/签名/TypedDict 变更
- Fake 仓储通过鸭子类型匹配真实接口（无 ABC/Protocol，避免大规模重构）

### 4. 异常处理 ✅
- **FakeLLM**: 队列耗尽时回退 `_response`，不会崩溃
- **FakeDWMySQLRepository**: 支持单 Exception 和 `list[Exception|None]` 两种模式
- **语义校验**: `test_semantic_validate_conservative_on_llm_failure` 验证了 LLM 异常→保守放行
- **validate_sql**: `test_validate_sql_raises_on_infra_error` 验证了基础设施错→抛出
- **集成测试**: `test_graph_retry_loop` 验证了 3 次修正上限 + 超限后仍执行

### 5. 重复逻辑 ✅
- `_FakeStreamWriter` 统一定义在 `conftest.py`，各测试复用
- `make_runtime()` 辅助函数在 `conftest.py`
- 各节点的 `_state()` helper 有轻微重复，但每个节点 State 字段不同，属合理差异
- `_patch_llm_modules()` / `_patch_llm_modules_direct()` 在集成测试中封装，避免散落

---

## 发现的问题 & 修复

| # | 严重度 | 位置 | 问题 | 修复 |
|:--|:--|:---|:---|:---|
| 1 | 中危 | `tests/test_graph_integration.py:174` | `test_graph_retry_loop` 断言计数 6 而非 3（每个调用产生 running+success 两个事件） | 加 `and e.get("status") == "running"` 过滤 |
| 2 | 低危 | `tests/conftest.py:8` | import 顺序不符合 isort（stdlib 与 third-party 分组间缺空行） | ruff --fix 自动修复 |
| 3 | 低危 | `tests/test_graph_integration.py:42` | 未使用的 `import importlib` | 已移除 |
| 4 | 低危 | `tests/test_graph_integration.py:131` | 未使用的 `MAX_CORRECT_RETRIES` | 已移除 |
| 5 | 低危 | `StepRail.test.tsx:18-23` | `"pending"` 不是合法的 `ProgressStatus` 值 | 已修正为仅传有状态的步骤 |
| 6 | 低危 | `Composer.test.tsx` | 测试间 DOM 未自动清理（vitest v4 + RTL v16 兼容性） | `test-setup.ts` 加 `afterEach(cleanup)` |

---

## 剩余风险

- [低] CI 中 `astral-sh/setup-uv@v5` 的 `python-version: "3.14"` 依赖 GitHub Actions runner 支持，如不支持可回退到 `uv python install 3.14`
- [低] `pnpm/action-setup@v4` 首次使用，需观察 CI 实际运行
- [低] LangChain `asyncio.iscoroutinefunction` 废弃警告（Python 3.16 移除），不影响功能

---

## 验证结果

```
后端: uv run pytest tests/ -v  →  13 passed ✅
前端: pnpm test                →  10 passed ✅
Lint: ruff check tests/        →  All checks passed ✅
Lint: pnpm lint (tsc)          →  clean ✅
```

---

## 总结

**审查结论：通过 ✅** — 所有 HIGH/MEDIUM 问题已修复，可以合入。

测试体系从零到 23 个测试覆盖关键路径（5 个节点 + 2 个集成覆盖全图 17 节点 + 2 个前端组件），CI 流水线自动化 lint + test。后续建议持续为新功能补测试，逐步提升覆盖率。
