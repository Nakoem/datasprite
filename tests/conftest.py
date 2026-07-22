"""
DataSprite 测试共享 fixtures

提供 FakeLLM、Fake 仓储、运行时助手和缓存 mock，让所有节点测试
不需要连接任何真实外部服务。
"""

from unittest.mock import MagicMock

import pytest

# ═══════════════════════════════════════════════════════════════════
# FakeLLM — 模拟 LLM，callable + ainvoke/invoke 双接口
# ═══════════════════════════════════════════════════════════════════


class FakeLLM:
    """模拟 LLM 调用。

    两种使用模式：
    - set_response(content): 所有调用返回同一个字符串
    - set_sequence([...]): 按队列顺序返回，队列用完后返回 "{}"

    同时支持 __call__（LangChain coerce_to_runnable 包装为
    RunnableLambda）和 ainvoke/invoke。
    返回纯字符串，StrOutputParser / JsonOutputParser 正常消费。
    """

    def __init__(self) -> None:
        self._response: str = ""
        self._queue: list[str] = []
        self.call_count: int = 0
        self.last_input: object = None

    def set_response(self, content: str) -> None:
        self._response = content
        self._queue = []

    def set_sequence(self, responses: list[str]) -> None:
        self._queue = list(responses)

    def __call__(self, input, config=None, **kwargs):
        self.call_count += 1
        self.last_input = input
        if self._queue:
            return self._queue.pop(0)
        return self._response

    async def ainvoke(self, input, config=None, **kwargs):
        return self.__call__(input, config=config, **kwargs)

    def invoke(self, input, config=None, **kwargs):
        return self.__call__(input, config=config, **kwargs)


@pytest.fixture
def fake_llm() -> FakeLLM:
    """创建一个 FakeLLM 实例。需要 LLM 的测试文件应自行 patch
    对应节点模块的 llm 引用。"""
    return FakeLLM()


# ═══════════════════════════════════════════════════════════════════
# Fake 仓储
# ═══════════════════════════════════════════════════════════════════


class FakeDWMySQLRepository:
    """模拟数仓 MySQL 仓储，可用于控制 validate / run 的行为。"""

    def __init__(self, raise_on_validate=None, run_results=None, db_info=None):
        self.raise_on_validate = raise_on_validate  # Exception 或 list[Exception|None]
        self.run_results = run_results or []
        self.db_info = db_info or {"dialect": "mysql", "version": "8.0.0"}
        self.validated_sqls: list[str] = []
        self.run_sqls: list[str] = []
        self._validate_call_count = 0

    async def validate(self, sql: str):
        self.validated_sqls.append(sql)
        self._validate_call_count += 1
        err = self.raise_on_validate
        if isinstance(err, list):
            idx = self._validate_call_count - 1
            if idx < len(err) and err[idx] is not None:
                raise err[idx]
        elif err is not None:
            raise err

    async def run(self, sql: str) -> list[dict]:
        self.run_sqls.append(sql)
        return list(self.run_results)

    async def get_db_info(self):
        return dict(self.db_info)

    async def get_column_types(self, table_name: str) -> dict[str, str]:
        return {}

    async def get_column_values(
        self, table_name: str, column_name: str, limit: int = 10
    ) -> list:
        return []


class FakeMetaMySQLRepository:
    """内存中的元数据仓储，预填充表/字段/主键供节点查询。"""

    def __init__(self):
        self._columns: dict[str, object] = {}
        self._tables: dict[str, object] = {}
        self._key_columns: dict[str, list[object]] = {}

    def add_column(self, column_info):
        self._columns[column_info.id] = column_info

    def add_table(self, table_info):
        self._tables[table_info.id] = table_info

    def set_key_columns(self, table_id: str, columns: list):
        self._key_columns[table_id] = columns

    async def get_column_info_by_id(self, id: str):
        return self._columns.get(id)

    async def get_table_info_by_id(self, id: str):
        return self._tables.get(id)

    async def get_key_columns_by_table_id(self, table_id: str):
        return list(self._key_columns.get(table_id, []))


class FakeColumnQdrantRepository:
    def __init__(self):
        self._results: list[object] = []

    def set_search_results(self, results: list):
        self._results = list(results)

    async def search(self, embedding: list[float]) -> list[object]:
        return list(self._results)


class FakeMetricQdrantRepository:
    def __init__(self):
        self._results: list[object] = []

    def set_search_results(self, results: list):
        self._results = list(results)

    async def search(self, embedding: list[float]) -> list[object]:
        return list(self._results)


class FakeValueESRepository:
    def __init__(self):
        self._results: list[object] = []

    def set_search_results(self, results: list):
        self._results = list(results)

    async def search(self, keyword: str) -> list[object]:
        return list(self._results)


class FakeEmbeddingClient:
    """返回零向量，记录所有 aembed_query 调用。"""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.calls: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * self.dim


# ═══════════════════════════════════════════════════════════════════
# 运行时助手
# ═══════════════════════════════════════════════════════════════════


class _FakeStreamWriter:
    """收集 writer(event) 调用，供断言检查进度事件。"""

    def __init__(self):
        self.events: list[dict] = []

    def __call__(self, event: dict):
        self.events.append(event)

    def steps(self) -> list[str]:
        return [e.get("step", "") for e in self.events]

    def last_status(self) -> str | None:
        return self.events[-1].get("status") if self.events else None


def make_runtime(context: dict) -> MagicMock:
    """构造一个带 context 和 stream_writer 的 mock Runtime。"""
    writer = _FakeStreamWriter()
    runtime = MagicMock()
    runtime.context = context
    runtime.stream_writer = writer
    return runtime


# ═══════════════════════════════════════════════════════════════════
# 缓存 mock（自动应用，防止测试意外访问 Redis）
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def patch_cache(mocker):
    """mock 所有 Redis 缓存函数，返回 None / 静默成功。"""
    mocker.patch("app.core.cache.get_cached_embedding", return_value=None)
    mocker.patch("app.core.cache.cache_embedding", return_value=None)
    mocker.patch("app.core.cache.get_cached_query_result", return_value=None)
    mocker.patch("app.core.cache.cache_query_result", return_value=None)
