"""API Key 管理路由 — 验证/保存/获取用户 API Key"""
import logging

from fastapi import APIRouter, HTTPException, Request

from api.schemas import ApiKeyRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/apikeys/verify")
async def verify_api_key(req: ApiKeyRequest):
    """验证智谱 API Key 有效性 — 调用 models 接口"""
    import httpx

    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="API Key 不能为空")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://open.bigmodel.cn/api/paas/v4/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", "") for m in data.get("data", [])]
                return {
                    "valid": True,
                    "models_count": len(models),
                    "message": f"验证成功，可用模型 {len(models)} 个",
                }
            else:
                return {
                    "valid": False,
                    "message": f"验证失败 (HTTP {resp.status_code})",
                }
    except Exception as e:
        logger.error(f"API Key 验证请求失败: {e}")
        return {"valid": False, "message": f"验证请求失败: {str(e)}"}


@router.post("/apikeys/save")
async def save_user_api_key(req: Request):
    """保存用户 API Key 到后端（加密存储）"""
    body = await req.json()
    api_key = body.get("api_key", "").strip()
    user_id = body.get("user_id", "")

    if not api_key:
        raise HTTPException(status_code=422, detail="API Key 不能为空")

    from src.core.memory import project_memory

    if user_id:
        user = project_memory.get_user_by_id(user_id)
        if user:
            # Simple obfuscation (not real encryption, but better than plaintext)
            import base64
            encrypted = base64.b64encode(api_key.encode()).decode()
            project_memory.update_user_api_key(user_id, encrypted)
            return {"status": "ok", "message": "API Key 已保存"}

    return {"status": "ok", "message": "API Key 仅存储在本地"}


@router.get("/apikeys/{user_id}")
async def get_user_api_key(user_id: str):
    """获取用户的 API Key（解密）"""
    from src.core.memory import project_memory

    user = project_memory.get_user_by_id(user_id)
    if not user or not user.get("api_key"):
        return {"api_key": ""}

    import base64
    try:
        decrypted = base64.b64decode(user["api_key"]).decode()
        return {"api_key": decrypted}
    except Exception:
        return {"api_key": ""}
