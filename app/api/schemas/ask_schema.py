"""
/ask 同步接口请求/响应体定义

供外部系统（Dify / 飞书 / 钉钉等）通过 HTTP JSON 调用 DataSprite 问数能力，
一次请求返回 SQL + 数据 + AI 摘要，不需要消费 SSE 流。
"""

from pydantic import BaseModel


class AskRequest(BaseModel):
    """外部系统传入的问数请求"""

    query: str


class AskResponse(BaseModel):
    """同步返回的问数结果"""

    sql: str | None = None
    data: list[dict] | None = None
    summary: str | None = None
    metric_definitions: list[dict] | None = None
    column_sources: list[dict] | None = None
    error: str | None = None
    chart_image_base64: str | None = None  # PNG 图表 base64，供飞书等渠道展示
