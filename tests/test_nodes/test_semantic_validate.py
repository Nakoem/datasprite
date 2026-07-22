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
