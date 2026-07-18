"""
Redis 缓存工具

提供 Embedding 向量和 SQL 查询结果的缓存读写能力。
缓存命中时直接返回，避免重复调用 Embedding 服务或重复执行 SQL。

所有操作均为 fail-open：缓存只是加速器，Redis 故障时读当未命中、
写当没发生，绝不让缓存问题打断问数主链路。
"""

import functools
import hashlib
import json
import time

from app.clients.redis_client_manager import redis_client_manager
from app.core.log import logger

# Embedding 向量缓存 TTL（7 天，向量模型不变则结果不变）
_EMBEDDING_TTL = 7 * 24 * 3600

# 查询结果缓存 TTL（1 小时，数据可能更新）
_QUERY_RESULT_TTL = 3600

# 熔断冷却期（秒）：一次失败后这段时间内直接跳过 Redis，
# 避免一次问数十几个缓存操作挨个傻等超时，把降级模式拖成龟速
_CIRCUIT_COOLDOWN = 30

# 熔断截止时间戳；0 表示熔断关闭（Redis 正常）。
# 并发下的读写竞态无害：最坏情况多探测一两次 Redis
_circuit_open_until = 0.0


def _redis_safe(func):
    """缓存操作 fail-open + 熔断装饰器

    Redis 抽风（连接拒绝 / 超时 / 假死被 socket_timeout 掐断）时：
    读操作返回 None 等价于未命中，调用方自然回退到真实计算；
    写操作静默跳过，只留一条 warning 供排查。
    失败后熔断 30 秒——期间所有缓存操作直接跳过不碰 Redis，
    冷却结束后放一次探测，成功则自动恢复。
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        global _circuit_open_until
        if time.monotonic() < _circuit_open_until:
            return None
        try:
            result = await func(*args, **kwargs)
            _circuit_open_until = 0.0
            return result
        except Exception:
            _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN
            logger.opt(exception=True).warning(
                "Redis 缓存操作失败，熔断 {} 秒后再探测：{}",
                _CIRCUIT_COOLDOWN,
                func.__name__,
            )
            return None

    return wrapper


def _make_key(prefix: str, text: str) -> str:
    """生成带前缀的 SHA256 缓存键"""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


@_redis_safe
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


@_redis_safe
async def cache_embedding(keyword: str, vector: list[float]) -> None:
    """缓存 Embedding 向量"""
    client = redis_client_manager.client
    if client is None:
        return
    key = _make_key("emb", keyword)
    await client.setex(key, _EMBEDDING_TTL, json.dumps(vector))


@_redis_safe
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


@_redis_safe
async def cache_query_result(sql: str, result: list[dict]) -> None:
    """缓存 SQL 查询结果"""
    client = redis_client_manager.client
    if client is None:
        return
    key = _make_key("sql", sql)
    await client.setex(key, _QUERY_RESULT_TTL, json.dumps(result, default=str))
