"""
FastAPI 应用入口

负责创建后端应用实例，注册应用生命周期函数，并把各业务模块中的 router
挂载到同一个 app 上。HTTP 请求会先进入这里创建的 app，再按路由分发到
具体的接口处理函数。
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.lifespan import lifespan
from app.api.routers.conversation_router import conversation_router
from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var

# lifespan 交给 FastAPI 管理，用于在服务启动和关闭时统一初始化与释放外部客户端
app = FastAPI(
    title="DataSprite 问数精灵",
    lifespan=lifespan,
)

# 把查询路由注册进应用；没有挂载时，/docs 和真实 HTTP 请求都访问不到该接口
app.include_router(query_router)
app.include_router(conversation_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    # 请求被处理之前
    request_id = uuid.uuid4()
    request_id_ctx_var.set(request_id)
    response = await call_next(request)
    # 请求被处理之后
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底所有未捕获异常，统一返回 JSON 错误而非裸 500"""
    request_id = request_id_ctx_var.get(None)
    logger.opt(exception=True).error(
        "未处理异常 | request_id={} path={}", request_id, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后重试",
            "request_id": str(request_id) if request_id else None,
        },
    )
