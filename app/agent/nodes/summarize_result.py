"""
结果解读节点

在 SQL 执行完成后，调用 LLM 对查询结果生成一句话的业务摘要，
同时把本次查询涉及的业务指标口径说明一并返回给前端。
如果 LLM 调用失败，则降级跳过摘要，不阻塞查询结果展示。
"""

import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

# 截断参数：控制给 LLM 的结果数据量，避免 token 浪费
MAX_ROWS = 20
MAX_COLS = 15
MAX_STR_LEN = 100


def _truncate_value(value, max_len: int = MAX_STR_LEN):
    """截断过长的字符串或数值，保持可读性"""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "…"
    if isinstance(value, float):
        return round(value, 2)
    # Decimal / datetime 等非 JSON 类型 → 转字符串后截断
    if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
        s = str(value)
        return s[:max_len] + "…" if len(s) > max_len else s
    return value


def _build_prompt_data(result: list[dict]) -> tuple[str, int]:
    """将结果列表截断并序列化为 JSON 字符串"""
    total_rows = len(result)
    truncated = result[:MAX_ROWS]

    # 行截断 + 列截断 + 值截断
    safe = []
    for row in truncated:
        trimmed = {}
        for i, (k, v) in enumerate(row.items()):
            if i >= MAX_COLS:
                break
            trimmed[str(k)] = _truncate_value(v)
        safe.append(trimmed)

    data_str = json.dumps(safe, ensure_ascii=False, indent=2, default=str)
    if total_rows > MAX_ROWS:
        data_str += f"\n（……以上仅展示前 {MAX_ROWS} 行，共 {total_rows} 行）"
    return data_str, total_rows


def _build_metric_info(metric_infos: list[MetricInfoState]) -> tuple[str, list[dict]]:
    """构造给 prompt 的口径说明文本 + 前端展示用的指标列表"""
    if not metric_infos:
        return "（本次查询未关联特定业务指标）", []

    lines = []
    metrics = []
    for m in metric_infos:
        name = m.get("name", "")
        desc = m.get("description", "")
        if name:
            lines.append(f"- {name}：{desc or '暂无描述'}")
            metrics.append({"name": name, "description": desc or ""})
    return "\n".join(lines), metrics


def _build_table_sources(table_infos: list[TableInfoState]) -> list[dict]:
    """从过滤后的候选表提取数据来源引用，供前端展示用"""
    if not table_infos:
        return []

    tables = []
    for t in table_infos:
        columns = []
        for col in t.get("columns", []):
            columns.append({
                "name": col.get("name", ""),
                "type": col.get("type", ""),
                "description": col.get("description", ""),
                "alias": col.get("alias", []),
            })
        tables.append({
            "name": t.get("name", ""),
            "role": t.get("role", ""),
            "description": t.get("description", ""),
            "columns": columns,
        })
    return tables


async def summarize_result(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """对查询结果生成 AI 摘要 + 口径说明"""

    writer = runtime.stream_writer
    step = "生成结果解读"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    result = state.get("result", [])
    metric_infos: list[MetricInfoState] = state.get("metric_infos", [])
    table_infos: list[TableInfoState] = state.get("table_infos", [])

    # 准备 LLM 入参
    result_data, total_rows = _build_prompt_data(result)
    metric_descriptions, metrics = _build_metric_info(metric_infos)
    table_sources = _build_table_sources(table_infos)

    try:
        prompt = PromptTemplate(
            template=load_prompt("summarize_result"),
            input_variables=["query", "result_data", "total_rows", "metric_descriptions"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        llm_result: dict = await chain.ainvoke(
            {
                "query": query,
                "result_data": result_data,
                "total_rows": total_rows,
                "metric_descriptions": metric_descriptions,
            }
        )
        summary_text = llm_result.get("summary", "")

        logger.info(f"结果摘要：{summary_text}")
        writer({
            "type": "summary",
            "summary": summary_text,
            "metrics": metrics,
            "tables": table_sources,
        })
        writer({"type": "progress", "step": step, "status": "success"})

    except Exception as e:
        # LLM 故障降级：不阻塞查询结果，只跳过摘要
        logger.warning(f"结果摘要生成失败，降级跳过：{e}")
        writer({
            "type": "summary",
            "summary": None,
            "metrics": metrics,
            "tables": table_sources,
        })
        writer({"type": "progress", "step": step, "status": "success"})

    return {}
