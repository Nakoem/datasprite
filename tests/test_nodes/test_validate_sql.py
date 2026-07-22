"""
validate_sql 节点测试

该节点用 MySQL EXPLAIN 校验 SQL，是关键的语法安全边界。
基础设施错误必须抛出，语法错误必须返回（不崩溃）。
"""

import pytest

from tests.conftest import FakeDWMySQLRepository, _FakeStreamWriter


def _state(sql: str) -> dict:
    return {"sql": sql}


@pytest.mark.asyncio
async def test_validate_sql_passes_when_explain_succeeds():
    """EXPLAIN 成功 → error 应为 None。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.validate_sql import validate_sql

    dw = FakeDWMySQLRepository()  # 不抛异常 = EXPLAIN 通过
    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {"dw_mysql_repository": dw}
    runtime.stream_writer = writer

    result = await validate_sql(_state("SELECT 1"), runtime)

    assert result["error"] is None
    assert len(dw.validated_sqls) == 1
    # Fake 仓储原样记录 SQL，不做 EXPLAIN 包装（那是真实仓储的逻辑）


@pytest.mark.asyncio
async def test_validate_sql_returns_error_on_bad_syntax():
    """SQL 语法错 → error 应包含错误信息，不应抛出。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.validate_sql import validate_sql

    dw = FakeDWMySQLRepository(
        raise_on_validate=Exception("Table 'xxx' doesn't exist")
    )
    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {"dw_mysql_repository": dw}
    runtime.stream_writer = writer

    result = await validate_sql(_state("SELECT * FROM xxx"), runtime)

    assert result["error"] is not None
    assert "doesn't exist" in result["error"]


@pytest.mark.asyncio
async def test_validate_sql_raises_on_infra_error():
    """基础设施错误（断连）→ 必须向上抛出，不能写入 error。"""
    from unittest.mock import MagicMock

    from app.agent.nodes.validate_sql import validate_sql

    dw = FakeDWMySQLRepository(
        raise_on_validate=Exception("connection refused")
    )
    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = {"dw_mysql_repository": dw}
    runtime.stream_writer = writer

    with pytest.raises(Exception, match="connection refused"):
        await validate_sql(_state("SELECT 1"), runtime)
