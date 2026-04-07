"""聊天路由 — SSE 流式响应"""
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


@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """主对话 — SSE 流式返回"""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message must not exceed {MAX_MESSAGE_LENGTH} characters")
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id must not be empty")

    async def event_generator():
        try:
            from src.core.agents.coordinator import coordinator

            # 在线程池中运行同步的 coordinator
            start_time = time.time()
            result = await asyncio.to_thread(
                coordinator.process, req.message, req.project_id
            )
            elapsed = int((time.time() - start_time) * 1000)

            # 发送思考步骤
            for step in result.get("thinking_steps", []):
                yield {"event": "thinking", "data": json.dumps({"step": step}, ensure_ascii=False)}

            # 发送内容
            content = result.get("content", "")
            rtype = result.get("type", "text")

            if content:
                yield {"event": "content", "data": json.dumps({
                    "content": content,
                    "type": rtype,
                }, ensure_ascii=False)}

            # 发送引用信息
            citations = result.get("citations")
            if citations:
                yield {"event": "citations", "data": json.dumps(citations, ensure_ascii=False)}

            sources = result.get("sources")
            if sources:
                yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

            # 如果是章节生成，发送 section_name
            section_name = result.get("section_name")
            if section_name:
                yield {"event": "section", "data": json.dumps({
                    "section_name": section_name,
                    "content": content,
                    "type": rtype,
                }, ensure_ascii=False)}

            # 发送内容来源标注信息
            content_sources = result.get("content_sources")
            if content_sources:
                yield {"event": "content_sources", "data": json.dumps(
                    content_sources, ensure_ascii=False
                )}

            yield {"event": "done", "data": json.dumps({"type": rtype}, ensure_ascii=False)}

            # Record eval metrics
            session_id = f"s_{req.project_id}_{int(time.time())}"
            record_eval(
                session_id=session_id,
                project_id=req.project_id,
                intent=result.get("intent", "unknown"),
                task_type=result.get("type", "text"),
                success=True,
                response_time_ms=elapsed,
                has_citations=bool(result.get("citations")),
                llm_model="glm-4.7",
            )

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            # Record failed eval
            try:
                session_id = f"s_{req.project_id}_{int(time.time())}"
                record_eval(
                    session_id=session_id,
                    project_id=req.project_id,
                    intent="unknown",
                    task_type="text",
                    success=False,
                    response_time_ms=int((time.time() - start_time) * 1000),
                    llm_model="glm-4.7",
                    metadata={"error": "internal_error"},
                )
            except Exception:
                pass
            yield {"event": "error", "data": json.dumps({"message": "处理请求时发生错误，请稍后重试"}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/chat/sub")
async def sub_chat_endpoint(req: SubChatRequest):
    """子对话 — 章节级编辑"""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message must not exceed {MAX_MESSAGE_LENGTH} characters")
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id must not be empty")
    try:
        from src.core.agents.coordinator import coordinator

        SECTION_CONTENT_BUDGET = 3000
        MAIN_CONTEXT_BUDGET = 800
        SUB_CONTEXT_BUDGET = 600
        CONTENT_SNIPPET_LENGTH = 150

        augmented_prompt = f"""用户正在撰写论文的「{req.section_name}」章节。

当前章节内容：
{req.content[:SECTION_CONTENT_BUDGET]}

用户最新指令：{req.message}

请根据用户指令对「{req.section_name}」章节进行操作。直接输出修改后的内容或回答。"""

        result = await asyncio.to_thread(
            coordinator.process,
            augmented_prompt, req.project_id,
            intent="modify",
            target_content=req.content,
        )

        content = result.get("content", "")
        rtype = result.get("type", "text")

        # 子对话内容也保存回数据库
        if content and rtype != "error":
            from src.core.memory import project_memory
            project_memory.save_section(
                req.project_id, req.section_name, content
            )

        return {
            "content": content,
            "type": rtype,
            "sources": result.get("sources"),
            "citations": result.get("citations"),
        }
    except Exception as e:
        logger.error(f"Sub-chat error: {e}", exc_info=True)
        return {"content": "处理出错，请稍后重试", "type": "error"}
