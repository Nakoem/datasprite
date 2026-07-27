"""
审计 & 回放 API 路由

提供 SQL 审计日志查询和 checkpoint 回放面板所需的数据接口。
所有数据均来自已有的 LangGraph checkpointer，只读不写。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.dependencies import get_audit_service
from app.core.log import logger
from app.services.audit_service import AuditService

audit_router = APIRouter()


@audit_router.get("/api/conversations/{conversation_id}/audit")
async def get_audit_trail(
    conversation_id: str,
    audit_service: AuditService = Depends(get_audit_service),
):
    """获取会话的 SQL 审计日志"""
    logger.info("审计日志查询 | conversation_id={}", conversation_id)
    return await audit_service.get_audit_trail(conversation_id)


@audit_router.get("/api/conversations/{conversation_id}/checkpoints")
async def list_checkpoints(
    conversation_id: str,
    audit_service: AuditService = Depends(get_audit_service),
):
    """获取会话的所有 checkpoint 摘要，用于回放时间线"""
    logger.info("检查点列表查询 | conversation_id={}", conversation_id)
    checkpoints = await audit_service.list_checkpoints(conversation_id)
    return {
        "conversation_id": conversation_id,
        "checkpoints": checkpoints,
        "total_count": len(checkpoints),
    }


@audit_router.get(
    "/api/conversations/{conversation_id}/checkpoints/{checkpoint_id}"
)
async def get_checkpoint(
    conversation_id: str,
    checkpoint_id: str,
    audit_service: AuditService = Depends(get_audit_service),
):
    """获取单个 checkpoint 的完整 state 快照"""
    logger.info(
        "检查点详情查询 | conversation_id={} checkpoint_id={}",
        conversation_id,
        checkpoint_id,
    )
    detail = await audit_service.get_checkpoint_detail(
        conversation_id, checkpoint_id
    )
    if detail is None:
        logger.warning(
            "检查点不存在 | conversation_id={} checkpoint_id={}",
            conversation_id,
            checkpoint_id,
        )
        return JSONResponse(
            status_code=404, content={"detail": "检查点不存在"}
        )
    return detail


@audit_router.get(
    "/api/conversations/{conversation_id}/checkpoints/{checkpoint_id}/diff"
)
async def diff_checkpoints(
    conversation_id: str,
    checkpoint_id: str,
    base: str = Query(..., description="基准 checkpoint ID"),
    audit_service: AuditService = Depends(get_audit_service),
):
    """对比两个 checkpoint 的状态差异"""
    logger.info(
        "检查点 diff | conversation_id={} base={} target={}",
        conversation_id,
        base,
        checkpoint_id,
    )
    try:
        return await audit_service.diff_checkpoints(
            conversation_id, base, checkpoint_id
        )
    except ValueError:
        logger.warning(
            "Diff 检查点不存在 | conversation_id={} base={} target={}",
            conversation_id,
            base,
            checkpoint_id,
        )
        return JSONResponse(
            status_code=404, content={"detail": "检查点不存在"}
        )
