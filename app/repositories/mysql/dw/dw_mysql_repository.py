"""
数仓 MySQL 仓储

这一层对应文档里的 DW Repository，职责是到真实数仓中补齐配置文件里
没有显式维护的信息，例如字段类型和字段示例值。Service 层只关心
"需要哪些信息"，具体怎样查数仓由仓储层统一封装
SQL 生成闭环中的数据库环境读取 SQL 校验和最终查询执行也集中放在这里
"""

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 合法的 MySQL 未加反引号标识符：字母/数字/下划线/中文，不含空格和特殊字符
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_一-鿿]+$")

# 危险 SQL 关键字（仅允许 SELECT / EXPLAIN / SHOW / DESCRIBE / WITH 等只读语句）
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|REPLACE"
    r"|GRANT|REVOKE|LOAD|FLUSH|RENAME|LOCK|UNLOCK|KILL"
    r"|SET\s+(?!TRANSACTION|NAMES|SESSION\s+TRANSACTION))\b",
    re.IGNORECASE,
)

# 最大返回行数
_MAX_ROWS = 1000

# 查询超时（秒）
_QUERY_TIMEOUT = 30


def _validate_identifier(name: str, label: str = "标识符") -> str:
    """校验并返回安全的 MySQL 标识符（用反引号包裹）"""
    stripped = name.strip().strip("`")
    if not _IDENTIFIER_RE.match(stripped):
        raise ValueError(f"非法{label}：{name}")
    return f"`{stripped}`"


def _validate_readonly(sql: str) -> None:
    """检查 SQL 是否包含危险写操作关键字"""
    if _DANGEROUS_KEYWORDS.search(sql):
        raise ValueError("禁止执行写操作或危险语句")


def _add_row_limit(sql: str) -> str:
    """自动追加行数限制，防止全表扫描撑爆内存"""
    stripped = sql.rstrip(";").rstrip()
    if re.search(r"\bLIMIT\s+\d+", stripped, re.IGNORECASE):
        return stripped
    return f"{stripped} LIMIT {_MAX_ROWS}"


class DWMySQLRepository:
    """负责查询数仓真实表结构和字段样例值"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_column_types(self, table_name: str) -> dict[str, str]:
        """查询整张表的字段类型，作为 ColumnInfo.type 的真实来源"""
        safe_table = _validate_identifier(table_name, "表名")
        sql = f"SHOW COLUMNS FROM {safe_table}"
        result = await self.session.execute(text(sql))
        result_dict = result.mappings().fetchall()
        return {row["Field"]: row["Type"] for row in result_dict}

    async def get_column_values(
        self, table_name: str, column_name: str, limit: int = 10
    ) -> list:
        """抽样查询字段示例值，供元数据入库和后续检索链路复用"""
        safe_table = _validate_identifier(table_name, "表名")
        safe_col = _validate_identifier(column_name, "列名")
        sql = f"SELECT DISTINCT {safe_col} FROM {safe_table} LIMIT {int(limit)}"
        result = await self.session.execute(text(sql))
        return [row[0] for row in result.fetchall()]

    async def get_db_info(self):
        """读取当前数仓数据库的方言和版本，供 SQL 生成提示词使用"""
        sql = "SELECT VERSION()"
        result = await self.session.execute(text(sql))
        version = result.scalar()

        # dialect 来自 SQLAlchemy 当前绑定的数据库方言，例如 mysql
        dialect = self.session.bind.dialect.name
        return {"dialect": dialect, "version": version}

    async def validate(self, sql: str):
        """用 EXPLAIN 让数据库提前解析 SQL，发现语法 表名 字段名等错误"""
        _validate_readonly(sql)
        sql = f"EXPLAIN {sql}"
        await self.session.execute(text(sql))

    async def run(self, sql: str) -> list[dict]:
        """执行最终 SQL，自动安全检查 + 行数限制 + 超时控制"""
        _validate_readonly(sql)
        sql = _add_row_limit(sql)

        # 设置查询超时（MySQL 8.0+），单位毫秒
        await self.session.execute(
            text(f"SET SESSION MAX_EXECUTION_TIME={_QUERY_TIMEOUT * 1000}")
        )

        result = await self.session.execute(text(sql))
        return [dict(row) for row in result.mappings().fetchall()]
