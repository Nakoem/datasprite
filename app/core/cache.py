"""
Redis 缓存工具

提供 Embedding 向量和 SQL 查询结果的缓存读写能力。
缓存命中时直接返回，避免重复调用 Embedding 服务或重复执行 SQL。
"""

import hashlib
import json
from typing import Any

from app.clients.redis_client_manager import redis_client_manager

# Embedding 向量缓存 TTL（7 天，向量模型不变则结果不变）
_EMBEDDING_TTL = 7 * 24 * 3600

# 查询结果缓存 TTL（1 小时，数据可能更新）
_QUERY_RESULT_TTL = 3600


def _make_key(prefix: str, text: str) -> str:
    """生成带前缀的 SHA256 缓存键"""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


async def get_cached_embedding(keyword: str) -> list[float] | None:
    """读取缓存的 Embedding 向量，未命中返回 None"""
    client = redis_client_manager.client
    if client is None:
        return None
    key = _make_key("emb", keyword)
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_embedding(keyword: str, vector: list[float]) -> None:
    """缓存 Embedding 向量"""
    client = redis_client_manager.client
    if client is None:
        return
    key = _make_key("emb", keyword)
    await client.setex(key, _EMBEDDING_TTL, json.dumps(vector))


async def get_cached_query_result(sql: str) -> list[dict] | None:
    """读取缓存的 SQL 查询结果，未命中返回 None"""
    client = redis_client_manager.client
    if client is None:
        return None
    key = _make_key("sql", sql)
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_query_result(sql: str, result: list[dict]) -> None:
    """缓存 SQL 查询结果"""
    client = redis_client_manager.client
    if client is None:
        return
    key = _make_key("sql", sql)
    await client.setex(key, _QUERY_RESULT_TTL, json.dumps(result, default=str))
