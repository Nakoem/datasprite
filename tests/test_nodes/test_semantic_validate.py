"""
semantic_validate 节点测试

关键安全行为：LLM 调用失败时保守放行（宁放过不误杀）。
"""

import pytest


@pytest.fixture(autouse=True)
def _patch(mocker, fake_llm):
    mocker.patch("app.agent.nodes.semantic_validate.llm", fake_llm)


def _state(table_infos=None, metric_infos=None, db_info=None, query="", sql=""):
    return {
        "table_infos": table_infos or [],
        "metric_infos": metric_infos or [],
        "db_info": db_info or {"dialect": "mysql", "version": "8.0"},
        "query": query,
        "sql": sql,
    }


@pytest.mark.asyncio
async def test_semantic_validate_passes(fake_llm):
    """LLM 返回 pass=true → error 应为 None。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.semantic_validate import semantic_validate
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response('{"pass": true}')

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    result = await semantic_validate(
        _state(query="统计GMV", sql="SELECT SUM(gmv) FROM orders"), runtime
    )

    assert result["error"] is None


@pytest.mark.asyncio
async def test_semantic_validate_fails_with_reason(fake_llm):
    """LLM 返回 pass=false → error 应以 [语义校验] 开头。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.semantic_validate import semantic_validate
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response('{"pass": false, "reason": "缺少日期过滤条件"}')

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    result = await semantic_validate(
        _state(query="统计GMV", sql="SELECT SUM(gmv) FROM orders"), runtime
    )

    assert result["error"] is not None
    assert result["error"].startswith("[语义校验]")


@pytest.mark.asyncio
async def test_semantic_validate_injects_current_date(fake_llm):
    """date_info 必须注入校验 prompt——否则「去年/本月」等相对时间 LLM 没有日期基准会瞎猜，
    导致正确的年份（如 2025）被误杀，触发 correct_sql 无限重试。回归保护 bug：去年时间误判。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.semantic_validate import semantic_validate
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response('{"pass": true}')

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    state = _state(
        query="去年上海地区10月的销售额排名前5的商品",
        sql="SELECT ... WHERE f.date_id BETWEEN 20251001 AND 20251031 ...",
    )
    state["date_info"] = {"date": "2026-08-15", "weekday": "Saturday", "quarter": "Q3"}

    result = await semantic_validate(state, runtime)

    assert result["error"] is None
    # 校验 LLM 收到的完整 prompt 必须含当前日期（StringPromptValue 渲染后）
    assert "2026-08-15" in str(fake_llm.last_input)


@pytest.mark.asyncio
async def test_semantic_validate_conservative_on_llm_failure(fake_llm):
    """LLM 返回非法 JSON → 保守放行，error 为 None。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.semantic_validate import semantic_validate
    from tests.conftest import _FakeStreamWriter

    fake_llm.set_response("not valid json at all")

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {}
    runtime.stream_writer = writer

    result = await semantic_validate(
        _state(query="统计GMV", sql="SELECT SUM(gmv) FROM orders"), runtime
    )

    # 保守策略：LLM 异常时放行
    assert result["error"] is None
