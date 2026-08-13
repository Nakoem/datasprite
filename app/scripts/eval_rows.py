"""
评测结果集对比共享工具

从 run_evaluation.py 抽离，供评测批跑与候选审核（sync_eval_questions）共用同一份
「结果集对比」实现，避免两边语义漂移。

两层比对：
- 严格比对：数值取整 + 忽略列名排序后逐行一致（默认路径，零额外容忍）。
- 宽松兜底（#35）：仅当严格比对失败时，对「年月/日期形态」的取值做键归一后再比。
  修 q12 月度标签格式漂移盲区——同一种「按月分组」系统每次标签格式都不同
  （date_id DIV 100 → 202501 整数、DATE_FORMAT %Y-%m → '2025-01'、SUBSTRING → '202501'、
  '2025年1月'），业务等价但格式不同导致严格比对误判。
  兜底是「值形态」判定：字符串模式无歧义直接归一；整数 YYYYMM 仅在列名像时间键、
  且为 int 类型、年月在合理范围时才归一，避免把销售额 202501.0 这种普通数值误判成时间键。
"""

import re
from decimal import Decimal

# 年月/日期形态的正则（字符串模式无歧义，可安全归一）
_YM_STR_RE = re.compile(r"^(\d{4})-(\d{1,2})$")  # '2025-01'
_YM_INT_STR_RE = re.compile(r"^(\d{4})(\d{2})$")  # '202501'（SUBSTRING 产物）
_YM_CN_RE = re.compile(r"^(\d{4})年(\d{1,2})月$")  # '2025年1月'
_DATE_STR_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")  # '2025-01-15'

# 整数 YYYYMM 归一化需列名像时间键（保守，防普通数值误判）。
# 只用月度/日期类子串，不放 year/week 等易匹配到普通列（如 year_total）的子串。
_TIME_COL_HINTS = (
    "month",
    "date",
    "月份",
    "日期",
    "年月",
    "季度",
)


def _is_time_col(name: str) -> bool:
    name = (name or "").lower()
    return any(h in name for h in _TIME_COL_HINTS)


def _in_year_month(year: int, month: int) -> bool:
    return 1970 <= year <= 2099 and 1 <= month <= 12


def _in_ymd(year: int, month: int, day: int) -> bool:
    return _in_year_month(year, month) and 1 <= day <= 31


def normalize_value(v):
    """数值统一取整，避免浮点 / Decimal 精度差异误判不一致"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return round(float(v), 6)
    return v


def _time_key(col_name: str, v):
    """把「年月/日期形态」的取值归一成 (kind, *parts) 元组；非时间形态原样返回。

    只认形态 + 范围校验：字符串模式无歧义；整数 YYYYMM 要求列名像时间键且为 int。
    """
    if isinstance(v, str):
        s = v.strip()
        m = _YM_STR_RE.match(s) or _YM_INT_STR_RE.match(s) or _YM_CN_RE.match(s)
        if m and _in_year_month(int(m.group(1)), int(m.group(2))):
            return ("ym", int(m.group(1)), int(m.group(2)))
        m = _DATE_STR_RE.match(s)
        if m and _in_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3))):
            return ("date", int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return v
    if isinstance(v, int) and _is_time_col(col_name) and 197001 <= v <= 209912:
        year, month = divmod(v, 100)
        if _in_year_month(year, month):
            return ("ym", year, month)
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


def _relaxed_rows(rows: list[dict]) -> list:
    """宽松归一后的行集：仅对「年月/日期形态」取值做时间键归一，其余值仍取整。

    保留列名参与判定（整数 YYYYMM 需要），但排序时仍忽略列名（对齐严格路径）。
    """
    out = []
    for row in rows or []:
        values = tuple(
            sorted(
                (normalize_value(_time_key(k, v)) for k, v in row.items()),
                key=repr,
            )
        )
        out.append(values)
    return sorted(out)


def rows_equal(expected: list[dict], actual: list[dict]) -> bool:
    """结果集对比：期望结果与生成 SQL 结果是否一致。

    先严格比对（数值取整 + 排序）；不过再走时间键宽松兜底（#35），
    只放行「年月/日期标签格式漂移」这类业务等价的差异，其余仍严格。
    """
    if canonical_rows(expected) == canonical_rows(actual):
        return True
    return _relaxed_rows(expected) == _relaxed_rows(actual)
