"""
会话业务服务

封装会话与消息的业务逻辑，包括历史格式化、标题生成等。
"""

from app.entities.conversation import Conversation, Message
from app.repositories.mysql.meta.conversation_repository import ConversationRepository


def format_history_text(messages: list[tuple[str, str]]) -> str:
    """把 (role, content) 消息列表格式化成 LLM prompt 历史文本。

    用户/助手 前缀 + 助手内容截断 200 字符。真实链路（get_history_for_llm）
    与评测多轮样本（run_evaluation._format_context）共用，保证评测看到的
    上下文与真实链路格式完全一致，多轮指代才能被正确解析。
    """
    lines: list[str] = []
    for role, content in messages:
        role_label = "用户" if role == "user" else "助手"
        if role == "assistant" and len(content) > 200:
            content = content[:200] + "…"
        lines.append(f"{role_label}：{content}")
    return "\n".join(lines)


class ConversationService:
    """会话管理的业务编排层"""

    def __init__(self, conversation_repository: ConversationRepository):
        self.repo = conversation_repository

    # ── 会话管理 ──

    async def ensure_conversation(self, conversation_id: str, first_query: str) -> None:
        """如果会话不存在则创建，存在则更新标题（首条 query 才设标题）"""
        existing = await self.repo.get_conversation(conversation_id)
        if existing is None:
            title = first_query[:30] + ("…" if len(first_query) > 30 else "")
            await self.repo.create_conversation(conversation_id, title)

    async def list_conversations(self) -> list[Conversation]:
        """获取所有会话列表"""
        return await self.repo.list_conversations()

    async def get_conversation_detail(
        self, conversation_id: str
    ) -> tuple[Conversation | None, list[Message]]:
        """获取会话详情（元数据 + 全部消息）"""
        conv = await self.repo.get_conversation(conversation_id)
        if conv is None:
            return None, []
        messages = await self.repo.get_messages(conversation_id)
        return conv, messages

    async def delete_conversation(self, conversation_id: str) -> None:
        """删除会话及其所有消息"""
        await self.repo.delete_conversation(conversation_id)

    # ── 消息管理 ──

    async def save_message(self, message: Message) -> None:
        """保存一条消息"""
        await self.repo.add_message(message)

    async def get_history_for_llm(self, conversation_id: str) -> str:
        """将最近对话格式化为 LLM prompt 中可用的文本"""
        messages = await self.repo.get_recent_messages(conversation_id, limit=10)
        if not messages:
            return ""
        return format_history_text([(m.role, m.content) for m in messages])
