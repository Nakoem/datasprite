# Code Review Report — #16 API 限流（双层令牌桶）

> 审查日期：2026-07-18
> 审查范围：4 个变更文件（1 新增 + 3 修改）
> 触发场景：TODO #16 API 限流实现完成后的例行审查

---

## 审查文件

| # | 文件 | 改动量 | 结果 |
|:--|:---|:--|:--:|
| 1 | `app/core/rate_limiter.py` | 新增 ~150 行 | ⚠️ 1 个问题 |
| 2 | `main.py` | +6 行 | ⚠️ 1 个问题 |
| 3 | `app/conf/app_config.py` | +20 行 | ✅ 通过 |
| 4 | `conf/app_config.yaml` | +22 行 | ⚠️ 1 个问题 |

---

## 发现的问题

### 1. MEDIUM — 限流中间件注册在监控之外，429 逃出指标视野

**文件：** `main.py`

限流中间件初版注册在 `Instrumentator` / `FastAPIInstrumentor` **之后**。
Starlette 中间件"后注册 = 更外层"，导致限流器包在监控外面——被拒的 429
请求不经过 Prometheus/OTel 中间件，攻击洪水在 Grafana 上完全不可见，
与 #7 建设的监控体系目标冲突。

**修复：** 把 `app.middleware("http")(rate_limit_middleware)` 移到
Instrumentator 之前（成为最内层）。429 计入指标和链路，同时仍在路由
处理前拦截，LLM 链路照样受保护。

**验证：** 7 连发打 `/api/query` 后，`/metrics` 出现
`http_requests_total{handler="/api/query",status="4xx"} 7.0` ✅

### 2. LOW — `refill_rate: 0` 会让限流静默失效

**文件：** `app/core/rate_limiter.py`

Lua 中 `capacity / rate` 除零得 inf → `PEXPIRE` 报错 → 触发 fail-open
兜底放行。误配置后限流形同虚设，只留一条 warning 日志，很难察觉。

**修复：** 新增 `_validate_config()`，模块导入时校验
`capacity >= 1 且 refill_rate > 0`，配错直接拒绝启动（fail-fast）。

**验证：** 手动注入 `refill_rate = 0` 后导入模块，成功抛出 ValueError ✅

### 3. LOW — `/redoc` 未加入豁免路径

**文件：** `conf/app_config.yaml`

FastAPI 默认还提供 /redoc 文档页，初版豁免表只有 /docs。已补入。

### 4. HIGH — Redis"假死"时 fail-open 失效，限流器吊死全服务（补测发现）

**文件：** `app/core/rate_limiter.py`、`app/clients/redis_client_manager.py`

补测 fail-open 场景（`docker stop redis` 后打接口）时发现：前 2 发正常放行，
**第 3 发起全服务永久挂起**。原因是 Docker Desktop 停容器后代理端口仍在监听，
连接能建立但永远无响应（"假死"而非"拒绝连接"）；Redis 客户端未配 socket
超时，`await` 永久阻塞——fail-open 只防住了快速失败，防不住假死，
限流器反而成了服务杀手。

**修复（双层）：**
1. `_acquire_token` 套 `asyncio.wait_for(timeout=1.0)` 硬超时，超时走 fail-open
2. `redis_client_manager` 补 `socket_connect_timeout=1, socket_timeout=1`
   ——同时救了 #5 缓存（`get_cached_embedding` 等有同款隐患，假死会吊死整条问数链路）

**验证：** 停 Redis 后连打 8 发全部 200、各 ~1.0s 精确兜底；恢复 Redis 后
限流立即回归（顺带验证 Redis 重启丢脚本缓存后 NOSCRIPT 自动回退重注册）✅

### 5. MEDIUM — logger 导入错误，限流日志静默全丢（还炸出 #15 遗留地雷）

**文件：** `app/core/rate_limiter.py`、`main.py`

验证日志留痕时发现 app.log 里一条限流日志都没有。`log.py` 用
`logger.patch()` 生成带 request_id 注入的**新实例**，业务代码必须
`from app.core.log import logger`；而 rate_limiter 写的是
`from loguru import logger`（裸实例，extra 为空），格式模板取
`{extra[request_id]}` 直接 KeyError，sink 崩溃、日志全丢。

**连带发现：** `main.py` 也是 `from loguru import logger`——意味着
**#15 全局异常处理器的 error 日志从上线起就一直静默崩溃**，从未落盘。

**修复：** 两文件均改为 `from app.core.log import logger`。

**验证：** app.log 出现"限流检查失败"×3、"限流触发"×2，均带完整
request_id UUID；控制台 Loguru 报错 0 条 ✅

### 测试过程插曲 — Windows 下 TaskStop 杀不死 uvicorn 子进程

复测时发现旧服务进程残留占用 8000 端口（新服务 Errno 10048 绑定失败但
curl 仍有响应，响应的是跑旧代码的僵尸），导致一轮验证结果失真。
用 `netstat -ano` 定位 + `taskkill //F //T` 清理后重测。
**经验：起后台服务验证前，先确认端口由本轮进程持有。**

---

## 五项必检结论

| 检查项 | 结论 |
|:--|:--|
| 改动范围是否超出指令 | ✅ 6 文件（4 原始 + 修复涉及 redis_client_manager.py，main.py logger 属同类缺陷顺修） |
| 是否改了不该改的文件 | ✅ 无 .env / 缓存文件混入 |
| 接口和数据结构兼容性 | ✅ AppConfig 新增字段随 YAML 同步提交；中间件签名标准 |
| 异常状态处理 | ✅ Redis 故障 fail-open；Lua 原子扣减；拒绝路径不写状态避免漂移 |
| 重复逻辑 | ✅ 补桶逻辑仅存在于 Lua `refill()` 一处 |

## 设计要点备查

- **原子性**：取令牌/补令牌在单个 Lua 脚本内完成，并发下不会超发
- **双桶同扣**：先检查两桶都有令牌再一起扣，避免"IP 桶扣了全局桶拒绝"浪费令牌
- **惰性补充**：无定时器，按时间差一次性补算；拒绝时不写状态，下次按旧时间戳重算结果一致
- **TTL 自清理**：空闲桶按"补满耗时 ×2"自动过期，Redis 不积垃圾键
- **中间件顺序**（外→内）：request_id → OTel → Prometheus → 限流 → 路由

## 实测记录

| 场景 | 预期 | 实测 |
|:--|:--|:--:|
| /health 连打 40 次 | 全部 200（豁免） | ✅ |
| 普通档并发 50 发 | 部分 429 | ✅ 45×200 + 5×429 |
| 收紧档 7 连发 | 5 放行后 429 | ✅ 422×5 + 429×2 |
| Retry-After 头 | 2 秒（1÷0.5） | ✅ |
| 打空桶后等 2s | 放行 1 个后再 429 | ✅ 422 → 429 |
| 串行 curl 打普通档 | 打不出 429（~7req/s < 回补 10/s） | ✅ 符合设计 |
| 停 Redis（假死）连打 8 发 | 全 200、各 ~1s 硬超时兜底 | ✅ |
| Redis 恢复后 | 限流即刻回归 + 脚本重注册 | ✅ |
| fail-open / 429 日志落盘 | app.log 带 request_id | ✅ 3+2 条 |
| 坏配置 refill_rate=0 | 拒绝启动 | ✅ ValueError |

## 结论

初审 MEDIUM ×1、LOW ×2；补测又揪出 HIGH ×1（Redis 假死吊死服务）、
MEDIUM ×1（logger 导入错误连带 #15 遗留）。**五项全部修复并复测通过，准予提交。**

> 教训：fail-open 这类"故障兜底"逻辑，必须真把依赖弄挂了测一遍——
> 代码审查只能确认"写了兜底"，确认不了"兜得住"。
