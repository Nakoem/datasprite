"""
FastAPI 依赖组装

集中声明 API 层需要的依赖函数，把 Session、Repository、Client 和 Service
按职责组装起来。路由层只通过 Depends 声明自己需要什么对象，具体创建细节
都收敛在这里，避免 HTTP 处理函数直接感知底层基础设施。
"""

import os
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.checkpointer import MySQLSaver
from app.agent.graph import compile_graph
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.core.security import decode_token
from app.entities.user import User
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.checkpoint_repository import CheckpointRepository
from app.repositories.mysql.meta.conversation_repository import ConversationRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.user_repository import UserRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.query_service import QueryService

# ── /api/ask 外部调用鉴权 ────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_api_key_header)):
    """校验 X-API-Key 请求头，未配置 API_KEY 时跳过校验（开发模式）。"""
    expected = os.getenv("API_KEY")
    if not expected:
        # 未配置 API_KEY → 开发模式，不拦截
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API Key")


async def get_meta_session():
    """创建一次请求内使用的元数据库 Session"""

    # yield 之后的清理逻辑由 async with 负责，FastAPI 会在请求结束后继续执行退出流程
    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session


async def get_meta_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetaMySQLRepository:
    """基于请求级 Session 创建元数据仓储"""

    return MetaMySQLRepository(session)


async def get_embedding_client() -> HuggingFaceEndpointEmbeddings:
    """获取应用启动阶段初始化好的 Embedding 客户端"""

    return embedding_client_manager.client


async def get_dw_session():
    """创建一次请求内使用的数仓 Session"""

    async with dw_mysql_client_manager.session_factory() as dw_session:
        yield dw_session


async def get_dw_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_dw_session)],
) -> DWMySQLRepository:
    """基于请求级 Session 创建数仓仓储"""

    return DWMySQLRepository(session)


async def get_column_qdrant_repository() -> ColumnQdrantRepository:
    """创建字段向量检索仓储"""

    return ColumnQdrantRepository(qdrant_client_manager.client)


async def get_metric_qdrant_repository() -> MetricQdrantRepository:
    """创建指标向量检索仓储"""

    return MetricQdrantRepository(qdrant_client_manager.client)


async def get_value_es_repository() -> ValueESRepository:
    """创建字段取值全文检索仓储"""

    return ValueESRepository(es_client_manager.client)


async def get_conversation_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> ConversationRepository:
    """基于请求级 Session 创建会话仓储"""

    return ConversationRepository(session)


async def get_conversation_service(
    conversation_repository: Annotated[
        ConversationRepository, Depends(get_conversation_repository)
    ],
) -> ConversationService:
    """组装会话业务服务"""

    return ConversationService(conversation_repository)


async def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> UserRepository:
    """基于请求级 Session 创建用户仓储"""

    return UserRepository(session)


async def get_auth_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    """组装登录鉴权业务服务"""

    return AuthService(user_repository)


# ── JWT 登录鉴权依赖 ───────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer_scheme)
    ],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """解析 Authorization: Bearer <token>，返回当前登录用户。

    用于保护需要登录态的 API。token 缺失/无效/过期一律 401。
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    user = await user_repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


async def get_checkpoint_repository(
    checkpointer: Annotated[MySQLSaver, Depends(get_checkpointer)],
) -> CheckpointRepository:
    """基于 MySQLSaver 单例创建 checkpoint 只读仓储"""
    return CheckpointRepository(checkpointer)


async def get_audit_service(
    checkpoint_repo: Annotated[
        CheckpointRepository, Depends(get_checkpoint_repository)
    ],
) -> AuditService:
    """组装审计 + 回放业务服务"""
    return AuditService(checkpoint_repo)


# ── checkpointer 单例（应用级，非请求级）──

_checkpointer: MySQLSaver | None = None


async def get_checkpointer() -> MySQLSaver:
    """获取 MySQLSaver 单例，首次调用时建表。

    复用 meta_mysql_client_manager 的 AsyncEngine，checkpoint 表存在
    meta 库中。setup() 是幂等的，多次调用安全。
    """
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MySQLSaver(meta_mysql_client_manager.engine)
        await _checkpointer.setup()
    return _checkpointer


async def get_compiled_graph(
    checkpointer: Annotated[MySQLSaver, Depends(get_checkpointer)],
):
    """用 checkpointer 编译 LangGraph 工作流（每个节点后自动存档 state）。"""
    return compile_graph(checkpointer=checkpointer)


async def get_query_service(
    meta_mysql_repository: Annotated[
        MetaMySQLRepository, Depends(get_meta_mysql_repository)
    ],
    embedding_client: Annotated[
        HuggingFaceEndpointEmbeddings, Depends(get_embedding_client)
    ],
    dw_mysql_repository: Annotated[DWMySQLRepository, Depends(get_dw_mysql_repository)],
    column_qdrant_repository: Annotated[
        ColumnQdrantRepository, Depends(get_column_qdrant_repository)
    ],
    metric_qdrant_repository: Annotated[
        MetricQdrantRepository, Depends(get_metric_qdrant_repository)
    ],
    value_es_repository: Annotated[ValueESRepository, Depends(get_value_es_repository)],
    conversation_service: Annotated[
        ConversationService, Depends(get_conversation_service)
    ],
    compiled_graph: Annotated[CompiledStateGraph, Depends(get_compiled_graph)],
) -> QueryService:
    """组装一次查询所需的业务服务"""

    # QueryService 只接收已经创建好的依赖对象，本身不关心这些对象来自 MySQL、Qdrant 还是 ES
    return QueryService(
        meta_mysql_repository=meta_mysql_repository,
        embedding_client=embedding_client,
        dw_mysql_repository=dw_mysql_repository,
        column_qdrant_repository=column_qdrant_repository,
        metric_qdrant_repository=metric_qdrant_repository,
        value_es_repository=value_es_repository,
        conversation_service=conversation_service,
        compiled_graph=compiled_graph,
    )
