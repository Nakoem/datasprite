"""
API 限流中间件（双层令牌桶）

按客户端 IP 和全局各维护一个令牌桶，桶状态存 Redis，
取令牌 / 补令牌通过 Lua 脚本一次往返原子完成，并发下不会超发。
/api/query 背后是多次 LLM 调用，单独走更小的桶保护成本；
Redis 不可用时直接放行（fail-open），限流器故障不影响主业务。
"""

import asyncio
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from app.clients.redis_client_manager import redis_client_manager
from app.conf.app_config import app_config
from app.core.log import logger

# 命中该前缀的请求走收紧档令牌桶（LLM 链路昂贵）
_QUERY_PATH_PREFIX = "/api/query"

# 限流检查硬超时（秒）：Redis 假死（连接建立但不响应，如 Docker 代理端口）
# 不会快速抛错，没有这层兜底 await 会永久挂起，限流器反把全服务吊死
_ACQUIRE_TIMEOUT = 1.0

# 双层令牌桶 Lua 脚本：KEYS[1]=IP桶 KEYS[2]=全局桶
# ARGV = 当前时间戳, IP桶容量, IP桶速率, 全局桶容量, 全局桶速率
# 返回 {是否放行(1/0), 建议重试秒数}
_TOKEN_BUCKET_LUA = """
local now = tonumber(ARGV[1])

-- 惰性补充：不用定时器，按距上次请求的时间差一次性补算令牌
local function refill(key, capacity, rate)
  local data = redis.call('HMGET', key, 'tokens', 'ts')
  local tokens = tonumber(data[1])
  local ts = tonumber(data[2])
  if tokens == nil or ts == nil then
    return capacity  -- 新桶默认装满
  end
  return math.min(capacity, tokens + math.max(0, now - ts) * rate)
end

local ip_cap = tonumber(ARGV[2])
local ip_rate = tonumber(ARGV[3])
local g_cap = tonumber(ARGV[4])
local g_rate = tonumber(ARGV[5])

local ip_tokens = refill(KEYS[1], ip_cap, ip_rate)
local g_tokens = refill(KEYS[2], g_cap, g_rate)

-- 两个桶都有令牌才放行，并同时扣减（避免只扣一边白白浪费令牌）
if ip_tokens >= 1 and g_tokens >= 1 then
  redis.call('HSET', KEYS[1], 'tokens', ip_tokens - 1, 'ts', now)
  redis.call('HSET', KEYS[2], 'tokens', g_tokens - 1, 'ts', now)
  -- 空闲桶自动清理：TTL 取补满全桶所需时间的 2 倍
  redis.call('PEXPIRE', KEYS[1], math.ceil(ip_cap / ip_rate * 2000))
  redis.call('PEXPIRE', KEYS[2], math.ceil(g_cap / g_rate * 2000))
  return {1, 0}
end

-- 拒绝时不写状态：令牌数下次按旧时间戳重算，结果一致
local wait = 0
if ip_tokens < 1 then wait = (1 - ip_tokens) / ip_rate end
if g_tokens < 1 then wait = math.max(wait, (1 - g_tokens) / g_rate) end
return {0, math.max(1, math.ceil(wait))}
"""

# register_script 结果缓存，避免每次请求重复注册
_bucket_script = None


def _validate_config() -> None:
    """启动时校验限流参数，配错直接拒绝启动

    refill_rate <= 0 会让 Lua 里的 capacity / rate 除零得 inf，
    进而 PEXPIRE 报错触发 fail-open，限流静默失效——fail-fast 好过带病运行。
    """
    cfg = app_config.rate_limit
    if not cfg.enable:
        return
    buckets = (
        ("per_ip", cfg.per_ip),
        ("per_ip_query", cfg.per_ip_query),
        ("global_bucket", cfg.global_bucket),
    )
    for name, bucket in buckets:
        if bucket.capacity < 1 or bucket.refill_rate <= 0:
            raise ValueError(
                f"rate_limit.{name} 配置非法："
                f"capacity 需 >= 1（当前 {bucket.capacity}），"
                f"refill_rate 需 > 0（当前 {bucket.refill_rate}）"
            )


_validate_config()


async def _acquire_token(client, keys: list[str], args: list) -> tuple[int, int]:
    """执行令牌桶 Lua 脚本，返回 (是否放行, 建议重试秒数)

    整体套硬超时：超时抛 TimeoutError，由调用方按 fail-open 放行。
    """
    global _bucket_script
    if _bucket_script is None:
        _bucket_script = client.register_script(_TOKEN_BUCKET_LUA)
    allowed, retry_after = await asyncio.wait_for(
        _bucket_script(keys=keys, args=args, client=client),
        timeout=_ACQUIRE_TIMEOUT,
    )
    return allowed, retry_after


async def rate_limit_middleware(request: Request, call_next):
    """令牌桶限流中间件：超限返回 429 + Retry-After"""
    cfg = app_config.rate_limit
    path = request.url.path
    if not cfg.enable or any(path.startswith(p) for p in cfg.exempt_paths):
        return await call_next(request)

    client = redis_client_manager.client
    if client is None:
        return await call_next(request)

    # 注意：部署在反向代理后面时 request.client.host 拿到的是代理 IP，
    # 需改读 X-Forwarded-For；当前直连 uvicorn，无此问题
    ip = request.client.host if request.client else "unknown"
    is_query = path.startswith(_QUERY_PATH_PREFIX)
    bucket = cfg.per_ip_query if is_query else cfg.per_ip
    tier = "query" if is_query else "common"

    try:
        allowed, retry_after = await _acquire_token(
            client,
            keys=[f"ratelimit:{tier}:{ip}", "ratelimit:global"],
            args=[
                time.time(),
                bucket.capacity,
                bucket.refill_rate,
                cfg.global_bucket.capacity,
                cfg.global_bucket.refill_rate,
            ],
        )
    except Exception:
        # fail-open：限流器自身故障不能拖垮主业务
        logger.opt(exception=True).warning("限流检查失败，本次请求直接放行")
        return await call_next(request)

    if not allowed:
        logger.warning(
            "限流触发 | ip={} path={} retry_after={}s", ip, path, retry_after
        )
        return JSONResponse(
            status_code=429,
            content={"detail": f"请求过于频繁，请 {retry_after} 秒后再试"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
