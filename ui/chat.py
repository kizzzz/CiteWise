"""对话渲染组件"""
import re
import html
import streamlit as st


def render_annotated_content(content: str):
    """渲染带来源标注的内容（三色块）"""
    if not content or not isinstance(content, str):
        st.write(content)
        return

    parts = re.split(r'\n(?=\[KB\]|\[WEB\]|\[AI\])', content)
    has_annotation = any(p.strip().startswith(('[KB]', '[WEB]', '[AI]')) for p in parts)

    if not has_annotation:
        st.markdown(content)
        return

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("[KB]"):
            body = part[4:].strip()
            st.markdown('<div class="source-rag"><b>📖 知识库文献</b></div>', unsafe_allow_html=True)
            st.markdown(body)
        elif part.startswith("[WEB]"):
            body = part[5:].strip()
            st.markdown('<div class="source-web"><b>🌐 联网搜索</b></div>', unsafe_allow_html=True)
            st.markdown(body)
        elif part.startswith("[AI]"):
            body = part[4:].strip()
            st.markdown('<div class="source-llm"><b>🧠 大模型推理</b></div>', unsafe_allow_html=True)
            st.markdown(body)
        else:
            st.markdown(part)


def render_thinking(steps: list[str]):
    """渲染思考过程"""
    if not steps:
        return
    with st.expander("💭 思考过程", expanded=False):
        for i, s in enumerate(steps, 1):
            st.markdown(f'<p class="thinking-step">{i}. {html.escape(str(s))}</p>', unsafe_allow_html=True)


def render_citations_panel(content: str, sources: list[dict]):
    """渲染引用来源面板"""
    if not sources or not isinstance(content, str):
        return
    en = re.findall(r'\[([A-Z][\w\s]+(?:et al\.)?,\s*\d{4})\]', content)
    zh = re.findall(r'\[([\u4e00-\u9fff]+等?,\s*\d{4})\]', content)
    cites = list(set(en + zh))
    label = f"📎 引用来源 ({max(len(cites), len(sources))} 条)"
    with st.expander(label):
        if cites:
            for c in cites:
                m = [s for s in sources if c.lower() in s.get("citation", "").lower()]
                st.markdown(f"- **{c}** — {m[0].get('title','')}" if m else f"- {c}")
        else:
            for s in sources:
                st.markdown(f"- **{s.get('title','')}** {s.get('citation','')}")


def render_citation_badge(check: dict):
    """渲染引用校验结果"""
    if not check:
        return
    r = check.get("verification_rate", 0)
    t = check.get("total_citations", 0)
    v = check.get("verified", 0)
    if r >= 0.9:
        st.success(f"引用校验: {v}/{t} ({r:.0%})")
    elif r >= 0.7:
        st.warning(f"引用校验: {v}/{t} ({r:.0%})")
    else:
        st.error(f"引用校验: {v}/{t} ({r:.0%})")
    if check.get("unverified"):
        with st.expander("未验证"):
            for c in check["unverified"]:
                st.write(f"- {c}")


def render_msg(msg: dict):
    """渲染单条消息"""
    content = msg.get("content", "")
    msg_type = msg.get("type", "text")
    if msg.get("thinking_steps"):
        render_thinking(msg["thinking_steps"])
    if not isinstance(content, str):
        if isinstance(content, dict):
            _render_framework(content)
            return
        content = str(content)
    if msg_type == "table":
        st.markdown("### 📊 结构化对比表格")
        st.markdown(content)
    elif msg_type == "section":
        render_annotated_content(content)
        if msg.get("citations"):
            render_citation_badge(msg["citations"])
    elif msg_type == "framework":
        _render_framework(content)
    elif msg_type == "analysis":
        _render_analysis(content)
    else:
        render_annotated_content(content)
    render_citations_panel(content if isinstance(content, str) else "", msg.get("sources"))


def _render_framework(fw):
    if isinstance(fw, str):
        st.markdown(fw)
        return
    if not isinstance(fw, dict):
        st.write(fw); return
    for i, s in enumerate(fw.get("framework", []), 1):
        st.markdown(f"**{i}. {s.get('section','')}**")
        st.caption(f"目标: {s.get('goal','')} | 建议字数: {s.get('suggested_words',1000)}")
        for p in s.get("key_points", []):
            st.write(f"  - {p}")
    if fw.get("insights"):
        st.markdown("**关键洞察：**")
        for ins in fw["insights"]:
            st.write(f"  - {ins}")


def _render_analysis(result):
    """渲染分析结果"""
    if isinstance(result, str):
        st.markdown(result)
        return
    insights = result.get("insights", [])
    if insights:
        for ins in insights:
            st.info(ins)
