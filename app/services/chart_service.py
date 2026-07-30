"""
图表服务 —— 从查询结果自动检测图表类型并生成 PNG 图片

把前端 chartDetector.ts + ChartView.tsx 的图表自动检测和渲染逻辑
移植到 Python 后端，通过 matplotlib 生成静态 PNG。
供 /api/ask 等接口调用，返回 base64 图片供飞书等外部渠道展示。
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

import matplotlib
matplotlib.use("Agg")  # 非交互式后端，不弹窗
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as mticker
import numpy as np

from app.core.log import logger

# ═══════════════════════════════════════════════════════════════
# 中文字体
# ═══════════════════════════════════════════════════════════════

def _setup_chinese_font():
    """查找可用中文字体并设为默认，找不到则回退 sans-serif"""
    for name in ("Noto Sans SC", "Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei"):
        try:
            fm.findfont(name, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
        except Exception:
            continue
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return "sans-serif"


_CHINESE_FONT = _setup_chinese_font()
logger.info("图表中文字体：{}", _CHINESE_FONT)

# ═══════════════════════════════════════════════════════════════
# 色板（对应 chartColors.ts）
# ═══════════════════════════════════════════════════════════════

CATEGORICAL = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
]

EMPHASIS = "#5E7855"       # moss 品牌色（单系列）
EMPHASIS_AREA = "#5E785519"  # moss 10% 透明度（面积填充）— 用 hex alpha
CHROME = {
    "gridline": "#E5E0D4",
    "baseline": "#C5BFB4",
    "ink": "#14110E",
    "inkSecondary": "#6B645A",
    "inkMuted": "#9A9284",
    "surface": "#FAF8F4",
}

# 面积图填充色（16 进制 argb → 实际用 matplotlib alpha）
EMPHASIS_AREA_RGBA = (0.369, 0.471, 0.333, 0.10)


def _to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, ...]:
    """hex → (r, g, b) 或 (r, g, b, a)，值域 0~1"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    return (r, g, b, alpha) if alpha < 1.0 else (r, g, b)


# ═══════════════════════════════════════════════════════════════
# 检测逻辑（移植自 chartDetector.ts）
# ═══════════════════════════════════════════════════════════════

TIME_KEYWORDS = [
    "日期", "时间", "月份", "季度", "年份", "年", "月", "日", "季",
    "date", "time", "month", "quarter", "year", "day", "week", "周",
]

TIME_VALUE_RE = re.compile(
    r"^\d{6}$"             # 202401 (YYYYMM)
    r"|^\d{8}$"             # 20240101 (YYYYMMDD)
    r"|^\d{4}[年/\-]\d{1,2}"  # 2024-01 / 2024年1月
    r"|^\d{4}Q[1-4]"        # 2024Q1
    r"|^Q[1-4]\s?\d{4}"     # Q1 2024
    r"|^\d{4}$"             # 2024 (仅年份)
)

PIE_MAX_SEGMENTS = 6
PIE_MAX_ROWS = 12
PART_WHOLE_COL_KEYWORDS = ["占比", "比例", "份额", "%", "percent", "share", "ratio"]
PART_WHOLE_QUERY_KEYWORDS = ["占比", "比例", "份额", "百分比", "占多少"]

STACKED_MAX_ROWS = 10
STACKED_MAX_MEASURES = 5
HEATMAP_MIN_CELLS = 4


def _is_time_column(name: str, sample_values: list[Any]) -> bool:
    """判断列是否为时间类型"""
    lower = name.lower()
    if any(kw in lower for kw in TIME_KEYWORDS):
        return True
    hits = sum(
        1 for v in sample_values
        if isinstance(v, str) and TIME_VALUE_RE.search(v.strip())
    )
    return hits >= min(3, len(sample_values))


def _is_numeric_column(values: list[Any]) -> bool:
    """判断列是否数值型（≥80% 能转成数字）"""
    hits = sum(
        1 for v in values
        if v is not None and v != "" and _try_number(v) is not None
    )
    return hits >= len(values) * 0.8


def _try_number(v: Any) -> float | None:
    """尝试把值转为 float，失败返回 None"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _is_part_whole_col(col_name: str) -> bool:
    """列名是否暗示占比"""
    lower = col_name.lower()
    return any(kw in lower for kw in PART_WHOLE_COL_KEYWORDS)


def _query_asks_part_whole(query: str | None) -> bool:
    """用户原始 query 是否问占比"""
    if not query:
        return False
    return any(kw in query for kw in PART_WHOLE_QUERY_KEYWORDS)


def _values_look_like_ratio(values: list[float]) -> bool:
    """数值是否像占比（0~1 或 0~100 区间）"""
    if not values:
        return False
    has_nonzero = any(v > 0 for v in values)
    if not has_nonzero:
        return False
    all_in_01 = all(0 <= v <= 1 for v in values)
    all_in_0100 = all(0 <= v <= 100 for v in values)
    return all_in_01 or all_in_0100


def _measures_same_scale(values: dict[str, list[float]]) -> bool:
    """多度量是否同量级（均值相差 ≤50 倍）"""
    avgs = {}
    for name, vals in values.items():
        if not vals:
            return True
        avgs[name] = sum(vals) / len(vals)
    if len(avgs) < 2:
        return True
    max_avg = max(avgs.values())
    min_avg = min(avgs.values())
    if min_avg == 0:
        return False
    return max_avg / min_avg <= 50


def _normalize_rows(data: Any) -> list[dict[str, Any]]:
    """把各种形状的 data 统一为 list[dict]"""
    if isinstance(data, list):
        result = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                result.append(item)
            else:
                result.append({"序号": i + 1, "值": item})
        return result
    if isinstance(data, dict):
        return [data]
    return [{"值": data}]


def detect_chart_type(
    data: Any, query: str | None = None
) -> dict[str, Any]:
    """
    分析查询结果，返回图表类型建议。

    返回 dict：
    {chart_type, dimensionCol, dimensionCol2, measureCols, reason}
    chart_type: "bar" | "line" | "area" | "pie" | "stackedBar" | "heatmap" | "table" | None
    """
    rows = _normalize_rows(data)
    if len(rows) == 0:
        return {"chartType": None, "dimensionCol": None, "measureCols": [], "reason": "无数据"}

    columns = list(rows[0].keys())
    if len(columns) < 2:
        return {"chartType": "table", "dimensionCol": None, "measureCols": [], "reason": "仅单列"}

    sample_size = min(len(rows), 10)
    sample_rows = rows[:sample_size]

    def col_values(col: str) -> list[Any]:
        return [r.get(col) for r in sample_rows]

    dim_cols: list[str] = []
    measure_cols: list[str] = []

    for col in columns:
        if _is_numeric_column(col_values(col)):
            measure_cols.append(col)
        else:
            dim_cols.append(col)

    # 从度量列中揪出时间列（如 "月份" 的值为 202401，会被误判为数字列）
    time_measures = [c for c in measure_cols if _is_time_column(c, col_values(c))]
    for c in time_measures:
        measure_cols.remove(c)
        dim_cols.append(c)

    if not measure_cols:
        return {"chartType": "table", "dimensionCol": None, "measureCols": [], "reason": "无度量值列"}

    primary_dim = dim_cols[0] if dim_cols else columns[0]
    primary_measure = measure_cols[0]

    if len(rows) > 30:
        return {
            "chartType": "table",
            "dimensionCol": primary_dim,
            "measureCols": measure_cols,
            "reason": f"行数过多（{len(rows)} 行）",
        }

    # 时间维度
    time_col = next((c for c in dim_cols if _is_time_column(c, col_values(c))), None)
    if time_col:
        other_dims = [c for c in dim_cols if c != time_col]
        if other_dims and len(measure_cols) == 1 and len(rows) >= 4:
            return {
                "chartType": "line",
                "dimensionCol": time_col,
                "dimensionCol2": other_dims[0],
                "measureCols": measure_cols,
            }
        if len(measure_cols) == 1:
            return {"chartType": "area", "dimensionCol": time_col, "measureCols": measure_cols}
        return {"chartType": "line", "dimensionCol": time_col, "measureCols": measure_cols}

    # 单度量
    if len(measure_cols) == 1 and dim_cols:
        vals = [_try_number(r.get(primary_measure)) for r in rows]
        vals_f = [v for v in vals if v is not None]

        # 占比 → 饼图
        part_whole = (
            _is_part_whole_col(primary_measure) or _query_asks_part_whole(query)
        ) and _values_look_like_ratio(vals_f)
        if part_whole and 2 <= len(rows) <= PIE_MAX_SEGMENTS:
            return {"chartType": "pie", "dimensionCol": primary_dim, "measureCols": measure_cols}

        # 双维度交叉
        non_time_dims = [
            c for c in dim_cols if not _is_time_column(c, col_values(c))
        ]
        if non_time_dims and len(non_time_dims) >= 2:
            if HEATMAP_MIN_CELLS <= len(rows) <= 30:
                return {
                    "chartType": "heatmap",
                    "dimensionCol": non_time_dims[0],
                    "dimensionCol2": non_time_dims[1],
                    "measureCols": [primary_measure],
                }
            if len(rows) >= 2:
                return {
                    "chartType": "bar",
                    "dimensionCol": non_time_dims[0],
                    "dimensionCol2": non_time_dims[1],
                    "measureCols": measure_cols,
                }

        return {"chartType": "bar", "dimensionCol": primary_dim, "measureCols": measure_cols}

    # 多度量
    if (
        2 <= len(measure_cols) <= STACKED_MAX_MEASURES
        and dim_cols
        and len(rows) <= STACKED_MAX_ROWS
    ):
        measure_vals: dict[str, list[float]] = {}
        for m in measure_cols:
            measure_vals[m] = [_try_number(r.get(m, 0)) or 0 for r in rows]
        if _measures_same_scale(measure_vals):
            return {"chartType": "stackedBar", "dimensionCol": primary_dim, "measureCols": measure_cols}
        return {"chartType": "bar", "dimensionCol": primary_dim, "measureCols": measure_cols}

    return {
        "chartType": "table",
        "dimensionCol": primary_dim,
        "measureCols": measure_cols,
        "reason": f"列数较多（{len(columns)}）",
    }


# ═══════════════════════════════════════════════════════════════
# 格式化
# ═══════════════════════════════════════════════════════════════

def _fmt(v: Any) -> str:
    """数值格式化（对应前端 formatValue）"""
    if v is None:
        return "-"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return str(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}"


# ═══════════════════════════════════════════════════════════════
# 图表生成函数
# ═══════════════════════════════════════════════════════════════

# 图表尺寸
FIG_W = 8
FIG_H = 4.5
DPI = 120


def _set_chrome(ax: plt.Axes):
    """统一 chrome 样式"""
    ax.set_facecolor(CHROME["surface"])
    ax.grid(
        True, axis="y", color=CHROME["gridline"],
        linewidth=0.8, zorder=0,
    )
    ax.tick_params(
        colors=CHROME["inkMuted"], labelsize=10,
        left=False, bottom=False,
    )
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt(x)))


def _build_chart_data(
    rows: list[dict[str, Any]], hint: dict
) -> tuple[list[dict], list[str], str | None, str | None]:
    """
    把原始行数据转为图表可用格式。
    返回 (chart_data, data_keys, dim_col, dim_col2)
    其中 chart_data 每条为 {name, series1, series2, ...}
    """
    dim_col = hint.get("dimensionCol")
    dim_col2 = hint.get("dimensionCol2")
    measure_cols = hint.get("measureCols", [])

    if not dim_col:
        return rows, measure_cols, None, None

    if not dim_col2:
        chart_data = []
        for r in rows:
            item = {"name": str(r.get(dim_col, ""))}
            for m in measure_cols:
                item[m] = _try_number(r.get(m)) or 0
            chart_data.append(item)
        return chart_data, measure_cols, dim_col, None

    # 多系列：按 dimCol2 透视
    x_vals = list(dict.fromkeys(str(r.get(dim_col, "")) for r in rows))
    series_names = list(dict.fromkeys(str(r.get(dim_col2, "")) for r in rows))

    lookup: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        x = str(r.get(dim_col, ""))
        s = str(r.get(dim_col2, ""))
        lookup.setdefault(x, {}).setdefault(s, {})
        for m in measure_cols:
            lookup[x][s][m] = _try_number(r.get(m)) or 0

    chart_data = []
    for x in x_vals:
        point: dict[str, Any] = {"name": x}
        for s in series_names:
            for m in measure_cols:
                key = s if len(measure_cols) == 1 else f"{s}·{m}"
                point[key] = lookup.get(x, {}).get(s, {}).get(m, 0)
        chart_data.append(point)

    data_keys = (
        series_names
        if len(measure_cols) == 1
        else [f"{s}·{m}" for s in series_names for m in measure_cols]
    )
    return chart_data, data_keys, dim_col, dim_col2


def _generate_bar_chart(rows: list[dict], hint: dict) -> io.BytesIO:
    """柱状图"""
    chart_data, data_keys, dim_col, dim_col2 = _build_chart_data(rows, hint)
    labels = [d["name"] for d in chart_data]
    x = np.arange(len(labels))
    n_bars = len(data_keys)
    bar_w = 0.7 / max(n_bars, 1)

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    _set_chrome(ax)

    for i, key in enumerate(data_keys):
        vals = [d.get(key, 0) for d in chart_data]
        color = EMPHASIS if n_bars == 1 else CATEGORICAL[i % len(CATEGORICAL)]
        offset = (i - (n_bars - 1) / 2) * bar_w
        ax.bar(
            x + offset, vals, bar_w * 0.9,
            color=_to_rgba(color),
            edgecolor="white", linewidth=0.5,
            label=key if n_bars > 1 else None,
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9, color=CHROME["inkSecondary"])
    if n_bars > 1:
        ax.legend(
            fontsize=9, frameon=False, labelcolor=CHROME["inkSecondary"],
            loc="upper right",
        )

    ax.set_ylim(bottom=0)
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_line_chart(rows: list[dict], hint: dict) -> io.BytesIO:
    """折线图"""
    chart_data, data_keys, dim_col, _ = _build_chart_data(rows, hint)
    labels = [d["name"] for d in chart_data]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    _set_chrome(ax)

    for i, key in enumerate(data_keys):
        vals = [d.get(key, 0) for d in chart_data]
        color = EMPHASIS if len(data_keys) == 1 else CATEGORICAL[i % len(CATEGORICAL)]
        ax.plot(
            x, vals,
            color=_to_rgba(color), linewidth=2,
            marker="o", markersize=5,
            markerfacecolor=color, markeredgecolor="white", markeredgewidth=1.5,
            label=key if len(data_keys) > 1 else None,
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9, color=CHROME["inkSecondary"])
    if len(data_keys) > 1:
        ax.legend(
            fontsize=9, frameon=False, labelcolor=CHROME["inkSecondary"],
            loc="upper right",
        )

    ax.set_ylim(bottom=0)
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_area_chart(rows: list[dict], hint: dict) -> io.BytesIO:
    """面积图"""
    chart_data, data_keys, dim_col, _ = _build_chart_data(rows, hint)
    labels = [d["name"] for d in chart_data]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    _set_chrome(ax)

    for i, key in enumerate(data_keys):
        vals = [d.get(key, 0) for d in chart_data]
        color = EMPHASIS if len(data_keys) == 1 else CATEGORICAL[i % len(CATEGORICAL)]
        ax.fill_between(
            x, vals,
            color=_to_rgba(color, 0.10),
            step=None, zorder=2,
        )
        ax.plot(
            x, vals,
            color=_to_rgba(color), linewidth=2,
            marker="o", markersize=5,
            markerfacecolor=color, markeredgecolor="white", markeredgewidth=1.5,
            label=key if len(data_keys) > 1 else None,
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9, color=CHROME["inkSecondary"])
    if len(data_keys) > 1:
        ax.legend(
            fontsize=9, frameon=False, labelcolor=CHROME["inkSecondary"],
            loc="upper right",
        )

    ax.set_ylim(bottom=0)
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_pie_chart(rows: list[dict], hint: dict) -> io.BytesIO:
    """饼图"""
    dim_col = hint.get("dimensionCol")
    measure_cols = hint.get("measureCols", [])
    if not dim_col or not measure_cols:
        return _empty_buf()

    measure = measure_cols[0]
    labels = [str(r.get(dim_col, "")) for r in rows]
    values = [_try_number(r.get(measure)) or 0 for r in rows]

    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=DPI)
    colors = [_to_rgba(CATEGORICAL[i % len(CATEGORICAL)]) for i in range(len(labels))]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        pctdistance=0.75,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5, "width": 0.55},
        textprops={"fontsize": 9, "color": CHROME["inkSecondary"]},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color(CHROME["ink"])

    # 图例放右侧
    ax.legend(
        wedges, labels,
        title="",
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        frameon=False,
        fontsize=9,
        labelcolor=CHROME["inkSecondary"],
    )
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _generate_stacked_bar_chart(rows: list[dict], hint: dict) -> io.BytesIO:
    """堆叠柱状图"""
    chart_data, data_keys, dim_col, _ = _build_chart_data(rows, hint)
    labels = [d["name"] for d in chart_data]
    x = np.arange(len(labels))
    bar_w = 0.5

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)
    _set_chrome(ax)

    bottom = np.zeros(len(labels))
    for i, key in enumerate(data_keys):
        vals = [d.get(key, 0) for d in chart_data]
        color = CATEGORICAL[i % len(CATEGORICAL)]
        ax.bar(
            x, vals, bar_w,
            bottom=bottom,
            color=_to_rgba(color),
            edgecolor="white", linewidth=0.5,
            label=key,
            zorder=3,
        )
        bottom += np.array(vals)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9, color=CHROME["inkSecondary"])
    ax.legend(
        fontsize=9, frameon=False, labelcolor=CHROME["inkSecondary"],
        loc="upper right",
    )

    ax.set_ylim(bottom=0)
    fig.tight_layout(pad=1.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _empty_buf() -> io.BytesIO:
    """空图片（兜底）"""
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(FIG_W, 1), dpi=DPI)
    ax.text(0.5, 0.5, "暂无图表", ha="center", va="center", fontsize=12, color=CHROME["inkMuted"])
    ax.axis("off")
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

_CHART_GENERATORS = {
    "bar": _generate_bar_chart,
    "line": _generate_line_chart,
    "area": _generate_area_chart,
    "pie": _generate_pie_chart,
    "stackedBar": _generate_stacked_bar_chart,
}


def generate_chart(
    data: Any, query: str | None = None
) -> str | None:
    """
    从查询结果生成图表，返回 base64 编码的 PNG 字符串。

    如果数据不适合出图（chartType == "table" 或 None），返回 None。
    """
    if data is None:
        return None

    hint = detect_chart_type(data, query)
    chart_type = hint.get("chartType")
    if not chart_type or chart_type == "table":
        if chart_type == "table":
            logger.debug(
                "chart_service: 检测为 table | reason={} | measureCols={}",
                hint.get("reason"), hint.get("measureCols"),
            )
        return None

    rows = _normalize_rows(data)
    generator = _CHART_GENERATORS.get(chart_type)
    if not generator:
        logger.warning("chart_service: 不支持的图表类型 {}", chart_type)
        return None

    try:
        buf = generator(rows, hint)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        logger.info(
            "chart_service: 生成 {} 图表 | 数据行数={} | size={:.1f}KB",
            chart_type, len(rows), len(b64) / 1024,
        )
        return b64
    except Exception:
        logger.exception("chart_service: 图表生成失败")
        return None
