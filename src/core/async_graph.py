"""LangGraph 异步版本 — 支持逐字流式输出

替换 graph.py 中的同步节点为异步节点，
使 astream_events 能 yield on_chat_model_stream 事件。
"""
import logging

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
    """异步 Responder — 支持逐 token 流式输出"""
    import time
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

    # 异步调用 — astream_events 可以捕获此调用的流式输出
    response = await llm_client.achat(messages, temperature=0.7)
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
    import time
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

    # 对大部分 writer 操作使用同步调用（保持兼容）
    # 仅对 generate 使用异步
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
    project_state = project_memory.get_project_state(project_id) if project_id else {}

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

    # 异步 LLM 调用
    content = await llm_client.achat(messages, temperature=0.7, max_tokens=4000)
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


# ========== Build Async Graph ==========

def build_async_graph():
    """构建异步版 LangGraph — Supervisor 模式，节点使用 async"""
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)    # 同步，够快
    workflow.add_node("researcher", researcher_node)    # 同步（RAG 是同步的）
    workflow.add_node("responder", async_responder_node)  # 异步 LLM
    workflow.add_node("writer", async_writer_node)        # 异步 LLM
    workflow.add_node("analyst", analyst_node)  # analyst 用同步也行

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
