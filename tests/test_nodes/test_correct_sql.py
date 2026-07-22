"""
correct_sql 节点测试

关键逻辑：correct_retry_count 递增、error 清除（供后续 validate 重判）。
"""

import pytest


@pytest.fixture(autouse=True)
def _patch(mocker, fake_llm):
    mocker.patch("app.agent.nodes.correct_sql.llm", fake_llm)


def _state(
    table_infos=None,
    metric_infos=None,
    date_info=None,
    db_info=None,
    query="",
    sql="",
    error="",
    correct_retry_count=0,
):
    return {
        "table_infos": table_infos or [],
        "metric_infos": metric_infos or [],
        "date_info": date_info or {"date": "", "weekday": "", "quarter": ""},
        "db_info": db_info or {"dialect": "mysql", "version": "8.0"},
        "query": query,
        "sql": sql,
        "error": error,
        "correct_retry_count": correct_retry_count,
    }


@pytest.mark.asyncio
async def test_correct_sql_increments_retry_count(fake_llm):
    """修正后 retry_count +1，error 清除。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.correct_sql import correct_sql
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response("SELECT COUNT(*) FROM orders WHERE status = 'paid'")

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    result = await correct_sql(
        _state(
            query="统计已支付订单数",
            sql="SELECT COUNT(*) FROM orders WHERE status = 'payed'",
            error="Unknown column 'payed'",
            correct_retry_count=1,
        ),
        runtime,
    )

    assert result["correct_retry_count"] == 2
    assert result["error"] is None  # 清除错误供 validate 重判
    assert "paid" in result["sql"]
