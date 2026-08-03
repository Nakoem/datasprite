"""
登录鉴权请求/响应模型
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """登录请求体"""

    username: str
    password: str


class TokenResponse(BaseModel):
    """登录成功返回的 JWT"""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """当前登录用户信息"""

    id: int
    username: str
    email: str | None = None
