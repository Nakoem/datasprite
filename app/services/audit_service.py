"""
审计 & Checkpoint 回放业务服务

从 LangGraph checkpoint 数据中提取：
- 审计日志：谁问了什么 → 生成了什么 SQL → 执行耗时/结果行数
- 回放数据：checkpoint 时间线、State 详情、字段级 diff
"""

from datetime import date, datetime

from app.entities.checkpoint import AuditEntry
from app.repositories.mysql.meta.checkpoint_repository import CheckpointRepository

# 审计列表中 result 最多保留的行数
_MAX_RESULT_ROWS_IN_AUDIT = 100
# _sanitize 最大递归深度，防止循环引用导致栈溢出
_MAX_SANITIZE_DEPTH = 20


def _sanitize(obj: object, _depth: int = 0) -> object:
    """递归将 Python 对象转为 JSON-safe 类型。

    checkpoint 的 channel_values 里可能包含 ColumnInfo 等实体对象，
    FastAPI 的 JSONResponse 无法直接序列化，需要提前转换。
    """
    if _depth > _MAX_SANITIZE_DEPTH:
        return "<max depth exceeded>"
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, (list, tuple)):
        return [_sanitize(i, _depth + 1) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _sanitize(v, _depth + 1) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        return _sanitize(vars(obj), _depth + 1)
    return str(obj)


class AuditService:
    """审计 + 回放业务逻辑。"""

    def __init__(self, checkpoint_repository: CheckpointRepository) -> None:
        self._repo = checkpoint_repository

    # ── 审计日志 ──────────────────────────────────────────

    async def get_audit_trail(self, conversation_id: str) -> dict:
        """构建单次会话的审计轨迹。"""
        checkpoints = await self._repo.list_checkpoints(conversation_id)
        if not checkpoints:
            return {"conversation_id": conversation_id, "entries": []}

        entries: list[AuditEntry] = []
        current_group: list = []
        last_query: str | None = None

        for cp in checkpoints:
            cv = cp.channel_values
            query = cv.get("query")
            # 检测 query 变化 → 新一轮问数开始
            if query and query != last_query:
                if current_group:
                    entries.append(self._build_audit_entry(current_group))
                current_group = [cp]
                last_query = query
            else:
                current_group.append(cp)

        if current_group:
            entries.append(self._build_audit_entry(current_group))

        return {
            "conversation_id": conversation_id,
            "entries": [self._entry_to_dict(e) for e in entries],
        }

    def _build_audit_entry(self, checkpoints: list) -> AuditEntry:
        first = checkpoints[0]
        last = checkpoints[-1]
        question = ""
        sql: str | None = None
        result_row_count: int | None = None

        for cp in checkpoints:
            cv = cp.channel_values
            if cv.get("query") and not question:
                question = cv["query"]
            if cv.get("sql"):
                sql = cv["sql"]
            if isinstance(cv.get("result"), list):
                result_row_count = len(cv["result"])

        # 估算执行耗时
        exec_ms: int | None = None
        if first.timestamp and last.timestamp:
            try:
                t1 = datetime.fromisoformat(
                    first.timestamp.replace("Z", "+00:00")
                )
                t2 = datetime.fromisoformat(
                    last.timestamp.replace("Z", "+00:00")
                )
                exec_ms = int((t2 - t1).total_seconds() * 1000)
            except (ValueError, OSError):
                pass

        steps = []
        for cp in checkpoints:
            node_name = cp.node_name or f"step_{cp.step_number}"
            steps.append({
                "step_name": node_name,
                "step_order": cp.step_number,
                "status": "success",
                "timestamp": cp.timestamp,
            })

        return AuditEntry(
            question=question,
            sql=sql,
            execution_time_ms=exec_ms,
            result_row_count=result_row_count,
            steps=steps,
            started_at=first.timestamp,
            finished_at=last.timestamp,
        )

    @staticmethod
    def _entry_to_dict(entry: AuditEntry) -> dict:
        return {
            "question": entry.question,
            "sql": entry.sql,
            "execution_time_ms": entry.execution_time_ms,
            "result_row_count": entry.result_row_count,
            "steps": entry.steps,
            "started_at": entry.started_at,
            "finished_at": entry.finished_at,
        }

    # ── Checkpoint 回放 ───────────────────────────────────

    async def list_checkpoints(self, conversation_id: str) -> list[dict]:
        checkpoints = await self._repo.list_checkpoints(conversation_id)
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "parent_checkpoint_id": cp.parent_checkpoint_id,
                "step_number": cp.step_number,
                "source": cp.source,
                "node_name": cp.node_name,
                "timestamp": cp.timestamp,
                "has_sql": bool(cp.channel_values.get("sql")),
                "has_result": bool(cp.channel_values.get("result")),
            }
            for cp in checkpoints
        ]

    async def get_checkpoint_detail(
        self, conversation_id: str, checkpoint_id: str
    ) -> dict | None:
        t = await self._repo.get_checkpoint(conversation_id, checkpoint_id)
        if t is None:
            return None
        cp = t.checkpoint
        parent_id: str | None = None
        if t.parent_config is not None:
            parent_id = t.parent_config["configurable"]["checkpoint_id"]

        # 截断大结果集
        state_raw = cp.get("channel_values", {})
        state_sanitized = _sanitize(state_raw)
        if (
            isinstance(state_sanitized, dict)
            and "result" in state_sanitized
            and isinstance(state_sanitized["result"], list)
        ):
            state_sanitized["result"] = state_sanitized["result"][
                :_MAX_RESULT_ROWS_IN_AUDIT
            ]

        pending_writes = []
        for tid, ch, val in t.pending_writes or []:
            pending_writes.append({
                "task_id": tid,
                "channel": ch,
                "value": _sanitize(val),
            })

        return {
            "checkpoint_id": cp["id"],
            "parent_checkpoint_id": parent_id,
            "timestamp": cp.get("ts"),
            "state": state_sanitized,
            "metadata": t.metadata,
            "pending_writes": pending_writes,
        }

    async def diff_checkpoints(
        self, conversation_id: str, base_id: str, target_id: str
    ) -> dict:
        base = await self._repo.get_checkpoint(conversation_id, base_id)
        target = await self._repo.get_checkpoint(conversation_id, target_id)
        if base is None or target is None:
            raise ValueError("Checkpoint not found")

        base_state = base.checkpoint.get("channel_values", {})
        target_state = target.checkpoint.get("channel_values", {})

        all_keys = sorted(
            set(base_state.keys()) | set(target_state.keys())
        )
        diffs = []
        for key in all_keys:
            before = _sanitize(base_state.get(key))
            after = _sanitize(target_state.get(key))
            diffs.append({
                "field": key,
                "before": before,
                "after": after,
                "changed": before != after,
            })

        return {
            "base_checkpoint_id": base_id,
            "target_checkpoint_id": target_id,
            "diffs": diffs,
        }
