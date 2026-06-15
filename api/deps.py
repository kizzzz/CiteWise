"""FastAPI 依赖注入 — 认证守卫"""
from fastapi import Depends, HTTPException, Request

from api.routes.auth import get_current_user


async def require_auth(request: Request) -> dict:
    """依赖注入：要求有效的 JWT token，否则返回 401"""
    user = get_current_user(request)
    if not user or not user.get("user_id"):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def verify_project_owner(project_id: str, user_id: str) -> None:
    """Verify the authenticated user owns the project. Raises 403 if not."""
    from src.core.memory import project_memory
    project = project_memory.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    owner = project.get("user_id", "")
    # Allow legacy projects without user_id (backward compat)
    if owner and owner != user_id:
        raise HTTPException(status_code=403, detail="无权访问该项目")
