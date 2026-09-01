"""
指标信息过滤节点

负责从合并后的候选指标中筛选出当前问题真正需要的指标
过滤后的指标会进入 SQL 生成上下文，帮助模型遵循正确的业务口径
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.nodes._schema_compact import compact_metric_infos
from app.agent.state import DataAgentState, MetricInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """根据用户问题裁剪候选指标上下文"""

    writer = runtime.stream_writer
    step = "过滤指标信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = state["query"]
        metric_infos: list[MetricInfoState] = state["metric_infos"]

        # metric_infos 转成 YAML 后作为候选项交给模型，模型只需要返回被选中的指标名称
        prompt = PromptTemplate(
            template=load_prompt("filter_metric_info"),
            input_variables=["query", "metric_infos"],
        )
        # filter_metric_info prompt 要求模型只输出 JSON 数组
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        compacted_yaml = compact_metric_infos(metric_infos)
        result = await chain.ainvoke(
            {
                "query": query,
                "metric_infos": compacted_yaml,
            }
        )
        # 模型偶发会返回 dict/str 而不是数组（如 {"metrics": [...]}）。
        # 格式异常时降级为"不过滤"：保留全部候选指标原样传给下游，
        # 宁可多给上下文，也别让 SQL 生成阶段没有指标口径可用
        if not isinstance(result, list):
            logger.warning(
                f"指标过滤结果格式异常，保留全部候选指标 | "
                f"result_type={type(result).__name__} result={str(result)[:200]}"
            )
            filtered_metric_infos = list(metric_infos)
        else:
            # 用模型返回的指标名称过滤原始结构，保留描述 依赖字段 别名等完整上下文
            filtered_metric_infos = [
                metric_info
                for metric_info in metric_infos
                if metric_info["name"] in result
            ]

        logger.info("指标信息瘦身（#39）：YAML 输入压缩到 {} 字符", len(compacted_yaml))
        logger.info(
            f"过滤后的指标信息：{[filtered_metric_info['name'] for filtered_metric_info in filtered_metric_infos]}"
        )

        writer({"type": "progress", "step": step, "status": "success"})
        return {"metric_infos": filtered_metric_infos}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
