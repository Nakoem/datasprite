"""
会话与消息 ORM 模型

定义元数据库中 conversations 和 messages 两张新表对应的 ORM 模型，
用于持久化多轮对话历史和查询记录。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import quoted_name
from sqlalchemy.types import JSON

from app.models.base import Base


class ConversationMySQL(Base):
    """会话元数据表 — 一次对话会话对应一条记录"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="会话 UUID（前端生成）"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="会话标题（首条 query 截断）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="最后更新时间"
    )


class MessageMySQL(Base):
    """消息记录表 — 会话中的每一条用户/助手消息"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="消息自增 ID"
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属会话 ID",
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="消息角色：user / assistant"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息文本内容"
    )
    sql: Mapped[str | None] = mapped_column(
        Text,
        name=quoted_name("sql", quote=True),
        nullable=True,
        comment="助手消息对应的 SQL（仅 assistant）",
    )
    result: Mapped[dict | list | None] = mapped_column(
        JSON,
        name=quoted_name("result", quote=True),
        nullable=True,
        comment="助手消息的查询结果（仅 assistant）",
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="AI 生成的结果解读摘要（仅 assistant）",
    )
    metric_definitions: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="本次查询涉及的指标口径说明（仅 assistant）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="消息创建时间"
    )
