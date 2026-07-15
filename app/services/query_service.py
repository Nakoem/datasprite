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
from app.agent.graph import graph
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

    async def query(self, query: str, conversation_id: str | None = None):
        """执行一次问数工作流，并逐段产出 SSE 消息"""

        # 如果没有会话 ID，生成新 UUID 并创建会话
        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        # 确保会话存在（首次创建或延续已有会话）
        await self.conversation_service.ensure_conversation(conversation_id, query)

        # 加载历史消息用于多轮对话上下文
        conversation_history = await self.conversation_service.get_history_for_llm(
            conversation_id
        )

        # 保存用户消息
        await self.conversation_service.save_message(
            Message(conversation_id=conversation_id, role="user", content=query)
        )

        # State 只放会被图节点读写和合并的业务数据，外部工具对象不塞进 State
        state = DataAgentState(
            query=query,
            correct_retry_count=0,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
        )
        # Context 保存本次图执行需要复用的外部依赖，节点通过 runtime.context 读取
        context = DataAgentContext(
            column_qdrant_repository=self.column_qdrant_repository,
            embedding_client=self.embedding_client,
            metric_qdrant_repository=self.metric_qdrant_repository,
            value_es_repository=self.value_es_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
        )

        # 收集图执行过程中的关键信息用于持久化
        collected_sql: str | None = None
        collected_result: dict | list | None = None
        assistant_content = ""

        try:
            # stream_mode="custom" 对应节点内部 writer(...) 写出的进度消息
            async for chunk in graph.astream(
                input=state, context=context, stream_mode="custom"
            ):
                # 收集 SQL 和结果用于持久化
                if isinstance(chunk, dict):
                    if chunk.get("type") == "progress":
                        step = chunk.get("step", "")
                        status = chunk.get("status", "")
                        if status == "running":
                            assistant_content = f"正在执行：{step}"
                    elif chunk.get("type") == "result":
                        collected_result = chunk.get("data")
                        collected_sql = chunk.get("sql")
                        assistant_content = "查询完成"
                    elif chunk.get("type") == "clarification":
                        assistant_content = "需要确认一下～"

                # SSE 要求每条消息以 data: 开头，并以两个换行符结束
                # ensure_ascii=False 保留中文进度文案，default=str 兜底处理日期等非 JSON 类型
                yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"

            # 图执行完成后，从最终 state 中获取 SQL（如果有的话）
            # 注意：graph.astream 不直接返回最终 state，但我们可以从 chunk 中推断

        except Exception as e:
            assistant_content = f"查询失败：{str(e)}"
            # 流式接口已经开始返回后不能再改 HTTP 状态码，因此把异常也包装成一条 SSE 消息
            error = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"

        finally:
            # 持久化助手消息（包含 SQL 和结果）
            await self.conversation_service.save_message(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content or "流程已结束",
                    sql=collected_sql,
                    result=collected_result,
                )
            )
