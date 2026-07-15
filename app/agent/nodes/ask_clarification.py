"""
澄清追问节点

当意图分类发现用户查询模糊时，通过 SSE 向用户发出澄清追问选项，
并终止当前图执行（不进入 SQL 生成链路）。

前端收到 clarification 事件后渲染追问按钮，用户点击后以新 query + 同一 conversation_id 重新走整条链路。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def ask_clarification(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """发出澄清追问事件并终止图执行"""

    writer = runtime.stream_writer
    step = "澄清追问"
    writer({"type": "progress", "step": step, "status": "running"})

    questions = state.get("clarification_questions", [])
    if not questions:
        questions = ["能再具体描述一下你的需求吗？"]

    logger.info(f"发出澄清追问：{questions}")
    writer({
        "type": "clarification",
        "questions": questions,
    })

    writer({"type": "progress", "step": step, "status": "success"})

    # 不返回任何 state 更新 — 图在此终止，不需要后续节点
    return {}
