"""图表索引面板"""
import html
import streamlit as st


def render_figures_panel(project_id: str):
    """渲染图表索引面板"""
    from src.core.memory import project_memory

    figures = project_memory.get_all_figures(project_id)
    if not figures:
        return

    with st.expander(f"🖼 图表索引 ({len(figures)})", expanded=False):
        # 按论文分组
        papers = project_memory.get_papers(project_id)
        paper_map = {p["id"]: p["title"] for p in papers}

        grouped = {}
        for fig in figures:
            pid = fig.get("paper_id", "")
            if pid not in grouped:
                grouped[pid] = []
            grouped[pid].append(fig)

        for pid, figs in grouped.items():
            title = paper_map.get(pid, "未知论文")
            st.markdown(f"**📄 {title[:50]}**")
            for fig in figs:
                col1, col2 = st.columns([4, 1])
                with col1:
                    caption = html.escape(str(fig.get("caption", f"Page {fig.get('page', '?')}")[:60]))
                    width = fig.get("width") or 0
                    height = fig.get("height") or 0
                    st.markdown(
                        f'<div class="figure-item">'
                        f'<b>{caption}</b><br>'
                        f'<span style="font-size:.8em;color:#666">'
                        f'Page {fig.get("page", "?")} | '
                        f'{width:.0f}x{height:.0f}'
                        f'</span></div>',
                        unsafe_allow_html=True
                    )
                with col2:
                    context = fig.get("context_before", "")
                    if context:
                        st.caption(context[:80] + "...")
            st.divider()
