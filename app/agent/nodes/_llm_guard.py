"""
LLM 输出格式兜底工具

各节点用 JsonOutputParser 解析模型输出，但模型偶发会返回非预期结构
（如 {"keywords": [...]} 而不是 ["a", "b"]）。这里提供统一的类型校验，
格式异常时降级为空值并告警，避免节点直接崩溃。
"""

from typing import Any

from app.core.log import logger


def ensure_str_list(result: Any, context: str) -> list:
    """确保 LLM 扩展词输出是 list；不是则降级为空 list 并告警。

    context 用于日志区分来源（如"字段扩展词"、"指标扩展词"）。
    降级为空 list 后，调用方只保留原始关键词参与召回。
    """
    if not isinstance(result, list):
        logger.warning(
            f"{context}格式异常，降级为仅用原始关键词 | "
            f"result_type={type(result).__name__} result={str(result)[:200]}"
        )
        return []
    return result
