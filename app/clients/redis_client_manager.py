"""
Redis 客户端管理器

统一创建和管理 Redis 异步客户端，用于缓存 Embedding 向量与热点查询结果，
减少重复计算和 LLM 调用开销。
"""

from redis.asyncio import Redis

from app.conf.app_config import app_config


class RedisClientManager:
    """管理 Redis 客户端的初始化与关闭"""

    def __init__(self):
        self.client: Redis | None = None

    def init(self):
        """初始化 Redis 异步客户端

        socket 超时必须显式设置：Redis"假死"（端口可连但不响应，
        如 Docker 代理端口在容器停止后仍监听）时，默认无超时会让
        所有 await 永久挂起，缓存和限流都会被吊死。
        """
        self.client = Redis(
            host=app_config.redis.host,
            port=app_config.redis.port,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

    async def close(self):
        """关闭 Redis 客户端连接"""
        if self.client:
            await self.client.aclose()


# 全局管理器实例
redis_client_manager = RedisClientManager()
