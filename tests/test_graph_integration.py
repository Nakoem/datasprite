"""
图级集成测试

验证完整的 LangGraph 拓扑和条件路由逻辑，所有外部依赖用 fake 替代。
"""

import pytest

from tests.conftest import (
    FakeColumnQdrantRepository,
    FakeDWMySQLRepository,
    FakeEmbeddingClient,
    FakeMetaMySQLRepository,
    FakeMetricQdrantRepository,
    FakeValueESRepository,
)

# ── 所有 import LLM 的节点模块 ──────────────────────────────────
_LLM_MODULES = [
    "app.agent.nodes.classify_intent",
    "app.agent.nodes.recall_column",
    "app.agent.nodes.recall_value",
    "app.agent.nodes.recall_metric",
    "app.agent.nodes.filter_table",
    "app.agent.nodes.filter_metric",
    "app.agent.nodes.dream",
    "app.agent.nodes.generate_sql",
    "app.agent.nodes.semantic_validate",
    "app.agent.nodes.correct_sql",
    "app.agent.nodes.summarize_result",
]


def _patch_llm_modules(mocker, fake):
    """mock.patch 所有 LLM 节点模块的 llm 引用为 fake。"""
    for mod in _LLM_MODULES:
        mocker.patch(f"{mod}.llm", fake)


def _patch_llm_modules_direct(fake):
    """直接赋值 hack：绕过 mock.patch，适合特殊调试场景。"""
    import sys

    patched = []
    for mod_path in _LLM_MODULES:
        if mod_path in sys.modules:
            mod = sys.modules[mod_path]
            patched.append((mod, mod.llm))
            mod.llm = fake
    return patched


def _restore_llm_modules(patched):
    for mod, original in patched:
        mod.llm = original


def _make_context(dw=None):
    """组装一份全 fake 的 DataAgentContext。"""
    return {
        "column_qdrant_repository": FakeColumnQdrantRepository(),
        "metric_qdrant_repository": FakeMetricQdrantRepository(),
        "value_es_repository": FakeValueESRepository(),
        "embedding_client": FakeEmbeddingClient(),
        "meta_mysql_repository": FakeMetaMySQLRepository(),
        "dw_mysql_repository": dw or FakeDWMySQLRepository(
            run_results=[{"total": 12345}],
        ),
    }


@pytest.mark.asyncio
async def test_full_graph_happy_path(mocker, fake_llm):
    """全图 Happy Path：所有节点 mock，验证 START → END 完整链路。

    并行节点（recall x3 / filter x2）的响应设计为可互换：
    - recall 三次都需要 JSON 数组 → 全返回 '["销售"]'
    - filter 两次 {} 对 filter_table / filter_metric 都安全
    - dream 节点 history 为空，len=0 ≤ 3000，跳过（无 LLM 调用）
    """
    from app.agent.graph import compile_graph

    fake_llm.set_sequence([
        '{"intent": "new"}',     # 1: classify_intent
        '["销售", "华北"]',       # 2-4: recall x3（并行）
        '["销售", "华北"]',
        '["销售", "华北"]',
        "{}",                     # 5-6: filter x2（并行）
        "{}",
        "SELECT 1 AS demo",       # 7: generate_sql
        '{"pass": true}',         # 8: semantic_validate
        '{"summary": "查询完成，共 1 条记录"}',   # 9: summarize_result
    ])

    _patch_llm_modules(mocker, fake_llm)

    graph = compile_graph()
    state = {"query": "统计华北地区销售总额", "correct_retry_count": 0}
    context = _make_context()

    events: list[dict] = []
    async for chunk in graph.astream(
        input=state, context=context, stream_mode="custom",
    ):
        events.append(chunk)

    # ── 断言：关键步骤应全部出现 ──────────────────────────────
    steps_seen = {
        e.get("step") for e in events
        if e.get("type") == "progress"
    }
    expected_steps = {
        "分析意图", "抽取关键词",
        "召回字段信息", "召回字段取值", "召回指标信息",
        "过滤表信息", "过滤指标信息",
        "生成SQL", "校验SQL", "语义校验",
        "执行SQL", "生成结果解读",
    }
    missing = expected_steps - steps_seen
    assert not missing, f"缺少步骤：{missing}"

    # 应产生最终结果和摘要
    assert any(e.get("type") == "result" for e in events), "应有 result 事件"
    assert any(e.get("type") == "summary" for e in events), "应有 summary 事件"


@pytest.mark.asyncio
async def test_graph_retry_loop(mocker, fake_llm):
    """验证 SQL 修正闭环：超限后仍执行 run_sql。"""
    from app.agent.graph import compile_graph

    dw = FakeDWMySQLRepository(
        raise_on_validate=[
            Exception("Table 'xxx' doesn't exist"),
            Exception("Unknown column 'yyy'"),
            Exception("Syntax error near 'ZZZ'"),
            None,  # 第 4 次通过
        ],
        run_results=[{"cnt": 100}],
    )

    # LLM 响应序列（3 次 correct + generate + classify + recall x3 + filter x2 + semantic + summarize）
    fake_llm.set_sequence([
        '{"intent": "new"}',           # classify_intent
        '["销售"]', '["销售"]', '["销售"]',  # recall x3
        "{}", "{}",                     # filter x2
        "SELECT * FROM bad_table",      # generate_sql
        # 第 1 次修正：
        "SELECT * FROM bad_table2",     # correct_sql ①
        # 第 2 次修正：
        "SELECT * FROM bad_table3",     # correct_sql ②
        # 第 3 次修正：
        "SELECT * FROM bad_table4",     # correct_sql ③
        # 第 4 次 validate 通过 → semantic_validate
        '{"pass": true}',
        # summarize
        '{"summary": "修正后查询完成"}',
    ])

    _patch_llm_modules(mocker, fake_llm)

    ctx = _make_context(dw=dw)
    graph = compile_graph()
    state = {"query": "统计销售", "correct_retry_count": 0}

    events: list[dict] = []
    async for chunk in graph.astream(
        input=state, context=ctx, stream_mode="custom",
    ):
        events.append(chunk)

    # 3 次修正（每次有 running + success/retry 两个事件）
    correct_events = [
        e for e in events
        if e.get("type") == "progress"
        and e.get("step") == "校正SQL"
        and e.get("status") == "running"
    ]
    assert len(correct_events) == 3, f"预期 3 次修正，实际 {len(correct_events)}"

    # 最终仍产生 result（超限后走 run_sql）
    assert any(e.get("type") == "result" for e in events), "超限后应有 result"
