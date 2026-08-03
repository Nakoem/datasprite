"""
用户 ORM 模型

定义元数据库中 users 表对应的 ORM 模型，用于登录鉴权的账号持久化。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserMySQL(Base):
    """用户表 — 一个登录账号对应一条记录"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="用户自增 ID"
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="登录用户名"
    )
    email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="邮箱"
    )
    password_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="bcrypt 密码哈希"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="最后更新时间"
    )
