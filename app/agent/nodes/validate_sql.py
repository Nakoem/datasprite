"""
SQL 校验节点

负责在真正执行查询前，用数据库解析一次生成的 SQL
校验结果不在这里决定流程走向，而是通过 state["error"] 交给 graph.py 的条件边判断
只有 SQL 语法/语义错误才会写入 error 触发修正流程，基础设施错误直接抛出
"""

import re

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

# MySQL 基础设施错误的典型关键词，这类错误不应交给 LLM 修正
_INFRA_ERROR_PATTERNS = [
    r"connection refused",
    r"connection timeout",
    r"too many connections",
    r"access denied",
    r"can't connect",
    r"lost connection",
    r"server has gone away",
    r"connection reset",
    r"no route to host",
    r"unknown mysql server host",
]


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """校验 SQL，并返回 error 字段控制后续条件分支"""

    writer = runtime.stream_writer
    step = "校验SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 读取 generate_sql 或 correct_sql 写入状态的候选 SQL
        sql = state["sql"]

        # SQL 可用性必须交给真实数仓判断，这里从运行时上下文取 DW Repository
        dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

        try:
            # validate 内部使用 explain <sql>，只关心数据库能否成功解析这条 SQL
            await dw_mysql_repository.validate(sql)
            writer({"type": "progress", "step": step, "status": "success"})
            logger.info("SQL语法正确")
            return {"error": None}
        except Exception as e:
            error_str = str(e).lower()
            # 基础设施错误（断连、超时等）不应交给 LLM 修正，直接抛出
            if any(re.search(pattern, error_str) for pattern in _INFRA_ERROR_PATTERNS):
                logger.error(f"校验阶段基础设施错误：{error_str}")
                writer({"type": "progress", "step": step, "status": "error"})
                raise
            # SQL 语法/语义错误写入 state，供条件分支进入 correct_sql
            logger.info(f"SQL语法错误：{str(e)}")
            writer({"type": "progress", "step": step, "status": "retry"})
            return {"error": str(e)}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
