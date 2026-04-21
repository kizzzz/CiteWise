"""FastAPI 依赖注入 — 认证守卫"""
from fastapi import Depends, HTTPException, Request

from api.routes.auth import get_current_user


async def require_auth(request: Request) -> dict:
    """依赖注入：要求有效的 JWT token，否则返回 401"""
    user = get_current_user(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user
