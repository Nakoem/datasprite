"""
generate_sql 节点测试

LLM 节点模式模板：patch 节点模块的 llm → 预设响应 → 调用节点 → 断言状态。
"""

import pytest


@pytest.fixture(autouse=True)
def _patch(mocker, fake_llm):
    """patch generate_sql 模块的 llm 引用为 fake。"""
    mocker.patch("app.agent.nodes.generate_sql.llm", fake_llm)


def _state(table_infos=None, metric_infos=None, date_info=None, db_info=None, query=""):
    return {
        "table_infos": table_infos or [],
        "metric_infos": metric_infos or [],
        "date_info": date_info or {"date": "", "weekday": "", "quarter": ""},
        "db_info": db_info or {"dialect": "mysql", "version": "8.0"},
        "query": query,
    }


@pytest.mark.asyncio
async def test_generate_sql_returns_sql_in_state(fake_llm):
    """LLM 返回的 SQL 应写入 state["sql"]。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.generate_sql import generate_sql
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response("SELECT COUNT(*) FROM orders")

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    result = await generate_sql(_state(query="统计订单总数"), runtime)

    assert result["sql"] == "SELECT COUNT(*) FROM orders"
    assert fake_llm.call_count >= 1
    # 进度事件应以 success 结束
    assert writer.last_status() == "success"
