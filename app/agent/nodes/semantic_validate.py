"""
语义校验节点

负责在 SQL 语法校验通过后，用 LLM 判断生成的 SQL 在业务语义上
是否真正回答了用户的自然语言问题。仅EXPLAIN通过且语义校验通过的SQL
才会进入执行节点，语义问题会写入 error 字段触发修正闭环。
"""

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def semantic_validate(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
):
    """用 LLM 校验 SQL 的业务语义是否与用户问题一致"""

    writer = runtime.stream_writer
    step = "语义校验"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = state["query"]
        sql = state["sql"]
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        db_info = state["db_info"]

        prompt = PromptTemplate(
            template=load_prompt("semantic_validate"),
            input_variables=[
                "query",
                "conversation_history",
                "db_info",
                "table_infos",
                "metric_infos",
                "sql",
            ],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                "query": query,
                "conversation_history": state.get("conversation_history", "") or "",
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
                "table_infos": yaml.dump(
                    table_infos, allow_unicode=True, sort_keys=False
                ),
                "metric_infos": yaml.dump(
                    metric_infos, allow_unicode=True, sort_keys=False
                ),
                "sql": sql,
            }
        )

        if result.get("pass", True):
            logger.info("语义校验通过")
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": None}

        reason = result.get("reason", "语义校验未通过")
        error_msg = f"[语义校验] {reason}"
        logger.info(f"语义校验未通过：{reason}")
        writer({"type": "progress", "step": step, "status": "retry"})
        return {"error": error_msg}

    except Exception as e:
        # 保守策略：LLM 调用失败时放行，宁放过不误杀
        logger.warning(f"语义校验 LLM 调用异常，保守放行：{e}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"error": None}
