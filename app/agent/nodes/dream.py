"""
Dream 记忆压缩节点

在多轮对话中，conversation_history 会随轮次增加而膨胀。
当历史文本超过 token 预算时，调用 LLM 将历史压缩为一段简洁摘要，
覆盖 conversation_history 供下游节点（generate_sql / correct_sql）使用。
"""

from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

# 历史文本字符数阈值（中文约 2 char ≈ 1 token，这里设为 ~1500 token）
COMPRESS_CHAR_THRESHOLD = 3000


async def dream(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """检测对话历史长度，超预算时调用 LLM 进行摘要压缩"""

    writer = runtime.stream_writer
    history = state.get("conversation_history", "") or ""

    # 历史短 → 不需要压缩
    if len(history) <= COMPRESS_CHAR_THRESHOLD:
        logger.info(f"对话历史 {len(history)} chars，未触发压缩阈值 {COMPRESS_CHAR_THRESHOLD}")
        return {"compressed_memory": ""}

    step = "压缩对话记忆"
    writer({"type": "progress", "step": step, "status": "running"})
    logger.info(f"对话历史 {len(history)} chars 触发压缩")

    try:
        prompt = PromptTemplate(
            template=load_prompt("dream"),
            input_variables=["conversation_history"],
        )
        chain = prompt | llm
        result = await chain.ainvoke({"conversation_history": history})
        compressed = result.content.strip() if hasattr(result, "content") else str(result).strip()

        logger.info(f"记忆压缩完成：{len(history)} → {len(compressed)} chars")
        writer({"type": "progress", "step": step, "status": "success"})

        return {
            "compressed_memory": compressed,
            "conversation_history": compressed,
        }

    except Exception as e:
        # 压缩失败不阻塞流程，保留原始历史继续
        logger.warning(f"记忆压缩失败，降级保留原始历史：{e}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"compressed_memory": ""}
