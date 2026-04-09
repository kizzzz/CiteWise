"""用户认证路由 — 注册/登录/获取当前用户

纯 Python 实现，无 C 扩展依赖（bcrypt/passlib 已移除）。
"""
import hashlib
import hmac
import base64
import json
import logging
import os
import datetime

from fastapi import APIRouter, HTTPException, Request

from api.schemas import RegisterRequest, LoginRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# JWT config
JWT_SECRET = os.getenv("JWT_SECRET", "citewise_jwt_secret_change_in_production")
JWT_EXPIRE_HOURS = 72

# Password hashing — PBKDF2 with per-user salt, pure Python
_ITERATIONS = 200_000


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """PBKDF2-HMAC-SHA256 with per-user random salt — pure Python"""
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()
    return h, salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify password against stored hash and salt"""
    h, _ = _hash_password(password, salt)
    return hmac.compare_digest(h, stored_hash)


def _create_jwt_token(user_id: str, username: str) -> str:
    """Create JWT token — pure Python base64, no PyJWT dependency"""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    # Encode payload
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    # Sign with HMAC
    signature = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def _decode_jwt_token(token: str) -> dict:
    """Decode JWT token"""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return {}
        payload_b64, signature = parts
        # Verify signature
        expected_sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return {}
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Check expiry
        if payload.get("exp", 0) < datetime.datetime.now(datetime.timezone.utc).timestamp():
            return {}
        return payload
    except Exception:
        return {}


def get_current_user(request: Request) -> dict:
    """Extract current user from Authorization header"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return {}
    token = auth_header[7:]
    payload = _decode_jwt_token(token)
    if not payload or not payload.get("user_id"):
        return {}
    return payload


@router.post("/auth/register")
async def register(req: RegisterRequest):
    """用户注册"""
    try:
        from src.core.memory import project_memory

        existing = project_memory.get_user_by_username(req.username)
        if existing:
            raise HTTPException(status_code=409, detail="用户名已存在")

        password_hash, password_salt = _hash_password(req.password)
        user_id = project_memory.create_user(req.username, password_hash, password_salt)

        if not user_id:
            raise HTTPException(status_code=500, detail="注册失败")

        token = _create_jwt_token(user_id, req.username)
        return {
            "token": token,
            "user": {"id": user_id, "username": req.username},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")


@router.post("/auth/login")
async def login(req: LoginRequest):
    """用户登录"""
    try:
        from src.core.memory import project_memory

        user = project_memory.get_user_by_username(req.username)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not _verify_password(req.password, user["password_hash"], user.get("password_salt", "")):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = _create_jwt_token(user["id"], user["username"])
        return {
            "token": token,
            "user": {"id": user["id"], "username": user["username"]},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")


@router.get("/auth/me")
async def get_me(request: Request):
    """获取当前用户信息"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user
