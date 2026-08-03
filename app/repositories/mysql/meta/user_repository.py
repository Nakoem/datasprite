"""
用户仓储

负责 users 表的读写操作，面向业务实体而非 ORM 模型。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.user import User


def _row_to_user(row) -> User:
    """将 raw SQL 行映射为 User 实体"""
    return User(
        id=row["id"],
        username=row["username"],
        email=row.get("email"),
        password_hash=row["password_hash"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class UserRepository:
    """用户数据访问层"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, username: str, password_hash: str, email: str | None = None) -> User:
        """创建新用户"""
        sql = """
            INSERT INTO users (username, password_hash, email)
            VALUES (:username, :password_hash, :email)
        """
        result = await self.session.execute(
            text(sql),
            {"username": username, "password_hash": password_hash, "email": email},
        )
        await self.session.commit()
        return await self.get_by_id(result.lastrowid)

    async def get_by_username(self, username: str) -> User | None:
        """按用户名查询用户"""
        result = await self.session.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": username},
        )
        row = result.mappings().first()
        return _row_to_user(row) if row else None

    async def get_by_id(self, user_id: int) -> User | None:
        """按 ID 查询用户"""
        result = await self.session.execute(
            text("SELECT * FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        return _row_to_user(row) if row else None

    async def count(self) -> int:
        """统计用户总数（用于判断是否需要 seed 管理员）"""
        result = await self.session.execute(text("SELECT COUNT(*) FROM users"))
        return result.scalar() or 0
