"""
FastAPI 应用入口

负责创建后端应用实例，注册应用生命周期函数，并把各业务模块中的 router
挂载到同一个 app 上。HTTP 请求会先进入这里创建的 app，再按路由分发到
具体的接口处理函数。
"""

import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.dependencies import get_current_user
from app.api.lifespan import lifespan
from app.api.routers.audit_router import audit_router
from app.api.routers.auth_router import auth_router
from app.api.routers.conversation_router import conversation_router
from app.api.routers.query_router import query_router
from app.core.context import request_id_ctx_var
from app.core.log import logger
from app.core.rate_limiter import rate_limit_middleware

# ── OpenTelemetry 链路追踪 ──────────────────────────────────────────
resource = Resource.create({SERVICE_NAME: "datasprite"})
provider = TracerProvider(resource=resource)

# collector（localhost:4318）没启动时，后台导出线程会持续连接失败刷日志。
# try/except 保证 exporter 初始化任何异常都不会拖垮应用 import；
# timeout=3 让 collector 挂死时后台线程能快速放弃，而不是无限等待。
try:
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint="http://localhost:4318/v1/traces",
                timeout=3,
            )
        )
    )
except Exception as e:
    logger.warning(f"OTLP exporter 初始化失败，trace 降级为仅本地采样 | {e}")

# set_tracer_provider 必须无条件执行，否则 FastAPIInstrumentor 埋点会报错
trace.set_tracer_provider(provider)

# ── FastAPI 应用 ────────────────────────────────────────────────────
app = FastAPI(
    title="DataSprite 问数精灵",
    lifespan=lifespan,
)

# 把查询路由注册进应用；没有挂载时，/docs 和真实 HTTP 请求都访问不到该接口
# 登录接口不鉴权；会话/审计接口需要 JWT 登录态（/api/query 在 query_router 内单独加依赖）
app.include_router(auth_router)
app.include_router(query_router)
app.include_router(conversation_router, dependencies=[Depends(get_current_user)])
app.include_router(audit_router, dependencies=[Depends(get_current_user)])

# ── API 限流（双层令牌桶，实现见 app/core/rate_limiter.py）──────────
# 最先注册 = 位于中间件栈最内层（后面注册的 add_request_id 等在其外层）：
# 429 会被外层的 Prometheus/OTel 统计到，攻击流量在监控里可见；
# 同时仍在路由处理前拦截，LLM 链路不受冲击
app.middleware("http")(rate_limit_middleware)

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
    # 优先沿用上游透传的 request_id（feishu-bridge 带 X-Request-Id 头），
    # 实现 feishu-bridge → DataSprite 全链路贯通；上游没传才自建 UUID
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
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
