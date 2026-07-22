"""
extract_keywords 节点测试

该节点仅依赖 jieba 分词，不需要 LLM / 数据库 / 外部服务，
是项目里最容易测试的节点。
"""

import pytest

from app.agent.nodes.extract_keywords import extract_keywords
from tests.conftest import _FakeStreamWriter


@pytest.mark.asyncio
async def test_extract_keywords_basic():
    """关键词应包含原始查询作为兜底，且非空。"""
    from unittest.mock import MagicMock

    runtime = MagicMock()
    runtime.stream_writer = _FakeStreamWriter()

    state = {"query": "统计华北地区的销售总额"}
    result = await extract_keywords(state, runtime)

    keywords = result["keywords"]
    assert len(keywords) > 0, "关键词列表不应为空"
    assert "统计华北地区的销售总额" in keywords, "原始 query 应作为兜底保留"


@pytest.mark.asyncio
async def test_extract_keywords_progress_events():
    """应写入 running → success 进度事件。"""
    from unittest.mock import MagicMock

    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.stream_writer = writer

    state = {"query": "查询GMV"}
    await extract_keywords(state, runtime)

    statuses = [e.get("status") for e in writer.events]
    assert "running" in statuses
    assert "success" in statuses


@pytest.mark.asyncio
async def test_extract_keywords_deduplication():
    """关键词应去重（set）。"""
    from unittest.mock import MagicMock

    runtime = MagicMock()
    runtime.stream_writer = _FakeStreamWriter()

    state = {"query": "销售额"}
    result = await extract_keywords(state, runtime)

    # 不应有重复关键词
    keywords = result["keywords"]
    assert len(keywords) == len(set(keywords))
