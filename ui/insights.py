"""数据洞察面板"""
import streamlit as st
import pandas as pd


def render_insights_panel(project_id: str):
    """渲染数据洞察面板 — 上传完成后自动分析"""
    from src.core.agents.analyst import AnalystAgent

    analyst = AnalystAgent()
    result = analyst.analyze_project(project_id)

    if result.get("type") != "analysis":
        return

    st.markdown("### 💡 数据洞察")

    # 洞察卡片
    insights = result.get("insights", [])
    if insights:
        for ins in insights:
            st.info(ins)

    # 方法分布图
    methods = result.get("method_distribution", {})
    if methods:
        st.markdown("**研究方法分布**")
        df = pd.DataFrame({
            "方法": list(methods.keys()),
            "论文数": list(methods.values())
        })
        st.bar_chart(df.set_index("方法"))

    # 年份分布图
    years = result.get("year_distribution", {})
    if years:
        st.markdown("**年份分布**")
        df = pd.DataFrame({
            "年份": [str(y) for y in years.keys()],
            "论文数": list(years.values())
        })
        st.bar_chart(df.set_index("年份"))

    # 框架推荐
    framework = result.get("framework", {})
    if framework:
        with st.expander("📋 推荐框架", expanded=False):
            _render_framework(framework)


def _render_framework(framework: dict):
    """渲染推荐框架"""
    sections = framework.get("framework", [])
    for i, s in enumerate(sections, 1):
        st.markdown(f"**{i}. {s.get('section', '')}**")
        st.caption(f"目标: {s.get('goal', '')} | 建议字数: {s.get('suggested_words', 1000)}")
        for p in s.get("key_points", []):
            st.write(f"  - {p}")
    if framework.get("insights"):
        st.markdown("**关键洞察：**")
        for ins in framework["insights"]:
            st.write(f"  - {ins}")
