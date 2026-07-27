"""
问数查询服务

负责把 API 层传入的自然语言问题转换成一次 LangGraph 工作流执行：
创建初始 State、组装 Runtime Context、消费 graph.astream 的流式输出，
并统一包装成 SSE 文本返回给路由层。

新增多轮对话支持：接收 conversation_id、加载历史、图执行后持久化消息。
"""

import json
import uuid

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.agent.graph import graph  # 无 checkpointer 的默认图（fallback）
from app.agent.state import DataAgentState
from app.entities.conversation import Message
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.conversation_service import ConversationService


class QueryService:
    """封装一次问数查询所需的业务编排逻辑"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        value_es_repository: ValueESRepository,
        conversation_service: ConversationService,
        compiled_graph=None,
    ):
        # MySQL 仓储分别负责元数据补全和真实数仓环境信息读取
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository

        # 召回链路依赖的向量检索、Embedding 和全文检索能力由依赖层注入
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.value_es_repository = value_es_repository

        # 会话持久化
        self.conversation_service = conversation_service

        # LangGraph 编译图（可选带 checkpointer）
        self.compiled_graph = compiled_graph or graph

    async def _run_graph(self, query: str, conversation_id: str | None = None):
        """内部共享方法：执行 LangGraph 管线，逐段 yield 原始 dict chunk。

        query() 将其包装为 SSE，query_sync() 直接收集为 dict。
        避免 SSE 序列化/反序列化来回折腾。
        """
        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        await self.conversation_service.ensure_conversation(conversation_id, query)

        conversation_history = await self.conversation_service.get_history_for_llm(
            conversation_id
        )

        await self.conversation_service.save_message(
            Message(conversation_id=conversation_id, role="user", content=query)
        )

        state = DataAgentState(
            query=query,
            correct_retry_count=0,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
        )
        context = DataAgentContext(
            column_qdrant_repository=self.column_qdrant_repository,
            embedding_client=self.embedding_client,
            metric_qdrant_repository=self.metric_qdrant_repository,
            value_es_repository=self.value_es_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
        )

        collected_sql: str | None = None
        collected_result: dict | list | None = None
        collected_summary: str | None = None
        collected_metric_definitions: list | None = None
        collected_column_sources: list | None = None
        assistant_content = ""

        try:
            astream_config = {"configurable": {"thread_id": conversation_id}}
            async for chunk in self.compiled_graph.astream(
                input=state,
                context=context,
                stream_mode="custom",
                config=astream_config,
            ):
                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "progress":
                        step = chunk.get("step", "")
                        status = chunk.get("status", "")
                        if status == "running":
                            assistant_content = f"正在执行：{step}"
                        elif status == "retry":
                            assistant_content = f"正在{step}（重试中）"
                    elif chunk_type == "result":
                        collected_result = chunk.get("data")
                        collected_sql = chunk.get("sql")
                        assistant_content = "查询完成"
                    elif chunk_type == "summary":
                        collected_summary = chunk.get("summary")
                        collected_metric_definitions = chunk.get("metrics")
                        collected_column_sources = chunk.get("tables")
                        assistant_content = "查询完成"
                    elif chunk_type == "clarification":
                        assistant_content = "需要确认一下～"

                # yield 原始 dict 给调用方（query → SSE 包装 / query_sync → 直接收集）
                yield chunk

        except Exception as e:
            assistant_content = f"查询失败：{str(e)}"
            error = {"type": "error", "message": str(e)}
            yield error

        finally:
            await self.conversation_service.save_message(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content or "流程已结束",
                    sql=collected_sql,
                    result=collected_result,
                    summary=collected_summary,
                    metric_definitions=collected_metric_definitions,
                    column_sources=collected_column_sources,
                )
            )

    async def query_sync(self, query: str) -> dict:
        """同步版问数：直接消费 _run_graph 的 dict chunk，一次性返回。

        供 /api/ask 等外部集成接口使用，返回 SQL + 数据 + AI 摘要。
        """
        result = {
            "sql": None,
            "data": None,
            "summary": None,
            "metric_definitions": None,
            "column_sources": None,
            "error": None,
        }

        try:
            async for chunk in self._run_graph(query):
                if not isinstance(chunk, dict):
                    continue

                chunk_type = chunk.get("type", "")
                if chunk_type == "result":
                    result["sql"] = chunk.get("sql")
                    result["data"] = chunk.get("data")
                elif chunk_type == "summary":
                    result["summary"] = chunk.get("summary")
                    result["metric_definitions"] = chunk.get("metrics")
                    result["column_sources"] = chunk.get("tables")
                elif chunk_type == "error":
                    result["error"] = chunk.get("message")
        except Exception as e:
            result["error"] = str(e)

        return result

    async def query(self, query: str, conversation_id: str | None = None):
        """执行一次问数工作流，并逐段产出 SSE 消息"""

        async for chunk in self._run_graph(query, conversation_id):
            yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
