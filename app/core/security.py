"""
登录安全工具

提供密码哈希（bcrypt）与 JWT 签发/校验（pyjwt）两个能力，
供 AuthService 和 get_current_user 依赖复用。本模块不依赖 FastAPI，
抛出的异常由调用方决定如何转成 HTTP 响应。
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.conf.app_config import app_config

_jwt_config = app_config.jwt


def hash_password(password: str) -> str:
    """生成 bcrypt 密码哈希（返回可存库的字符串）"""
    # bcrypt 5.x 对超过 72 字节的密码会抛错而非静默截断，这里防御性截断到安全长度
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    try:
        pw_bytes = password.encode("utf-8")[:72]
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # 库里存的不是合法 bcrypt 哈希（如手工写入的坏数据），按不匹配处理
        return False


def create_access_token(user_id: int, username: str) -> str:
    """签发 JWT access token（HS256）"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=_jwt_config.access_token_expire_minutes),
    }
    return jwt.encode(payload, _jwt_config.secret, algorithm=_jwt_config.algorithm)


def decode_token(token: str) -> dict:
    """校验并解析 JWT，返回 payload；无效/过期抛 jwt.InvalidTokenError"""
    return jwt.decode(
        token,
        _jwt_config.secret,
        algorithms=[_jwt_config.algorithm],
    )
