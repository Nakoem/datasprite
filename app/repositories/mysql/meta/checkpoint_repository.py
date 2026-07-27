"""
Checkpoint 数据访问层

封装 LangGraph MySQLSaver 的 alist() / aget_tuple() 方法，
提供按 conversation_id（= thread_id）查询 checkpoint 的能力。
不直接操作 SQL —— MySQLSaver 内部已处理 msgpack 反序列化。
"""

from langgraph.checkpoint.base import CheckpointTuple

from app.agent.checkpointer import MySQLSaver
from app.core.log import logger
from app.entities.checkpoint import CheckpointInfo

# 单次 list_checkpoints 返回上限，防止超长会话拖慢接口
_DEFAULT_LIMIT = 200


class CheckpointRepository:
    """只读访问 LangGraph checkpoint 数据。"""

    def __init__(self, checkpointer: MySQLSaver) -> None:
        self._checkpointer = checkpointer

    async def list_checkpoints(
        self, thread_id: str, limit: int = _DEFAULT_LIMIT
    ) -> list[CheckpointInfo]:
        """列出某个会话的 checkpoint，按时间升序排列，最多返回 limit 条。"""
        config = {"configurable": {"thread_id": thread_id}}
        tuples: list[CheckpointTuple] = []
        async for t in self._checkpointer.alist(config, limit=limit):
            tuples.append(t)
        # alist 默认 ORDER BY checkpoint_id DESC，反转得到升序
        tuples.reverse()
        if len(tuples) >= limit:
            logger.info(
                "checkpoint 列表已达上限 | thread_id={} limit={}",
                thread_id,
                limit,
            )
        return [self._to_checkpoint_info(t) for t in tuples]

    async def get_checkpoint(
        self, thread_id: str, checkpoint_id: str
    ) -> CheckpointTuple | None:
        """获取某个会话的特定 checkpoint。"""
        config: dict = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        return await self._checkpointer.aget_tuple(config)

    @staticmethod
    def _to_checkpoint_info(t: CheckpointTuple) -> CheckpointInfo:
        cp = t.checkpoint
        meta = t.metadata

        # 从 pending_writes 提取节点名（第一个 task_id 就是执行节点名）
        node_name: str | None = None
        if t.pending_writes:
            node_name = t.pending_writes[0][0]

        parent_id: str | None = None
        if t.parent_config is not None:
            parent_id = t.parent_config["configurable"]["checkpoint_id"]

        return CheckpointInfo(
            checkpoint_id=cp["id"],
            parent_checkpoint_id=parent_id,
            step_number=meta.get("step", 0),
            source=meta.get("source", ""),
            node_name=node_name,
            timestamp=cp.get("ts"),
            channel_values=cp.get("channel_values", {}),
            metadata=meta,
        )
