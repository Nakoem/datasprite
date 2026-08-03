"""
登录鉴权接口路由

提供登录（发 JWT）和当前用户查询接口。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.api.dependencies import get_auth_service, get_current_user
from app.api.schemas.auth_schema import LoginRequest
from app.entities.user import User
from app.services.auth_service import AuthError, AuthService

auth_router = APIRouter()


@auth_router.post("/api/auth/login")
async def login_handler(
    body: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """用户名密码登录，成功返回 JWT access token"""
    try:
        token = await auth_service.login(body.username, body.password)
    except AuthError as exc:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    return {"access_token": token, "token_type": "bearer"}


@auth_router.get("/api/auth/me")
async def me_handler(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """返回当前登录用户信息（token 有效则成功）"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
    }
