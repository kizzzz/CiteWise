"""聊天路由 — LangGraph 流式响应（agent_start/agent_end + 内容）"""
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
    """主对话 — LangGraph astream_events 流式返回"""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="Message must not be empty")
    if len(req.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message must not exceed {MAX_MESSAGE_LENGTH} characters")
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id must not be empty")

    async def event_generator():
        try:
            from src.core.async_graph import get_async_graph

            graph = get_async_graph()
            config = {"configurable": {"thread_id": req.project_id}}
            input_state = {
                "user_input": req.message,
                "project_id": req.project_id,
                "thinking_steps": [],
                "agent_events": [],
            }

            start_time = time.time()
            final_result = {}

            async for event in graph.astream_events(
                input_state, config=config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")

                # Agent 节点开始
                if kind == "on_chain_start" and name in _AGENT_NODES:
                    output_state = event.get("data", {}).get("input", {})
                    agent_events = output_state.get("agent_events", []) if isinstance(output_state, dict) else []
                    # 从已有的 agent_events 中取最后一条作为描述
                    last = agent_events[-1] if agent_events else {}
                    yield {
                        "event": "agent_start",
                        "data": json.dumps({
                            "agent": name.capitalize(),
                            "detail": last.get("detail", f"{name} 启动中..."),
                        }, ensure_ascii=False),
                    }

                # Agent 节点完成
                elif kind == "on_chain_end" and name in _AGENT_NODES:
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        final_result.update(output)
                        agent_events = output.get("agent_events", [])
                        last = agent_events[-1] if agent_events else {}
                        yield {
                            "event": "agent_end",
                            "data": json.dumps({
                                "agent": name.capitalize(),
                                "detail": last.get("detail", "完成"),
                                "duration_ms": last.get("duration_ms", 0),
                            }, ensure_ascii=False),
                        }

            # ---- 发送最终结果 ----
            # 思考步骤
            for step in final_result.get("thinking_steps", []):
                yield {"event": "thinking", "data": json.dumps({"step": step}, ensure_ascii=False)}

            # 内容
            content = final_result.get("content", "")
            rtype = final_result.get("response_type", final_result.get("type", "text"))
            if content:
                yield {"event": "content", "data": json.dumps({
                    "content": content, "type": rtype,
                }, ensure_ascii=False)}

            # 引用
            citations = final_result.get("citations")
            if citations:
                yield {"event": "citations", "data": json.dumps(citations, ensure_ascii=False)}

            sources = final_result.get("sources")
            if sources:
                yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

            # 章节名
            section_name = final_result.get("section_name")
            if section_name:
                yield {"event": "section", "data": json.dumps({
                    "section_name": section_name, "content": content, "type": rtype,
                }, ensure_ascii=False)}

            # 来源标注
            content_sources = final_result.get("content_sources")
            if content_sources:
                yield {"event": "content_sources", "data": json.dumps(content_sources, ensure_ascii=False)}

            elapsed = int((time.time() - start_time) * 1000)
            yield {"event": "done", "data": json.dumps({"type": rtype}, ensure_ascii=False)}

            # Eval metrics
            session_id = f"s_{req.project_id}_{int(time.time())}"
            record_eval(
                session_id=session_id,
                project_id=req.project_id,
                intent=final_result.get("intent", "unknown"),
                task_type=rtype,
                success=True,
                response_time_ms=elapsed,
                has_citations=bool(final_result.get("citations")),
                llm_model="glm-4.7",
            )

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
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
