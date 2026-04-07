"""CiteWise V2 — 智能研究助手 | 多 Agent 协同 + 语义切块 + 图表索引"""
import sys
import os
import io
import logging
import re
import html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

from config.settings import PAPERS_DIR, DATA_DIR
from src.core.rag import parse_pdf, chunk_paper
from src.core.embedding import vector_store
from src.core.retriever import bm25_index, hybrid_search
from src.core.memory import global_profile, project_memory, working_memory
from src.core.agent import agent, route_intent
from src.core.agents.coordinator import coordinator
from src.core.llm import llm_client

from ui.styles import STYLES, SOURCE_LEGEND
from ui.chat import render_msg, render_thinking, render_annotated_content, render_citation_badge, render_citations_panel
from ui.figures import render_figures_panel
from ui.insights import render_insights_panel
from ui.config_panel import render_config_panel, render_batch_generate_button

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Context window constants
MAIN_HISTORY_WINDOW = 6
CONTENT_SNIPPET_LENGTH = 150
MAIN_CONTEXT_BUDGET = 800
SUB_CONTEXT_BUDGET = 600
SECTION_CONTENT_BUDGET = 3000

# ========== 页面配置 ==========
st.set_page_config(page_title="CiteWise V2", page_icon="📚", layout="wide")
st.markdown(STYLES, unsafe_allow_html=True)


# ==================== 辅助函数 ====================

def _handle_agent_result(result):
    """统一的 agent 结果渲染"""
    render_thinking(result.get("thinking_steps", []))
    rtype = result.get("type", "text")
    content = result.get("content", "")

    if rtype == "table":
        st.markdown("### 📊 对比表格")
        st.markdown(content)
    elif rtype == "framework":
        from ui.chat import _render_framework
        _render_framework(content)
    elif rtype == "export":
        st.download_button("下载", content, "research_paper.md", "text/markdown")
    elif rtype == "section":
        render_annotated_content(content)
        if result.get("citations"):
            render_citation_badge(result["citations"])
    else:
        render_annotated_content(content)

    render_citations_panel(content if isinstance(content, str) else "", result.get("sources"))
    return rtype


def _save_to_history(target_list, result):
    target_list.append({
        "role": "assistant",
        "content": result.get("content", ""),
        "type": result.get("type", "text"),
        "citations": result.get("citations"),
        "sources": result.get("sources"),
        "thinking_steps": result.get("thinking_steps", []),
        "section_name": result.get("section_name"),
    })


def _register_section(result):
    sname = result.get("section_name", "未命名章节")
    st.session_state.sub_chats.setdefault(sname, [])
    st.session_state.sections_content[sname] = result["content"]
    st.success(f"✅ 章节「{sname}」已生成！可在左侧点击进入子对话继续修改。")


# ========== BM25 启动初始化 ==========
if "bm25_initialized" not in st.session_state:
    try:
        all_chunks = vector_store.get_all_chunks()
        if all_chunks:
            bm25_index.build_index(all_chunks)
            logger.info(f"BM25 索引已从 Chroma 初始化，共 {len(all_chunks)} 个片段")
    except Exception as e:
        logger.warning(f"BM25 初始化失败: {e}")
    st.session_state.bm25_initialized = True


# ========== Session State ==========
if "project_id" not in st.session_state:
    st.session_state.project_id = None
if "main_chat" not in st.session_state:
    st.session_state.main_chat = []
if "sub_chats" not in st.session_state:
    st.session_state.sub_chats = {}
if "current_chat" not in st.session_state:
    st.session_state.current_chat = "main"
if "sections_content" not in st.session_state:
    st.session_state.sections_content = {}


# ========== 侧边栏 ==========
with st.sidebar:
    st.title("📚 CiteWise V2")
    st.caption("多 Agent 协同 · 语义切块 · 图表索引")

    # --- 项目管理 ---
    st.subheader("项目管理")
    projects = project_memory.list_projects()
    if projects:
        opts = {f"{p['name']} ({p['id']})": p["id"] for p in projects}
        sel = st.selectbox("选择项目", list(opts.keys()), index=0)
        if st.button("切换项目"):
            st.session_state.project_id = opts[sel]
            working_memory.reset()
            st.session_state.main_chat = []
            st.session_state.sub_chats = {}
            st.session_state.sections_content = {}
            st.session_state.current_chat = "main"
            st.rerun()
        if not st.session_state.project_id:
            st.session_state.project_id = list(opts.values())[0]
    else:
        st.info("请创建项目")

    nn = st.text_input("新建项目", placeholder="如：充电站空间分析")
    nt = st.text_input("研究主题", placeholder="如：电动汽车充电基础设施")
    if st.button("创建项目") and nn:
        pid = project_memory.create_project(nn, nt)
        st.session_state.project_id = pid
        global_profile.update("research_field", nt)
        # 跨项目复用建议
        preferred = global_profile.get("field_templates", [])
        if preferred:
            st.info(f"💡 可沿用上次字段模板: {preferred[-1].get('name', '')}")
        st.success(f"已创建: {nn}")
        st.rerun()

    # --- 文献上传 ---
    st.divider()
    st.subheader("📄 文献上传")
    if not st.session_state.project_id:
        st.warning("请先选择项目")
    else:
        uf = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=True)
        if uf and st.button("解析并入库"):
            progress = st.progress(0, text="解析中...")
            all_chunks, total = [], len(uf)
            fig_count = 0
            for i, f in enumerate(uf):
                progress.progress(i / total, text=f"解析 {f.name} ({i+1}/{total})")
                safe_name = os.path.basename(f.name)
                path = os.path.join(PAPERS_DIR, safe_name)
                with open(path, "wb") as fp:
                    fp.write(f.getbuffer())
                data = parse_pdf(path)
                chunks = chunk_paper(data)
                project_memory.add_paper(data["paper_id"], st.session_state.project_id,
                                         data.get("title", f.name), data.get("authors",""),
                                         data.get("year",0), f.name, len(chunks))
                all_chunks.extend(chunks)
                # 存储图表元数据
                for fig in data.get("figures", []):
                    project_memory.add_figure(
                        fig["figure_id"], data["paper_id"], st.session_state.project_id,
                        fig["page"], fig["caption"],
                        fig.get("context_before", ""), fig.get("context_after", ""),
                        fig.get("section_title", ""),
                        fig.get("width", 0), fig.get("height", 0)
                    )
                    fig_count += 1
            progress.progress(0.7, text="向量化中...")
            vector_store.index_chunks(all_chunks)
            bm25_index.build_index(vector_store.get_all_chunks())
            progress.progress(1.0, text="完成!")
            msg = f"已入库 {total} 篇论文，{len(all_chunks)} 个片段"
            if fig_count:
                msg += f"，{fig_count} 张图表"
            st.success(msg)
            st.session_state.main_chat.append({"role":"assistant","content":msg,"type":"text"})
            st.session_state._show_insights = True
            st.rerun()

    # --- 项目状态 + 章节管理 ---
    st.divider()
    if st.session_state.project_id:
        st.subheader("📊 项目状态")
        state = project_memory.get_project_state(st.session_state.project_id)
        if state:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("论文", state.get("paper_count", 0))
            c2.metric("已提取", state.get("extraction_count", 0))
            c3.metric("已生成", state.get("section_count", 0))
            c4.metric("图表", state.get("figure_count", 0))

            sections_with_id = state.get("sections_with_id", [])
            if sections_with_id:
                st.markdown("**📝 已生成章节**")
                for i, sec in enumerate(sections_with_id):
                    cols = st.columns([6, 1])
                    with cols[0]:
                        if st.button(f"📄 {sec['name']}", key=f"nav_{i}"):
                            st.session_state.current_chat = sec["name"]
                            st.rerun()
                    with cols[1]:
                        if st.button("🗑", key=f"del_{i}", help=f"删除「{sec['name']}」"):
                            project_memory.delete_section(sec["id"])
                            st.session_state.sub_chats.pop(sec["name"], None)
                            st.session_state.sections_content.pop(sec["name"], None)
                            if st.session_state.current_chat == sec["name"]:
                                st.session_state.current_chat = "main"
                            st.rerun()

            st.markdown("**➕ 新增章节**")
            new_sec = st.text_input("章节名称", placeholder="如：文献综述", key="new_sec")
            if st.button("生成", key="btn_gen_sec") and new_sec:
                st.session_state._pending_section = new_sec
                st.rerun()

            if sections_with_id:
                if st.button("🏠 回到主对话", key="nav_main"):
                    st.session_state.current_chat = "main"
                    st.rerun()

            papers = state.get("papers", [])
            if papers:
                with st.expander(f"📋 论文列表 ({len(papers)})"):
                    for p in papers:
                        st.write(f"- **{p['title'][:45]}** ({p.get('authors','')[:12]}, {p.get('year','?')})")

    # --- 快捷操作 ---
    st.divider()
    st.subheader("⚡ 快捷操作")
    if st.button("🔄 重置主对话"):
        st.session_state.main_chat = []
        working_memory.reset()
        st.rerun()
    if st.button("📥 导出文章"):
        _export_document()


def _export_document():
    if not st.session_state.project_id:
        return
    sections = project_memory.get_sections(st.session_state.project_id)
    if not sections:
        st.warning("还没有生成章节")
        return
    proj = project_memory.get_project(st.session_state.project_id)
    doc = f"# {proj['name']}\n\n"
    for s in sections:
        doc += s["content"] + "\n\n---\n\n"
    st.download_button("下载 Markdown", doc, "research_paper.md", "text/markdown")


def _do_structured_summary(pid, fields):
    """结构化总结"""
    from src.core.retriever import hybrid_search, format_chunks_with_citations
    from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE

    papers = project_memory.get_papers(pid)
    if not papers:
        st.error("没有论文"); return

    prog = st.progress(0, text="提取中...")
    results = []
    for idx, p in enumerate(papers[:10]):
        prog.progress((idx+1)/min(len(papers),10), text=f"提取 {p['title'][:35]}...")
        chunks = hybrid_search(", ".join(fields), top_k=5, where={"paper_id": p["id"]})
        if not chunks:
            continue
        txt = format_chunks_with_citations(chunks)
        ext = llm_client.chat_json([{"role":"system","content":SYSTEM_PROMPT_BASE},
            {"role":"user","content":prompt_engine.build_extract_prompt(fields, txt)}], temperature=0.3)
        if "fields" in ext:
            project_memory.save_extraction(pid, p["id"], "自定义", ext.get("fields",{}), ext.get("confidence",{}))
            results.append({"paper_title":p["title"],"authors":p["authors"],"year":p.get("year",""),**ext.get("fields",{})})
    prog.empty()

    if not results:
        st.warning("提取失败"); return

    st.session_state._summary_result = results
    st.session_state._summary_fields = fields
    st.session_state.main_chat.append({"role":"assistant","content":"结构化总结完成","type":"text"})
    st.rerun()


def _render_summary_results():
    """渲染结构化总结结果"""
    results = st.session_state.get("_summary_result")
    fields = st.session_state.get("_summary_fields")
    if not results:
        return

    st.markdown("### 📊 结构化对比表格")
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="结构化总结")
    buf.seek(0)
    st.download_button("📥 下载 Excel", buf.getvalue(), "structured_summary.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("### 📈 可视化图表")
    chart_fields = [f for f in fields if f in df.columns]
    if chart_fields:
        col1, col2 = st.columns(2)
        with col1:
            sel = st.selectbox("选择字段", chart_fields, key="chart_sel")
            if sel:
                counts = df[sel].value_counts()
                st.markdown(f"**{sel}** 分布")
                chart_data = pd.DataFrame({"label": counts.index.astype(str), "count": counts.values})
                st.bar_chart(chart_data.set_index("label"))
        with col2:
            st.markdown("**论文年份分布**")
            if "year" in df.columns:
                year_counts = df["year"].value_counts().sort_index()
                yc = pd.DataFrame({"year": year_counts.index.astype(str), "count": year_counts.values})
                st.bar_chart(yc.set_index("year"))
            else:
                st.info("无年份数据")


# ========== 主区域 ==========
st.title("CiteWise V2 — 智能研究助手")

if not st.session_state.project_id:
    st.warning("请在左侧创建或选择项目")
    st.stop()

proj = project_memory.get_project(st.session_state.project_id)

# ========== 主对话 ==========
current = st.session_state.current_chat
if current == "main":
    st.info(f"📋 **主对话** — {proj['name']} | 多 Agent 协同模式")
    st.markdown(SOURCE_LEGEND, unsafe_allow_html=True)

    # 数据洞察（上传后自动弹出）
    if st.session_state.pop("_show_insights", False):
        with st.expander("💡 数据洞察与建议", expanded=True):
            render_insights_panel(st.session_state.project_id)

    # 图表索引
    render_figures_panel(st.session_state.project_id)

    # 结构化总结面板
    with st.expander("📊 结构化总结", expanded=False):
        c1, c2 = st.columns([3, 1])
        with c1:
            fs = st.text_input("字段（逗号分隔）", value="研究方法, 数据集, 核心发现, 创新点", key="sf")
        with c2:
            st.write(""); st.write("")
            if st.button("🔍 提取", type="primary", use_container_width=True, key="btn_extract"):
                _do_structured_summary(st.session_state.project_id, [f.strip() for f in fs.split(",") if f.strip()])
    st.divider()

    # 渲染结构化总结结果
    _render_summary_results()

    # 主对话历史
    for msg in st.session_state.main_chat:
        with st.chat_message(msg["role"]):
            render_msg(msg)

    # 处理侧边栏触发的章节生成
    if st.session_state.get("_pending_section"):
        sec_name = st.session_state.pop("_pending_section")
        with st.chat_message("assistant"):
            with st.spinner(f"正在生成「{sec_name}」..."):
                try:
                    result = coordinator.process(
                        f"帮我写{sec_name}", st.session_state.project_id,
                        section_name=sec_name,
                    )
                except Exception as e:
                    logger.error(f"章节生成错误: {e}", exc_info=True)
                    result = {"type":"text","content":"处理请求时发生内部错误，请重试。","intent":"error"}
            rtype = _handle_agent_result(result)
            _save_to_history(st.session_state.main_chat, result)
            if rtype == "section":
                _register_section(result)
        st.rerun()

    # 主对话输入
    if prompt := st.chat_input("主对话 — 总结/框架/写引言/联网搜索/分析数据..."):
        st.session_state.main_chat.append({"role":"user","content":prompt,"type":"text"})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            delete_done = False
            if prompt.startswith("删除") or prompt.startswith("删掉"):
                for sec in project_memory.get_unique_sections(st.session_state.project_id):
                    if sec["section_name"] in prompt:
                        project_memory.delete_section(sec["id"])
                        st.session_state.sub_chats.pop(sec["section_name"], None)
                        st.session_state.sections_content.pop(sec["section_name"], None)
                        st.success(f"已删除章节「{sec['section_name']}」")
                        st.session_state.main_chat.append(
                            {"role":"assistant","content":f"已删除章节「{sec['section_name']}」","type":"text"})
                        delete_done = True
                        break

            if delete_done:
                st.rerun()
            else:
                with st.spinner("多 Agent 协同处理中..."):
                    try:
                        result = coordinator.process(prompt, st.session_state.project_id)
                    except Exception as e:
                        logger.error(f"Agent错误: {e}", exc_info=True)
                        result = {"type":"text","content":"处理请求时发生内部错误，请重试。","intent":"error"}

                rtype = _handle_agent_result(result)
                _save_to_history(st.session_state.main_chat, result)
                if rtype == "section":
                    _register_section(result)


# ========== 子对话 ==========
else:
    section_name = current
    st.info(f"📝 **子对话：{section_name}** | 继承主对话上下文，修改仅在本对话生效")
    st.caption(f"所属项目：{proj['name']}")

    sec_content = st.session_state.sections_content.get(section_name, "")
    if not sec_content:
        sections = project_memory.get_unique_sections(st.session_state.project_id)
        for s in sections:
            if s["section_name"] == section_name:
                sec_content = s["content"]
                st.session_state.sections_content[section_name] = sec_content
                break

    if sec_content:
        with st.expander("📄 当前章节内容", expanded=False):
            st.markdown(sec_content)

    st.divider()
    st.markdown(SOURCE_LEGEND, unsafe_allow_html=True)

    sub_history = st.session_state.sub_chats.get(section_name, [])
    for msg in sub_history:
        with st.chat_message(msg["role"]):
            render_msg(msg)

    if prompt := st.chat_input(f"子对话：{section_name} — 修改/拆分表格/合并图表..."):
        main_summary = "\n".join(
            f"[{m['role']}] {str(m.get('content',''))[:CONTENT_SNIPPET_LENGTH]}"
            for m in st.session_state.main_chat[-MAIN_HISTORY_WINDOW:]
            if m["role"] == "user" or m.get("type") == "text"
        )[-MAIN_CONTEXT_BUDGET:]

        sub_context = "\n".join(
            f"[{m['role']}] {str(m.get('content',''))[:CONTENT_SNIPPET_LENGTH]}"
            for m in sub_history[-4:]
        )[-SUB_CONTEXT_BUDGET:]

        augmented_prompt = f"""用户正在撰写论文的「{section_name}」章节。

当前章节内容：
{sec_content[:SECTION_CONTENT_BUDGET]}

主对话上下文：
{main_summary}

本子对话历史：
{sub_context}

用户最新指令：{prompt}

请根据用户指令对「{section_name}」章节进行操作。直接输出修改后的内容或回答。"""

        st.session_state.sub_chats.setdefault(section_name, []).append(
            {"role":"user","content":prompt,"type":"text"})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    result = coordinator.process(
                        augmented_prompt, st.session_state.project_id,
                        intent="modify",
                        target_content=sec_content,
                    )
                except Exception as e:
                    logger.error(f"子对话错误: {e}", exc_info=True)
                    result = {"type":"text","content":"处理请求时发生内部错误，请重试。","intent":"error"}

            _handle_agent_result(result)
            _save_to_history(st.session_state.sub_chats[section_name], result)

            if result.get("type") == "modify":
                st.session_state.sections_content[section_name] = result["content"]
                st.success("✅ 章节内容已更新")
