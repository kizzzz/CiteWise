"""侧边栏组件"""
import os
import streamlit as st


def render_sidebar():
    """渲染完整侧边栏"""
    from src.core.memory import global_profile, project_memory, working_memory
    from src.core.embedding import vector_store
    from src.core.retriever import bm25_index
    from src.core.rag import parse_pdf, chunk_paper
    from config.settings import PAPERS_DIR

    with st.sidebar:
        st.title("📚 CiteWise")
        st.caption("智能研究助手 · 从文献到论文")

        # --- 项目管理 ---
        st.subheader("项目管理")
        _render_project_management(project_memory, global_profile, working_memory)

        # --- 文献上传 ---
        st.divider()
        st.subheader("📄 文献上传")
        _render_upload_panel(PAPERS_DIR, project_memory, vector_store, bm25_index)

        # --- 项目状态 + 章节管理 ---
        st.divider()
        _render_project_status(project_memory, working_memory)

        # --- 快捷操作 ---
        st.divider()
        st.subheader("⚡ 快捷操作")
        _render_quick_actions(working_memory, project_memory)


def _render_project_management(pm, gp, wm):
    projects = pm.list_projects()
    if projects:
        opts = {f"{p['name']} ({p['id']})": p["id"] for p in projects}
        sel = st.selectbox("选择项目", list(opts.keys()), index=0)
        if st.button("切换项目"):
            st.session_state.project_id = opts[sel]
            wm.reset()
            st.session_state.main_chat = []
            st.session_state.sub_chats = {}
            st.session_state.sections_content = {}
            st.session_state.current_chat = "main"
            st.rerun()
        if not st.session_state.project_id:
            st.session_state.project_id = list(opts.values())[0]
    else:
        st.info("请创建项目")

    new_project_name = st.text_input("新建项目", placeholder="如：充电站空间分析")
    research_topic = st.text_input("研究主题", placeholder="如：电动汽车充电基础设施")
    if st.button("创建项目") and new_project_name:
        pid = pm.create_project(new_project_name, research_topic)
        st.session_state.project_id = pid
        gp.update("research_field", research_topic)
        # 跨项目复用建议
        _suggest_from_history(gp, pm)
        st.success(f"已创建: {new_project_name}")
        st.rerun()


def _suggest_from_history(gp, pm):
    """基于历史项目给出复用建议"""
    preferred = gp.get("preferred_fields", [])
    if preferred:
        st.info(f"💡 建议沿用字段: {', '.join(preferred[:5])}")
    focus = gp.get("focus_keywords", [])
    if focus:
        st.info(f"💡 关注关键词: {', '.join(focus[:3])}")


def _render_upload_panel(papers_dir, pm, vs, bm25):
    if not st.session_state.project_id:
        st.warning("请先选择项目")
        return
    uf = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=True)
    if uf and st.button("解析并入库"):
        progress = st.progress(0, text="解析中...")
        all_chunks, total = [], len(uf)
        all_figures = []
        for i, f in enumerate(uf):
            progress.progress(i / total, text=f"解析 {f.name} ({i+1}/{total})")
            safe_name = os.path.basename(f.name)
            path = os.path.join(papers_dir, safe_name)
            with open(path, "wb") as fp:
                fp.write(f.getbuffer())
            data = parse_pdf(path)
            chunks = chunk_paper(data)
            pm.add_paper(data["paper_id"], st.session_state.project_id,
                         data.get("title", f.name), data.get("authors", ""),
                         data.get("year", 0), f.name, len(chunks))
            all_chunks.extend(chunks)
            # 存储图表元数据
            for fig in data.get("figures", []):
                pm.add_figure(
                    fig["figure_id"], data["paper_id"], st.session_state.project_id,
                    fig["page"], fig["caption"],
                    fig.get("context_before", ""), fig.get("context_after", ""),
                    fig.get("section_title", ""),
                    fig.get("width", 0), fig.get("height", 0)
                )
                all_figures.append(fig)
        progress.progress(0.7, text="向量化中...")
        vs.index_chunks(all_chunks)
        bm25.build_index(vs.get_all_chunks())
        progress.progress(1.0, text="完成!")
        fig_count = len(all_figures)
        msg = f"已入库 {total} 篇论文，{len(all_chunks)} 个片段"
        if fig_count:
            msg += f"，{fig_count} 张图表"
        st.success(msg)
        st.session_state.main_chat.append({"role": "assistant", "content": msg, "type": "text"})
        st.session_state._show_insights = True
        st.rerun()


def _render_project_status(pm, wm):
    if not st.session_state.project_id:
        return
    st.subheader("📊 项目状态")
    state = pm.get_project_state(st.session_state.project_id)
    if not state:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("论文", state.get("paper_count", 0))
    c2.metric("已提取", state.get("extraction_count", 0))
    c3.metric("已生成", state.get("section_count", 0))
    c4.metric("图表", state.get("figure_count", 0))

    # 章节列表
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
                    pm.delete_section(sec["id"])
                    st.session_state.sub_chats.pop(sec["name"], None)
                    st.session_state.sections_content.pop(sec["name"], None)
                    if st.session_state.current_chat == sec["name"]:
                        st.session_state.current_chat = "main"
                    st.rerun()

    # 新增章节
    st.markdown("**➕ 新增章节**")
    new_sec = st.text_input("章节名称", placeholder="如：文献综述", key="new_sec")
    if st.button("生成", key="btn_gen_sec") and new_sec:
        st.session_state._pending_section = new_sec
        st.rerun()

    if sections_with_id:
        if st.button("🏠 回到主对话", key="nav_main"):
            st.session_state.current_chat = "main"
            st.rerun()

    # 论文列表
    papers = state.get("papers", [])
    if papers:
        with st.expander(f"📋 论文列表 ({len(papers)})"):
            for p in papers:
                st.write(f"- **{p['title'][:45]}** ({p.get('authors','')[:12]}, {p.get('year','?')})")


def _render_quick_actions(wm, pm):
    if st.button("🔄 重置主对话"):
        st.session_state.main_chat = []
        wm.reset()
        st.rerun()
    if st.button("📥 导出文章"):
        from src.core.agents.coordinator import coordinator
        result = coordinator.writer._ensure_deps() or {}
        # 简化导出
        if st.session_state.project_id:
            sections = pm.get_sections(st.session_state.project_id)
            if sections:
                doc = f"# {pm.get_project(st.session_state.project_id)['name']}\n\n"
                for s in sections:
                    doc += s["content"] + "\n\n---\n\n"
                st.download_button("下载 Markdown", doc, "research_paper.md", "text/markdown")
            else:
                st.warning("还没有生成章节")
