"""聊天路由 — LangGraph 流式响应（token 级流式 + agent_start/agent_end）"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from api.schemas import ChatRequest, SubChatRequest
from src.eval.metrics import record_eval

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_LENGTH = 2000

# 需要监听的 LangGraph 节点名
_AGENT_NODES = {"supervisor", "researcher", "responder", "writer", "analyst"}


@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """主对话 — 真正的 token 级 SSE 流式输出"""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message must not exceed {MAX_MESSAGE_LENGTH} characters")
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id must not be empty")

    async def event_generator():
        try:
            from src.core.async_graph import stream_chat_response

            async for event in stream_chat_response(
                req.message, req.project_id,
                api_key=req.api_key or None,
                base_url=req.base_url or None,
                model=req.model or None,
            ):
                yield event

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            yield {"event": "error", "data": json.dumps({"message": "处理请求时发生错误，请稍后重试"}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/chat/sub")
async def sub_chat_endpoint(req: SubChatRequest):
    """子对话 — 章节级编辑（使用旧 coordinator 保持兼容）"""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message must not exceed {MAX_MESSAGE_LENGTH} characters")
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id must not be empty")
    try:
        from src.core.agents.coordinator import coordinator

        augmented_prompt = (
            f"用户正在撰写论文的「{req.section_name}」章节。\n\n"
            f"当前章节内容：\n{req.content[:3000]}\n\n"
            f"用户最新指令：{req.message}\n\n"
            f"请根据用户指令对「{req.section_name}」章节进行操作。直接输出修改后的内容或回答。"
        )

        result = await asyncio.to_thread(
            coordinator.process,
            augmented_prompt, req.project_id,
            intent="modify",
            target_content=req.content,
        )

        content = result.get("content", "")
        rtype = result.get("type", "text")

        if content and rtype != "error":
            from src.core.memory import project_memory
            project_memory.save_section(req.project_id, req.section_name, content)

        return {
            "content": content,
            "type": rtype,
            "sources": result.get("sources"),
            "citations": result.get("citations"),
        }
    except Exception as e:
        logger.error(f"Sub-chat error: {e}", exc_info=True)
        return {"content": "处理出错，请稍后重试", "type": "error"}
