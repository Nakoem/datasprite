"""
LangGraph MySQL Checkpointer

参照官方 AsyncSqliteSaver 实现，为 DataSprite 提供 LangGraph state
持久化能力。每次节点执行后 state 自动存档到 MySQL，支持：

- state 持久化：服务重启后可从断点恢复
- 时间回溯：可回退到任意历史 checkpoint 重跑
- 线程隔离：每个 conversation_id 对应一个 thread_id

所有 DB 操作通过 SQLAlchemy AsyncEngine 走 meta 库的已有连接池。
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.log import logger

# ── helpers ──

def _search_where(
    config: RunnableConfig | None,
    filter: dict[str, Any] | None = None,
    before: RunnableConfig | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a MySQL WHERE clause for listing checkpoints.

    返回 (where_clause, params_dict)，where_clause 以 "WHERE ..." 开头。
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if config is not None:
        clauses.append("thread_id = :thread_id")
        params["thread_id"] = str(config["configurable"]["thread_id"])

        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        if checkpoint_ns:
            clauses.append("checkpoint_ns = :checkpoint_ns")
            params["checkpoint_ns"] = checkpoint_ns

        if checkpoint_id := get_checkpoint_id(config):
            clauses.append("checkpoint_id = :checkpoint_id")
            params["checkpoint_id"] = checkpoint_id

    if before is not None:
        clauses.append("checkpoint_id < :before_cid")
        params["before_cid"] = str(before["configurable"]["checkpoint_id"])

    if filter is not None:
        for k, v in filter.items():
            clauses.append("JSON_EXTRACT(metadata, :filter_key_{k}) = :filter_val_{k}")
            params[f"filter_key_{k}"] = f"$.{k}"
            params[f"filter_val_{k}"] = json.dumps(v)

    if not clauses:
        return "WHERE 1=1", params
    return "WHERE " + " AND ".join(clauses), params


# ── MySQLSaver ──

class MySQLSaver(BaseCheckpointSaver[str]):
    """MySQL 异步 checkpoint 存储。

    用法：
        engine = create_async_engine("mysql+asyncmy://...")
        checkpointer = MySQLSaver(engine)
        graph = graph_builder.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "conversation-uuid"}}
        async for event in graph.astream(state, config=config):
            ...
    """

    lock: asyncio.Lock
    is_setup: bool

    def __init__(self, async_engine: AsyncEngine) -> None:
        super().__init__()
        self.engine = async_engine
        self.lock = asyncio.Lock()
        self.loop = asyncio.get_running_loop()
        self.is_setup = False

    @classmethod
    def from_conn_string(cls, conn_string: str) -> MySQLSaver:
        """从 SQLAlchemy 连接字符串创建实例。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            conn_string,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
        )
        return cls(engine)

    # ── Setup ──

    async def setup(self) -> None:
        """建表（幂等）。"""
        async with self.lock:
            if self.is_setup:
                return
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
                            thread_id         VARCHAR(128) NOT NULL,
                            checkpoint_ns     VARCHAR(128) NOT NULL DEFAULT '',
                            checkpoint_id     VARCHAR(64) NOT NULL,
                            parent_checkpoint_id VARCHAR(64),
                            type              VARCHAR(16),
                            checkpoint        MEDIUMBLOB,
                            metadata          MEDIUMBLOB,
                            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS langgraph_checkpoint_writes (
                            thread_id         VARCHAR(128) NOT NULL,
                            checkpoint_ns     VARCHAR(128) NOT NULL DEFAULT '',
                            checkpoint_id     VARCHAR(64) NOT NULL,
                            task_id           VARCHAR(64) NOT NULL,
                            idx               INT NOT NULL,
                            channel           VARCHAR(128) NOT NULL,
                            type              VARCHAR(16),
                            value             MEDIUMBLOB,
                            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
            self.is_setup = True
            logger.info("MySQLSaver 表初始化完成")

    # ── Sync methods (仅跨线程调用，内部委派到 async) ──

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        try:
            if asyncio.get_running_loop() is self.loop:
                raise asyncio.InvalidStateError(
                    "请使用 async 接口：await checkpointer.aget_tuple(...)"
                )
        except RuntimeError:
            pass
        return asyncio.run_coroutine_threadsafe(
            self.aget_tuple(config), self.loop
        ).result()

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        aiter_ = self.alist(config, filter=filter, before=before, limit=limit)
        while True:
            try:
                yield asyncio.run_coroutine_threadsafe(
                    anext(aiter_),  # type: ignore[arg-type]
                    self.loop,
                ).result()
            except StopAsyncIteration:
                break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return asyncio.run_coroutine_threadsafe(
            self.aput(config, checkpoint, metadata, new_versions), self.loop
        ).result()

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return asyncio.run_coroutine_threadsafe(
            self.aput_writes(config, writes, task_id, task_path), self.loop
        ).result()

    def delete_thread(self, thread_id: str) -> None:
        return asyncio.run_coroutine_threadsafe(
            self.adelete_thread(thread_id), self.loop
        ).result()

    # ── Async methods ──

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        await self.setup()
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        thread_id = str(config["configurable"]["thread_id"])

        async with self.lock, self.engine.begin() as conn:
            if checkpoint_id := get_checkpoint_id(config):
                result = await conn.execute(
                    text(
                        "SELECT thread_id, checkpoint_id, parent_checkpoint_id,"
                        "  type, checkpoint, metadata"
                        " FROM langgraph_checkpoints"
                        " WHERE thread_id = :tid AND checkpoint_ns = :ns"
                        "   AND checkpoint_id = :cid"
                    ),
                    {"tid": thread_id, "ns": checkpoint_ns, "cid": checkpoint_id},
                )
            else:
                result = await conn.execute(
                    text(
                        "SELECT thread_id, checkpoint_id, parent_checkpoint_id,"
                        "  type, checkpoint, metadata"
                        " FROM langgraph_checkpoints"
                        " WHERE thread_id = :tid AND checkpoint_ns = :ns"
                        " ORDER BY checkpoint_id DESC LIMIT 1"
                    ),
                    {"tid": thread_id, "ns": checkpoint_ns},
                )

            row = result.fetchone()
            if row is None:
                return None

            (
                thread_id,
                checkpoint_id,
                parent_checkpoint_id,
                type_,
                checkpoint_blob,
                metadata_blob,
            ) = row

            if not get_checkpoint_id(config):
                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                }

            # 读取 pending writes
            wresult = await conn.execute(
                text(
                    "SELECT task_id, channel, type, value"
                    " FROM langgraph_checkpoint_writes"
                    " WHERE thread_id = :tid AND checkpoint_ns = :ns"
                    "   AND checkpoint_id = :cid"
                    " ORDER BY task_id, idx"
                ),
                {"tid": thread_id, "ns": checkpoint_ns, "cid": checkpoint_id},
            )

            return CheckpointTuple(
                config,
                self.serde.loads_typed((type_, checkpoint_blob)),
                (
                    json.loads(metadata_blob.decode("utf-8"))
                    if metadata_blob
                    else {}
                ),
                (
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": parent_checkpoint_id,
                        }
                    }
                    if parent_checkpoint_id
                    else None
                ),
                [
                    (task_id, channel, self.serde.loads_typed((wt, wv)))
                    for task_id, channel, wt, wv in wresult
                ],
            )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        await self.setup()
        where, params = _search_where(config, filter, before)
        query = (
            "SELECT thread_id, checkpoint_ns, checkpoint_id,"
            "  parent_checkpoint_id, type, checkpoint, metadata"
            " FROM langgraph_checkpoints"
            f" {where}"
            " ORDER BY checkpoint_id DESC"
        )
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        async with self.lock, self.engine.begin() as conn:
            result = await conn.execute(text(query), params)
            rows = result.fetchall()

            for row in rows:
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_checkpoint_id,
                    type_,
                    checkpoint_blob,
                    metadata_blob,
                ) = row

                wresult = await conn.execute(
                    text(
                        "SELECT task_id, channel, type, value"
                        " FROM langgraph_checkpoint_writes"
                        " WHERE thread_id = :tid AND checkpoint_ns = :ns"
                        "   AND checkpoint_id = :cid"
                        " ORDER BY task_id, idx"
                    ),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "cid": checkpoint_id,
                    },
                )

                yield CheckpointTuple(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_id,
                        }
                    },
                    self.serde.loads_typed((type_, checkpoint_blob)),
                    (
                        json.loads(metadata_blob.decode("utf-8"))
                        if metadata_blob
                        else {}
                    ),
                    (
                        {
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": checkpoint_ns,
                                "checkpoint_id": parent_checkpoint_id,
                            }
                        }
                        if parent_checkpoint_id
                        else None
                    ),
                    [
                        (task_id, channel, self.serde.loads_typed((wt, wv)))
                        for task_id, channel, wt, wv in wresult
                    ],
                )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        await self.setup()
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        serialized_metadata = json.dumps(
            get_checkpoint_metadata(config, metadata), ensure_ascii=False
        ).encode("utf-8", "ignore")

        async with self.lock, self.engine.begin() as conn:
            await conn.execute(
                text(
                    "REPLACE INTO langgraph_checkpoints"
                    " (thread_id, checkpoint_ns, checkpoint_id,"
                    "  parent_checkpoint_id, type, checkpoint, metadata)"
                    " VALUES (:tid, :ns, :cid, :pid, :type, :cp, :meta)"
                ),
                {
                    "tid": thread_id,
                    "ns": checkpoint_ns,
                    "cid": checkpoint["id"],
                    "pid": config["configurable"].get("checkpoint_id"),
                    "type": type_,
                    "cp": serialized_checkpoint,
                    "meta": serialized_metadata,
                },
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self.setup()
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"]["checkpoint_ns"])
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        # 跟 SqliteSaver 一致：全是特殊 write 才 REPLACE，否则 IGNORE
        use_replace = all(w[0] in WRITES_IDX_MAP for w in writes)
        stmt = (
            "REPLACE" if use_replace else "INSERT IGNORE"
        ) + (
            " INTO langgraph_checkpoint_writes"
            " (thread_id, checkpoint_ns, checkpoint_id,"
            "  task_id, idx, channel, type, value)"
            " VALUES (:tid, :ns, :cid, :task_id, :idx, :channel, :type, :value)"
        )

        async with self.lock, self.engine.begin() as conn:
            for idx, (channel, value) in enumerate(writes):
                wtype, wvalue = self.serde.dumps_typed(value)
                await conn.execute(
                    text(stmt),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "cid": checkpoint_id,
                        "task_id": task_id,
                        "idx": WRITES_IDX_MAP.get(channel, idx),
                        "channel": channel,
                        "type": wtype,
                        "value": wvalue,
                    },
                )

    async def adelete_thread(self, thread_id: str) -> None:
        async with self.lock, self.engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM langgraph_checkpoint_writes"
                    " WHERE thread_id = :tid"
                ),
                {"tid": str(thread_id)},
            )
            await conn.execute(
                text(
                    "DELETE FROM langgraph_checkpoints WHERE thread_id = :tid"
                ),
                {"tid": str(thread_id)},
            )

    def get_next_version(self, current: str | None, channel: None) -> str:
        """生成单调递增的版本号（照搬 SqliteSaver 实现）。"""
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(current.split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"
