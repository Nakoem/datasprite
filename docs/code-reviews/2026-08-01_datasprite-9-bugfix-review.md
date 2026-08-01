# Code Review — 2026-08-01 全链路 9 项 Bug 修复

审查范围：上一轮对问数精灵全链路的系统性 review 发现的 9 个问题，本轮按严重度从高到低全部修复。

## 修复清单

| # | 严重度 | 位置 | 问题 | 修复 |
|:--|:--:|:---|:---|:---|
| 1 | HIGH | `conversation_repository.py` | `get_recent_messages` 复用 `get_messages`（ASC 取最早），多轮对话超过 5 轮后把最近追问上下文整个丢掉 | 改为 `ORDER BY created_at DESC LIMIT :limit` 再 `reverse()`，最近 N 条按正序交给 LLM |
| 2 | HIGH | `conversation_repository.py` | `add_message` 不刷新会话更新时间，会话列表按 `updated_at` 排序永远失效 | 落库前 `UPDATE conversations SET updated_at = NOW()`，与 INSERT 同事务 |
| 3 | MEDIUM | `merge_retrieved_info.py` | `get_column_info_by_id` / `get_table_info_by_id` 返回 `None` 时直接塞进 map / 用 `.table_id` / `.name`，字段被下线即崩溃 | 三处补 `is None` 判断，查不到则 `continue` 跳过并 `logger.warning` |
| 4 | MEDIUM | `query_service.py` + 三个 client | `/api/query`（SSE）无整体超时，LLM 假死导致 SSE 挂起不落帧；Embedding/Qdrant/ES 客户端无显式超时，基础设施"假死"即无限挂起 | `query()` 用 `asyncio.timeout(query_timeout)` 包裹；Embedding `request_timeout=60/max_retries=2`、Qdrant `timeout=30`、ES `request_timeout=30` |
| 5 | MEDIUM | 5 个 recall/filter 节点 | LLM 偶发输出 dict/str 而非数组，`keywords + result`、`x in result` 抛 TypeError 或逻辑错乱 | 新增 `_llm_guard.ensure_str_list()`；filter 节点格式异常时降级为"不过滤，保留全部候选"（详见审查发现） |
| 6 | LOW | `embedding_client_manager.py` + `lifespan.py` | Embedding 客户端无 `close()`，关闭阶段漏释放 | 补幂等 `close()`（`getattr` 探测），lifespan 关闭阶段调用 |
| 7 | LOW | `main.py` | OTLP exporter 初始化任何异常都会拖垮应用 import；collector 挂死会拖住后台导出线程 | try/except 包裹 + `timeout=3`，`set_tracer_provider` 无条件执行 |
| 8 | LOW | `checkpointer.py` | 全局 `asyncio.Lock` 把所有会话的 checkpoint 读写串行化，并发瓶颈 | 锁收窄到 `setup()`（幂等建表），其余方法靠 SQLAlchemy 连接池并发安全（REPLACE/INSERT IGNORE 幂等） |
| 9 | LOW | `lifespan.py` | 每次启动都对 messages 表执行一次必然失败的 `ALTER TABLE`（try/except 静默） | 先查 `information_schema.columns`，不存在才 ALTER |

## 审查中发现并修复的新问题

修复 #5 时**引入并当场发现**两个真实的降级语义 bug（比原问题严重）：

1. **filter_table / filter_metric 降级方向反了**：格式异常时最初写的是 `result = {}` / `result = []`，随后裁剪循环把**所有**候选表/指标筛掉 → 下游 SQL 生成阶段没有表/指标可用。已改为格式异常时**不过滤，原样保留全部候选**。
2. **filter_metric 注释与实现矛盾**：注释写"保留全部候选指标"，实现却把指标全筛空。同上修正。

## 真实运行验证新发现的问题（静态审查测不出的）

3. **HuggingFaceEndpointEmbeddings 不支持 `request_timeout`/`max_retries`**（Bug 27）：当前 langchain_huggingface 版本 `model_config extra=forbid`，传这两个参数直接 pydantic `ValidationError` → **应用启动即崩**。静态审查只假设参数存在（凭记忆），真实跑 `python -m app.agent.graph` 才暴露。修复：子类化 `_TimeoutEmbeddings`，在 `aembed_query` 方法级包 `asyncio.wait_for(timeout=60)` 兜底假死。
4. **`get_recent_messages` created_at 同秒排序不稳定**（Bug 28）：用户连发多条消息时 `created_at` 同秒，仅 `ORDER BY created_at DESC` 不保证取到"最近 N 条"。修复：加次级排序键 `ORDER BY created_at DESC, id DESC`（id 自增反映插入顺序）；`get_messages` 同步补 `id ASC`。真实 DB 脚本验证：同秒插 15 条，`get_recent_messages(limit=10)` 正确返回 msg-5..msg-14 正序。
5. **ES 容器 OOM**（配置修复）：Docker Desktop 上 ES 默认按容器内存抢一半堆（~5GB）必 OOM。docker-compose.yaml 加 `ES_JAVA_OPTS: "-Xms1g -Xmx1g"`，单节点测试环境 1GB 足够。

## 代码审查五项检查

| 检查项 | 结果 |
|:---|:---|
| 改动范围 | ✅ 全部对应 9 项 + conf/app_config.yaml（模型名，之前已确认的改动） |
| 误改文件 | ✅ 无配置/缓存文件；5 张未跟踪 png 截图不纳入提交 |
| 接口兼容 | ✅ 无签名/字段/API 变化；`get_recent_messages` 行为变化正是修复目标 |
| 异常处理 | ✅ 三处 None 防御、五节点格式校验、query 超时、lifespan 兜底 |
| 重复逻辑 | ✅ 三处 recall 相同防御块提取到 `_llm_guard.ensure_str_list()` |

## 验证结果

- `ruff check`（全部改动文件）：✅ 全绿
- `py_compile` + import 冒烟测试（helper 单测 + 13 模块 + `import main`）：✅ 通过
- **真实工作流** `python -m app.agent.graph`：✅ 17 节点全链路跑通，SQL 生成正确（`SELECT SUM(t1.order_amount) ... WHERE t2.region_name='华北'`），执行返回 `[{'销售总额': 1701802.0}]`，摘要生成成功。ES 修复后 recall_value 正常
- **会话层 DB 验证**（真实 MySQL）：✅ #1 同秒插 15 条取最近 10 条正序；#2 `updated_at` 随 add_message 刷新
- 遗留：全项目 `ruff check .` 有 2 个 chart_service.py 的 I001（历史遗留，非本轮改动，未顺手改）

## 未覆盖验证

- `query()` 的 `asyncio.timeout`（#4）：与 `query_sync` 的 `asyncio.wait_for` 同款模式（生产在用），语法/编译通过，未做假死实测
- `checkpointer` 锁收窄并发（#8）：单机无并发测试框架，逻辑分析（REPLACE/INSERT IGNORE 幂等 + 连接池安全）

## 建议回归测试

- [ ] 多轮对话 >5 轮后追问，确认 LLM 上下文包含最近追问（#1，DB 已验证）
- [ ] 对话列表：新消息落库后会话置顶（#2，DB 已验证）
- [ ] 停掉 Qdrant/ES/Embedding 其中一个，问数应超时/降级而非挂起（#4）
- [ ] 让 LLM 返回 dict 而非数组的扩展词，确认召回节点不崩且用原始关键词（#5）
