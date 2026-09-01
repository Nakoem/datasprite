"""
_schema_compact 瘦身函数测试（#39 问数降本）

关键安全行为：元数据的 description / alias / examples 在库里可为 NULL
（见 app/models/*.py 的 `Mapped[... | None]`），瘦身时不能因此抛异常——
filter_table / filter_metric 的 except 是 raise，这里炸掉会让整个问数请求失败。
"""

import yaml

from app.agent.nodes._schema_compact import compact_metric_infos, compact_table_infos


def _column(**overrides):
    """构造一个字段，默认全字段齐备；overrides 用来注入 None 等异常值"""
    column = {
        "name": "order_id",
        "type": "varchar",
        "role": "dim",
        "examples": ["A001", "A002", "A003"],
        "description": "订单编号",
        "alias": ["订单号"],
    }
    column.update(overrides)
    return column


def _table(columns=None, **overrides):
    table = {
        "name": "fact_order",
        "role": "fact",
        "description": "订单事实表",
        "columns": columns if columns is not None else [_column()],
    }
    table.update(overrides)
    return table


# ═══════════════════════════════════════════════════════════════════
# NULL 兼容：库里字段可为 NULL，瘦身绝不能抛异常
# ═══════════════════════════════════════════════════════════════════


def test_column_alias_none_does_not_raise():
    """alias=None（库里 NULL）→ 渲染成空列表，而不是 TypeError。

    回归防护：ColumnInfoState 是显式构造的，键一定存在，
    所以 `.get("alias", [])` 的默认值不生效，必须写成 `or []`。
    """
    out = compact_table_infos([_table(columns=[_column(alias=None)])])
    assert yaml.safe_load(out)[0]["columns"][0]["alias"] == []


def test_column_examples_none_does_not_raise():
    """examples=None → 空列表，不能因切片/迭代 None 崩掉。"""
    out = compact_table_infos([_table(columns=[_column(examples=None)])])
    assert yaml.safe_load(out)[0]["columns"][0]["examples"] == []


def test_description_none_becomes_empty_not_literal_none():
    """description=None 不能变成字符串 "None" 塞进提示词（污染语义）。"""
    out = compact_table_infos(
        [_table(description=None, columns=[_column(description=None)])]
    )
    parsed = yaml.safe_load(out)[0]
    assert parsed["description"] == ""
    assert parsed["columns"][0]["description"] == ""


def test_metric_alias_and_description_none_does_not_raise():
    """指标侧同样可为 NULL（metric_info.alias 是 JSON 可空列）。"""
    out = compact_metric_infos(
        [{"name": "销售额", "description": None, "relevant_columns": [], "alias": None}]
    )
    parsed = yaml.safe_load(out)[0]
    assert parsed["alias"] == []
    assert parsed["description"] == ""


def test_all_nullable_fields_none_does_not_raise():
    """极端情况：一整行元数据的可空字段全是 NULL。"""
    out = compact_table_infos(
        [
            _table(
                description=None,
                columns=[_column(examples=None, description=None, alias=None)],
            )
        ]
    )
    assert yaml.safe_load(out)[0]["columns"][0]["alias"] == []


# ═══════════════════════════════════════════════════════════════════
# 瘦身语义：只截断，不丢字段
# ═══════════════════════════════════════════════════════════════════


def test_examples_limited_to_two_and_truncated():
    """examples 是 token 大头，只留前 2 个。"""
    out = compact_table_infos(
        [_table(columns=[_column(examples=["a", "b", "c", "d", "x" * 100])])]
    )
    examples = yaml.safe_load(out)[0]["columns"][0]["examples"]
    assert examples == ["a", "b"]


def test_long_description_truncated_with_ellipsis():
    out = compact_table_infos([_table(columns=[_column(description="很长" * 100)])])
    desc = yaml.safe_load(out)[0]["columns"][0]["description"]
    assert len(desc) == 60
    assert desc.endswith("…")


def test_no_column_field_is_dropped():
    """瘦身是截断不是删除——ColumnInfoState 的 6 个键必须全在。

    列级用的是白名单重建（非 {**column} 展开），若将来给
    ColumnInfoState 加字段，这条会先红，提醒同步更新白名单。
    """
    out = compact_table_infos([_table()])
    column = yaml.safe_load(out)[0]["columns"][0]
    assert set(column) == {"name", "type", "role", "examples", "description", "alias"}


def test_table_level_other_fields_preserved():
    """{**table_info} 展开：除 description/columns 外的键原样保留。"""
    table = yaml.safe_load(compact_table_infos([_table()]))[0]
    assert table["name"] == "fact_order"
    assert table["role"] == "fact"


def test_empty_input_returns_empty_yaml():
    assert compact_table_infos([]).strip() == "[]"
    assert compact_metric_infos([]).strip() == "[]"
