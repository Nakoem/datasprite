"""
Checkpoint 相关领域实体

从 LangGraph MySQLSaver 的 langgraph_checkpoints /
langgraph_checkpoint_writes 表中读取并整理后的数据结构。
"""

from dataclasses import dataclass, field


@dataclass
class CheckpointInfo:
    """单个 checkpoint 的摘要信息，供审计日志和回放面板使用。"""

    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    step_number: int = 0
    source: str = ""
    node_name: str | None = None
    timestamp: str | None = None
    channel_values: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class AuditEntry:
    """一次问数（一条 query → SQL → 结果）的审计记录。"""

    question: str
    sql: str | None = None
    execution_time_ms: int | None = None
    result_row_count: int | None = None
    steps: list[dict] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
