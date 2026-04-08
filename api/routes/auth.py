"""用户认证路由 — 注册/登录/获取当前用户"""
import logging
import datetime

from fastapi import APIRouter, HTTPException, Request

from api.schemas import RegisterRequest, LoginRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# JWT config
JWT_SECRET = "citewise_jwt_secret_change_in_production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72


def _hash_password(password: str) -> str:
    """Hash password using bcrypt if available, else simple hash"""
    try:
        from passlib.hash import bcrypt as passlib_bcrypt
        return passlib_bcrypt.hash(password)
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    try:
        from passlib.hash import bcrypt as passlib_bcrypt
        return passlib_bcrypt.verify(password, hashed)
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest() == hashed


def _create_jwt_token(user_id: str, username: str) -> str:
    """Create JWT token"""
    try:
        import jwt
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRE_HOURS),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    except ImportError:
        # Fallback: simple base64 token
        import base64, json
        payload = {"user_id": user_id, "username": username}
        return base64.b64encode(json.dumps(payload).encode()).decode()


def _decode_jwt_token(token: str) -> dict:
    """Decode JWT token"""
    try:
        import jwt
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except ImportError:
        import base64, json
        try:
            return json.loads(base64.b64decode(token).decode())
        except Exception:
            return {}
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
    from src.core.memory import project_memory

    # Check if username exists
    existing = project_memory.get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    password_hash = _hash_password(req.password)
    user_id = project_memory.create_user(req.username, password_hash)

    if not user_id:
        raise HTTPException(status_code=500, detail="注册失败")

    token = _create_jwt_token(user_id, req.username)
    return {
        "token": token,
        "user": {"id": user_id, "username": req.username},
    }


@router.post("/auth/login")
async def login(req: LoginRequest):
    """用户登录"""
    from src.core.memory import project_memory

    user = project_memory.get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not _verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = _create_jwt_token(user["id"], user["username"])
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"]},
    }


@router.get("/auth/me")
async def get_me(request: Request):
    """获取当前用户信息"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user
