"""
意图分类节点

负责在问数工作流入口处分析用户查询的意图：
- new：独立新问题 → 继续走 SQL 链路
- follow_up：追问 → 结合历史补全问题后继续
- ambiguous：模糊 → 发出澄清追问事件并终止

这是多轮对话和意图澄清的核心入口节点。
"""

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def classify_intent(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """分析用户查询意图，决定后续路由"""

    writer = runtime.stream_writer
    step = "分析意图"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    conversation_history = state.get("conversation_history", "") or ""

    try:
        prompt = PromptTemplate(
            template=load_prompt("classify_intent"),
            input_variables=["conversation_history", "query"],
        )
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {"conversation_history": conversation_history, "query": query}
        )
        logger.info(f"意图分类结果：{result}")

        # 解析 LLM 返回的 JSON
        intent_data = json.loads(result.strip())
        intent = intent_data.get("intent", "new")

        return_data: dict = {"intent": intent}

        if intent == "ambiguous":
            clarification_questions = intent_data.get("clarification_questions", [])
            return_data["clarification_questions"] = clarification_questions
            logger.info(f"意图模糊，需要澄清：{clarification_questions}")
        elif intent == "follow_up":
            resolved_query = intent_data.get("resolved_query", query)
            return_data["resolved_query"] = resolved_query
            return_data["query"] = resolved_query  # 用补全后的问题覆盖原始 query
            logger.info(f"追问解析：'{query}' → '{resolved_query}'")

        writer({"type": "progress", "step": step, "status": "success"})
        return return_data

    except json.JSONDecodeError as e:
        logger.warning(f"意图分类 JSON 解析失败，按新问题处理：{e}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"intent": "new"}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
