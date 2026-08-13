"""
审计 & 回放相关的 Pydantic 请求/响应模型。
"""

from pydantic import BaseModel

# ── 审计日志 ──────────────────────────────────────────────


class AuditStepSchema(BaseModel):
    """审计中单步执行记录"""

    step_name: str
    step_order: int
    status: str
    timestamp: str | None = None


class AuditEntrySchema(BaseModel):
    """一次问数的完整审计"""

    question: str
    sql: str | None = None
    execution_time_ms: int | None = None
    result_row_count: int | None = None
    steps: list[AuditStepSchema] = []
    started_at: str | None = None
    finished_at: str | None = None


class AuditTrailResponse(BaseModel):
    conversation_id: str
    entries: list[AuditEntrySchema]


# ── Checkpoint 回放 ───────────────────────────────────────


class CheckpointSummarySchema(BaseModel):
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step_number: int
    source: str
    node_name: str | None = None
    timestamp: str | None = None
    has_sql: bool = False
    has_result: bool = False


class CheckpointListResponse(BaseModel):
    conversation_id: str
    checkpoints: list[CheckpointSummarySchema]
    total_count: int


class CheckpointDetailResponse(BaseModel):
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    timestamp: str | None = None
    state: dict
    metadata: dict
    pending_writes: list[dict]


class StateDiffEntry(BaseModel):
    field: str
    before: object | None = None
    after: object | None = None
    changed: bool


class CheckpointDiffResponse(BaseModel):
    base_checkpoint_id: str
    target_checkpoint_id: str
    diffs: list[StateDiffEntry]
