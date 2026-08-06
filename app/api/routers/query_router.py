"""
问数查询接口路由

负责定义前端访问的 `/api/query` 接口，把 HTTP 请求交给 QueryService，
并把问数智能体执行过程以 SSE 形式持续返回给客户端。
路由层只处理请求体、依赖声明和响应类型，不直接创建 Repository 或执行图节点。

同时提供 `/api/ask` 同步接口，供 Dify / 飞书 / 钉钉等外部系统通过 JSON 调用。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.dependencies import get_current_user, get_query_service, verify_api_key
from app.api.schemas.ask_schema import AskRequest, AskResponse
from app.api.schemas.query_schema import QuerySchema
from app.core.log import logger
from app.services.query_service import QueryService

# 当前模块只维护查询相关接口，避免后续所有 API 都挤在 main.py 中
query_router = APIRouter()


@query_router.post("/api/query")
async def query_handler(
    # 请求体参数：FastAPI 会把前端 JSON 自动解析成 QuerySchema
    query: QuerySchema,
    # 服务依赖：FastAPI 会调用 get_query_service，递归组装它所需的仓储和客户端
    query_service: Annotated[QueryService, Depends(get_query_service)],
    # 登录鉴权：必须携带有效 JWT 才能问数（/api/ask 走 X-API-Key，不受此依赖影响）
    _: None = Depends(get_current_user),
):
    """接收用户自然语言问题，并流式返回 LangGraph 工作流输出"""

    return StreamingResponse(
        # query.query 是用户问题字符串；QueryService.query 返回异步生成器供响应逐段消费
        # conversation_id 用于多轮对话上下文和会话持久化
        query_service.query(query.query, conversation_id=query.conversation_id),
        media_type="text/event-stream",
    )


@query_router.post("/api/ask")
async def ask_handler(
    body: AskRequest,
    query_service: Annotated[QueryService, Depends(get_query_service)],
    _: None = Depends(verify_api_key),
):
    """同步问数接口：接收自然语言 → 跑完整管线 → 返回 JSON

    外部系统通过 X-API-Key 请求头鉴权后，一次调用拿到 SQL + 数据 + AI 摘要。
    """
    logger.info(
        "外部 API 调用 /api/ask | query={} cid={}",
        body.query[:200],
        body.conversation_id,
    )
    result = await query_service.query_sync(
        body.query, conversation_id=body.conversation_id
    )
    return AskResponse(
        sql=result.get("sql"),
        data=result.get("data"),
        summary=result.get("summary"),
        metric_definitions=result.get("metric_definitions"),
        column_sources=result.get("column_sources"),
        error=result.get("error"),
        chart_image_base64=result.get("chart_image_base64"),
    )
