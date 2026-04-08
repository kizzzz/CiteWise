"""LangGraph 异步版本 — 支持逐字流式输出

替换 graph.py 中的同步节点为异步节点，
使 astream_events 能 yield on_chat_model_stream 事件。
"""
import logging
import time

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.core.graph_state import AgentState
from src.core.agents.router import RouterAgent
from src.core.agents.researcher import ResearchAgent
from src.core.agents.writer import WriterAgent
from src.core.agents.analyst import AnalystAgent
from src.core.graph import (
    supervisor_node, researcher_node, analyst_node,
    route_from_supervisor, route_after_research,
    _parse_section_name, _parse_section_topic,
)

logger = logging.getLogger(__name__)

_router = RouterAgent()
_researcher = ResearchAgent()
_writer = WriterAgent()
_analyst = AnalystAgent()


# ========== Async Node Functions ==========

async def async_responder_node(state: AgentState) -> dict:
    """异步 Responder — 使用 achat_stream 逐 token 输出

    每个 token 通过 state["stream_tokens"] 传递，
    聊天路由会收集并推送。
    """
    start = time.time()

    events = list(state.get("agent_events", [])) + [
        {"agent": "Responder", "event": "start", "detail": "生成回答...", "timestamp": start},
    ]

    from src.core.llm import llm_client
    from src.core.prompt import SYSTEM_PROMPT_BASE
    from src.core.source_annotation import annotate_sources
    from src.core.retriever import validate_citations

    user_input = state.get("user_input", "")
    intent = state.get("intent", "explore")
    chunks = state.get("chunks", [])
    web_results = state.get("web_results", [])
    rag_content = state.get("rag_content", "")
    thinking = list(state.get("thinking_steps", []))
    thinking.append("调用 LLM 生成回答...")

    safe_input = user_input.replace("```", " ").replace("<|", " ").strip()

    if intent == "websearch" and web_results:
        web_snippets = "\n".join(
            f"- [{r['title']}]({r['url']}): {r['snippet']}" for r in web_results
        )
        prompt = (
            f"## 用户问题\n{safe_input}\n\n"
            f"## 网络搜索结果\n{web_snippets}\n\n"
            f"## 知识库文献\n{rag_content or '（无）'}\n\n"
            "请整合以上来源回答用户问题，使用 [作者, 年份] 标注引用。"
        )
    else:
        prompt = (
            f"## 用户问题\n{safe_input}\n\n"
            f"## 参考材料（知识库检索）\n{rag_content or '（无相关内容）'}\n\n"
            "请基于参考材料和自身知识回答，使用 [作者, 年份] 标注引用。"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_BASE},
        {"role": "user", "content": prompt},
    ]

    # 流式 token 收集
    collected_tokens = []
    async for token in llm_client.achat_stream(messages, temperature=0.7):
        collected_tokens.append(token)

    response = "".join(collected_tokens)
    response = annotate_sources(response, chunks, web_results)

    citation_check = validate_citations(response, chunks) if chunks else {}
    sources = [
        {"title": c.get("paper_title", ""), "citation": c.get("citation", "")}
        for c in chunks
    ] if chunks else []

    thinking.append("回答生成完成")
    events.append({
        "agent": "Responder", "event": "end", "detail": f"生成 {len(response)} 字",
        "timestamp": time.time(), "duration_ms": int((time.time() - start) * 1000),
    })

    return {
        "content": response,
        "response_type": "text",
        "citations": citation_check,
        "sources": sources,
        "content_sources": {"rag": bool(chunks), "llm": True, "web": bool(web_results)},
        "thinking_steps": thinking,
        "agent_events": events,
    }


async def async_writer_node(state: AgentState) -> dict:
    """异步 Writer — 异步 LLM 调用"""
    start = time.time()
    intent = state.get("intent", "generate")
    user_input = state.get("user_input", "")
    project_id = state.get("project_id")

    events = list(state.get("agent_events", [])) + [
        {"agent": "Writer", "event": "start", "detail": f"处理: {intent}", "timestamp": start},
    ]

    research_result = {
        "chunks": state.get("chunks", []),
        "rag_content": state.get("rag_content", ""),
        "web_results": state.get("web_results", []),
        "sources": state.get("sources", []),
    }

    if intent == "modify":
        result = _writer.modify_content(
            user_input, state.get("target_content", ""),
            research_result, project_id,
        )
    elif intent == "export":
        from src.core.graph import _handle_export
        result = _handle_export(state)
    else:
        section_name = _parse_section_name(user_input)
        section_topic = _parse_section_topic(user_input, section_name)
        result = await _async_generate_section(
            section_name, section_topic, research_result, project_id,
            state.get("framework", []),
        )

    thinking = list(state.get("thinking_steps", [])) + result.get("thinking_steps", [])
    events.append({
        "agent": "Writer", "event": "end", "detail": result.get("response_type", intent),
        "timestamp": time.time(), "duration_ms": int((time.time() - start) * 1000),
    })

    return {
        **result,
        "thinking_steps": thinking,
        "agent_events": events,
    }


async def _async_generate_section(section_name, section_topic, research_result,
                                   project_id, framework):
    """异步章节生成"""
    from src.core.llm import llm_client
    from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE
    from src.core.source_annotation import annotate_sources, summarize_section
    from src.core.retriever import validate_citations
    from src.core.memory import project_memory, working_memory

    rag_content = research_result.get("rag_content", "")
    chunks = research_result.get("chunks", [])
    previous_summary = working_memory.get_previous_summary()

    system = SYSTEM_PROMPT_BASE
    task_prompt = prompt_engine.build_section_prompt(
        section_name=section_name,
        section_topic=section_topic,
        reference_material=rag_content,
        framework=str(framework) if framework else "",
        previous_summary=previous_summary,
        target_words=1000,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task_prompt},
    ]

    # 流式收集
    collected_tokens = []
    async for token in llm_client.achat_stream(messages, temperature=0.7, max_tokens=4000):
        collected_tokens.append(token)
    content = "".join(collected_tokens)
    content = annotate_sources(content, chunks, [])

    project_memory.save_section(project_id, section_name, content)
    summary = summarize_section(llm_client, content)
    working_memory.add_section_summary(section_name, summary, len(content))

    citation_check = validate_citations(content, chunks)

    return {
        "type": "section",
        "content": content,
        "section_name": section_name,
        "response_type": "section",
        "intent": "generate",
        "citations": citation_check,
        "word_count": len(content),
        "sources": [
            {"title": c.get("paper_title", ""), "citation": c.get("citation", "")}
            for c in chunks
        ] if chunks else [],
        "thinking_steps": ["异步章节生成完成"],
    }


# ========== Streaming Response Builder ==========
# This function provides direct token-level streaming for the chat route.

async def stream_chat_response(user_input: str, project_id: str):
    """直接流式对话 — 路由 → RAG → 流式 LLM 输出

    Yields SSE events: agent_start, agent_end, token, content, citations, done
    """
    import json
    from src.core.llm import llm_client
    from src.core.prompt import SYSTEM_PROMPT_BASE
    from src.core.source_annotation import annotate_sources
    from src.core.retriever import validate_citations, hybrid_search

    start_time = time.time()

    # Step 1: Route intent (sync, fast)
    yield {"event": "agent_start", "data": json.dumps({
        "agent": "Supervisor", "detail": "分析意图..."
    }, ensure_ascii=False)}

    route_result = _router.route(user_input)
    intent = route_result.get("intent", "explore")
    yield {"event": "agent_end", "data": json.dumps({
        "agent": "Supervisor", "detail": f"意图: {intent}"
    }, ensure_ascii=False)}

    # Step 2: Research (RAG)
    chunks = []
    web_results = []
    rag_content = ""

    yield {"event": "agent_start", "data": json.dumps({
        "agent": "Researcher", "detail": "检索知识库..."
    }, ensure_ascii=False)}

    try:
        chunks = hybrid_search(user_input, project_id=project_id)
        if chunks:
            rag_parts = []
            for i, c in enumerate(chunks[:10]):
                rag_parts.append(f"[{i+1}] {c.get('paper_title', '')} ({c.get('year', '')}): {c['text'][:300]}")
            rag_content = "\n\n".join(rag_parts)
    except Exception as e:
        logger.warning(f"RAG 检索失败: {e}")

    # Web search if needed
    if intent == "websearch":
        try:
            from src.tools.web_search import web_search_tool
            web_results = web_search_tool.search(user_input, max_results=5)
        except Exception as e:
            logger.warning(f"联网搜索失败: {e}")

    yield {"event": "agent_end", "data": json.dumps({
        "agent": "Researcher",
        "detail": f"检索完成: {len(chunks)} 文献片段" + (f", {len(web_results)} 网络结果" if web_results else ""),
        "duration_ms": int((time.time() - start_time) * 1000),
    }, ensure_ascii=False)}

    # Step 3: Stream LLM response
    yield {"event": "agent_start", "data": json.dumps({
        "agent": "Responder", "detail": "生成回答..."
    }, ensure_ascii=False)}

    safe_input = user_input.replace("```", " ").replace("<|", " ").strip()

    if intent == "websearch" and web_results:
        web_snippets = "\n".join(
            f"- [{r['title']}]({r['url']}): {r['snippet']}" for r in web_results
        )
        prompt = (
            f"## 用户问题\n{safe_input}\n\n"
            f"## 网络搜索结果\n{web_snippets}\n\n"
            f"## 知识库文献\n{rag_content or '（无）'}\n\n"
            "请整合以上来源回答用户问题，使用 [作者, 年份] 标注引用。"
        )
    else:
        prompt = (
            f"## 用户问题\n{safe_input}\n\n"
            f"## 参考材料（知识库检索）\n{rag_content or '（无相关内容）'}\n\n"
            "请基于参考材料和自身知识回答，使用 [作者, 年份] 标注引用。"
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_BASE},
        {"role": "user", "content": prompt},
    ]

    # Token-level streaming
    collected_tokens = []
    try:
        async for token in llm_client.achat_stream(messages, temperature=0.7):
            collected_tokens.append(token)
            yield {"event": "token", "data": json.dumps({"text": token}, ensure_ascii=False)}
    except Exception as e:
        logger.error(f"LLM 流式调用失败: {e}")
        yield {"event": "error", "data": json.dumps({"message": "LLM 调用失败"}, ensure_ascii=False)}
        return

    full_response = "".join(collected_tokens)
    full_response = annotate_sources(full_response, chunks, web_results)

    citation_check = validate_citations(full_response, chunks) if chunks else {}
    sources = [
        {"title": c.get("paper_title", ""), "citation": c.get("citation", "")}
        for c in chunks
    ] if chunks else []

    elapsed = int((time.time() - start_time) * 1000)
    yield {"event": "agent_end", "data": json.dumps({
        "agent": "Responder", "detail": f"生成 {len(full_response)} 字",
        "duration_ms": elapsed,
    }, ensure_ascii=False)}

    # Send final content (complete, with source annotations)
    yield {"event": "content", "data": json.dumps({
        "content": full_response, "type": "text",
    }, ensure_ascii=False)}

    if citation_check:
        yield {"event": "citations", "data": json.dumps(citation_check, ensure_ascii=False)}
    if sources:
        yield {"event": "sources", "data": json.dumps(sources, ensure_ascii=False)}

    yield {"event": "done", "data": json.dumps({"type": "text"}, ensure_ascii=False)}

    # Record eval
    try:
        from src.eval.metrics import record_eval
        session_id = f"s_{project_id}_{int(time.time())}"
        record_eval(
            session_id=session_id,
            project_id=project_id,
            intent=intent,
            task_type="text",
            success=True,
            response_time_ms=elapsed,
            has_citations=bool(citation_check),
            llm_model="glm-4.7",
        )
    except Exception:
        pass


# ========== Build Async Graph ==========

def build_async_graph():
    """构建异步版 LangGraph — Supervisor 模式，节点使用 async"""
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("responder", async_responder_node)
    workflow.add_node("writer", async_writer_node)
    workflow.add_node("analyst", analyst_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor", route_from_supervisor,
        {"researcher": "researcher", "writer": "writer"},
    )

    workflow.add_conditional_edges(
        "researcher", route_after_research,
        {"writer": "writer", "analyst": "analyst", "responder": "responder"},
    )

    for node in ("responder", "writer", "analyst"):
        workflow.add_edge(node, END)

    return workflow.compile(checkpointer=MemorySaver())


# 全局异步 graph 实例
_async_graph = None


def get_async_graph():
    global _async_graph
    if _async_graph is None:
        _async_graph = build_async_graph()
    return _async_graph

