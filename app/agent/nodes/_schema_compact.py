"""
筛选节点输入瘦身（#39 问数降本方向②）

filter_table / filter_metric 的 prompt 输入会把全部候选结构 dump 成 YAML 塞给 LLM，
实测（#38 by_node）吃掉约 30% 的总 token——其中大头是字段的真实样例值
（examples 常达千个）与中文描述。本模块在「塞进 prompt 前」做无损裁剪：

- 不删除任何字段，只截断长度 / 限制示例个数（保结构语义，不影响下游 state）
- 影响的只是筛选节点的输入，state 里的 table_infos / metric_infos 原样不动，
  generate_sql 等其他消费方拿到的是完整结构，不受影响
- 降级保护（格式异常 → 保留全部候选）逻辑不在本模块，原样保留在节点里
"""

import yaml

from app.agent.state import MetricInfoState, TableInfoState

# 描述类文本最大保留字符（中文说明，60 字足够理解字段语义）
_DESC_MAX = 60
# 字段真实样例值最多保留个数（辅助 where 枚举判断用，多了是重复 token 黑洞）
_EXAMPLE_LIMIT = 2
# 单个样例值最大保留字符
_VALUE_MAX = 30
# 别名单项最大保留字符
_ALIAS_MAX = 20


def _truncate(value, max_len: int) -> str:
    s = str(value)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def compact_table_infos(table_infos: list[TableInfoState]) -> str:
    """把候选表结构压缩成语义等价的 YAML 文本（只截断，不删字段）"""
    compacted = [
        {
            **table_info,
            "description": _truncate(table_info.get("description", ""), _DESC_MAX),
            "columns": [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "role": column["role"],
                    # 真实样例值：最多 2 个且截断——name/type/role 才是语义主体
                    "examples": [
                        _truncate(v, _VALUE_MAX)
                        for v in (column.get("examples", []) or [])[:_EXAMPLE_LIMIT]
                    ],
                    "description": _truncate(column.get("description", ""), _DESC_MAX),
                    "alias": [
                        _truncate(a, _ALIAS_MAX) for a in column.get("alias", [])
                    ],
                }
                for column in table_info["columns"]
            ],
        }
        for table_info in table_infos
    ]
    return yaml.dump(compacted, allow_unicode=True, sort_keys=False)


def compact_metric_infos(metric_infos: list[MetricInfoState]) -> str:
    """把候选指标压缩成语义等价的 YAML 文本（口径描述保留截断值）"""
    compacted = [
        {
            **metric_info,
            "description": _truncate(metric_info.get("description", ""), _DESC_MAX),
            "alias": [_truncate(a, _ALIAS_MAX) for a in metric_info.get("alias", [])],
        }
        for metric_info in metric_infos
    ]
    return yaml.dump(compacted, allow_unicode=True, sort_keys=False)
