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
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.lifespan import lifespan
from app.api.routers.conversation_router import conversation_router
from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var

# ── OpenTelemetry 链路追踪 ──────────────────────────────────────────
resource = Resource.create({SERVICE_NAME: "datasprite"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
trace.set_tracer_provider(provider)

# ── FastAPI 应用 ────────────────────────────────────────────────────
app = FastAPI(
    title="DataSprite 问数精灵",
    lifespan=lifespan,
)

# 把查询路由注册进应用；没有挂载时，/docs 和真实 HTTP 请求都访问不到该接口
app.include_router(query_router)
app.include_router(conversation_router)

# ── Prometheus 指标暴露 /metrics ────────────────────────────────────
Instrumentator().instrument(app).expose(app)

# ── OpenTelemetry 自动埋点 ──────────────────────────────────────────
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
async def health():
    """健康检查端点，供负载均衡 / K8s 探活使用"""
    return {"status": "ok"}


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid.uuid4()
    request_id_ctx_var.set(request_id)
    response = await call_next(request)
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
