"""
会话历史接口路由

提供会话列表、详情和删除功能，供前端侧边栏展示和加载历史对话。
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.api.dependencies import get_conversation_service
from app.services.conversation_service import ConversationService

conversation_router = APIRouter()


def _ts(d: dt.datetime | None) -> str | None:
    """将 MySQL 的 UTC naive datetime 转为带时区标记的 ISO 字符串"""
    if d is None:
        return None
    return d.replace(tzinfo=dt.timezone.utc).isoformat()


@conversation_router.get("/api/conversations")
async def list_conversations(
    conversation_service: Annotated[
        ConversationService, Depends(get_conversation_service)
    ],
):
    """获取所有会话列表（按更新时间倒序）"""
    conversations = await conversation_service.list_conversations()
    return [
        {
            "id": conv.id,
            "title": conv.title,
            "createdAt": _ts(conv.created_at),
            "updatedAt": _ts(conv.updated_at),
        }
        for conv in conversations
    ]


@conversation_router.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    conversation_service: Annotated[
        ConversationService, Depends(get_conversation_service)
    ],
):
    """获取单个会话详情（含全部消息）"""
    conv, messages = await conversation_service.get_conversation_detail(
        conversation_id
    )
    if conv is None:
        return JSONResponse(
            status_code=404, content={"detail": "会话不存在"}
        )

    return {
        "id": conv.id,
        "title": conv.title,
        "createdAt": _ts(conv.created_at),
        "updatedAt": _ts(conv.updated_at),
        "messages": [
            {
                "id": msg.id,
                "conversationId": msg.conversation_id,
                "role": msg.role,
                "content": msg.content,
                "sql": msg.sql,
                "result": msg.result,
                "summary": msg.summary,
                "metricDefinitions": msg.metric_definitions,
                "createdAt": _ts(msg.created_at),
            }
            for msg in messages
        ],
    }


@conversation_router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    conversation_service: Annotated[
        ConversationService, Depends(get_conversation_service)
    ],
):
    """删除会话及其所有消息"""
    await conversation_service.delete_conversation(conversation_id)
    return {"ok": True}
