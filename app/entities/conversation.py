"""
会话与消息领域实体

纯数据对象，不依赖 ORM 框架，用于在各层之间传递会话和消息数据。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Conversation:
    """一次对话会话"""

    id: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Message:
    """会话中的一条消息"""

    id: int | None = None
    conversation_id: str = ""
    role: str = ""  # "user" | "assistant"
    content: str = ""
    sql: str | None = None
    result: dict | list | None = None
    summary: str | None = None
    metric_definitions: list | None = None
    column_sources: list | None = None
    created_at: datetime | None = None
