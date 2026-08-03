"""
登录鉴权业务服务

封装用户名密码校验、JWT 签发与当前用户查询。
"""

from app.core.log import logger
from app.core.security import create_access_token, hash_password, verify_password
from app.entities.user import User
from app.repositories.mysql.meta.user_repository import UserRepository


class AuthError(Exception):
    """登录失败（用户名或密码错误）"""


class AuthService:
    """登录鉴权的业务编排层"""

    def __init__(self, user_repository: UserRepository):
        self.repo = user_repository

    async def login(self, username: str, password: str) -> str:
        """校验用户名密码，成功返回 JWT token 字符串"""
        user = await self.repo.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            logger.warning("登录失败 | username={}", username)
            raise AuthError("用户名或密码错误")

        token = create_access_token(user.id, user.username)
        logger.info("登录成功 | username={}", username)
        return token

    async def get_user_by_id(self, user_id: int) -> User | None:
        """按用户 ID 查询用户（供 get_current_user 用）"""
        return await self.repo.get_by_id(user_id)

    async def seed_admin(self, username: str, password: str) -> None:
        """users 表为空时创建初始管理员账号（幂等）"""
        if await self.repo.count() > 0:
            return
        await self.repo.create_user(username, hash_password(password))
        logger.info("已 seed 初始管理员账号 | username={}", username)
