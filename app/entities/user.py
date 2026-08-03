"""
用户领域实体

纯数据对象，不依赖 ORM 框架，用于在各层之间传递用户数据。
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """一个登录账号"""

    id: int | None = None
    username: str = ""
    email: str | None = None
    password_hash: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
