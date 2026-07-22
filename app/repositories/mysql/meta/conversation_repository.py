"""
会话与消息仓储

负责 conversations 和 messages 两张表的读写操作。
面向业务实体而非 ORM 模型，转换逻辑内聚在仓储内部。
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.conversation import Conversation, Message
from app.models.conversation import ConversationMySQL, MessageMySQL


def _parse_json(value: str | dict | list | None) -> dict | list | None:
    """将 raw SQL 返回的 JSON 字符串解析为 Python 对象"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError, TypeError:
            return None
    return value


def _row_to_message(row) -> Message:
    """将 raw SQL 行映射为 Message 实体，处理 JSON 列的字符串问题"""
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        sql=row["sql"],
        result=_parse_json(row["result"]),
        summary=row.get("summary"),
        metric_definitions=_parse_json(row.get("metric_definitions")),
        column_sources=_parse_json(row.get("column_sources")),
        created_at=row["created_at"],
    )


class ConversationRepository:
    """会话与消息的数据访问层"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 会话 ──

    async def create_conversation(self, conversation_id: str, title: str) -> None:
        """创建新会话记录"""
        model = ConversationMySQL(id=conversation_id, title=title)
        self.session.add(model)
        await self.session.commit()

    async def update_title(self, conversation_id: str, title: str) -> None:
        """更新会话标题"""
        conv = await self.session.get(ConversationMySQL, conversation_id)
        if conv:
            conv.title = title
            await self.session.commit()

    async def list_conversations(self) -> list[Conversation]:
        """列出所有会话，按更新时间倒序"""
        sql = """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            ORDER BY c.updated_at DESC
        """
        result = await self.session.execute(text(sql))
        rows = result.mappings().fetchall()
        return [
            Conversation(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """获取单条会话元数据"""
        model = await self.session.get(ConversationMySQL, conversation_id)
        if model is None:
            return None
        return Conversation(
            id=model.id,
            title=model.title,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def delete_conversation(self, conversation_id: str) -> None:
        """删除会话（级联删除关联消息）"""
        model = await self.session.get(ConversationMySQL, conversation_id)
        if model:
            await self.session.delete(model)
            await self.session.commit()

    # ── 消息 ──

    async def add_message(self, message: Message) -> None:
        """插入一条消息"""
        model = MessageMySQL(
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            sql=message.sql,
            result=message.result,
            summary=message.summary,
            metric_definitions=message.metric_definitions,
            column_sources=message.column_sources,
        )
        self.session.add(model)
        await self.session.commit()

    async def get_messages(
        self, conversation_id: str, limit: int = 100
    ) -> list[Message]:
        """获取会话的消息列表（按时间正序）"""
        sql = """
            SELECT id, conversation_id, role, content, `sql`, `result`, summary, metric_definitions, column_sources, created_at
            FROM messages
            WHERE conversation_id = :cid
            ORDER BY created_at ASC
            LIMIT :limit
        """
        result = await self.session.execute(
            text(sql), {"cid": conversation_id, "limit": limit}
        )
        rows = result.mappings().fetchall()
        return [_row_to_message(row) for row in rows]

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 10
    ) -> list[Message]:
        """获取最近 N 条消息（用于构造 LLM 上下文）"""
        return await self.get_messages(conversation_id, limit=limit)
