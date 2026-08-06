"""
评测结果集对比共享工具

从 run_evaluation.py 抽离，供评测批跑与候选审核（sync_eval_questions）共用同一份
「结果集对比」实现，避免两边语义漂移。
"""

from decimal import Decimal


def normalize_value(v):
    """数值统一取整，避免浮点 / Decimal 精度差异误判不一致"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return round(float(v), 6)
    return v


def canonical_rows(rows: list[dict]) -> list:
    """每行只取排序后的值元组，整张表再按行排序。

    刻意忽略列名：智能体生成的 SQL 别名可能与期望 SQL 不同（如 total_amount vs
    销售总额），但数值一致就算答对；列名不一致不应误判。列数不同仍会判不一致。
    """
    out = []
    for row in rows or []:
        # key=repr 提供全类型稳定全序：None / 数字 / 字符串混排不抛 TypeError
        values = tuple(sorted((normalize_value(v) for v in row.values()), key=repr))
        out.append(values)
    return sorted(out)


def rows_equal(expected: list[dict], actual: list[dict]) -> bool:
    """结果集对比：期望结果与生成 SQL 结果是否一致"""
    return canonical_rows(expected) == canonical_rows(actual)
