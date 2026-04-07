"""生成配置器面板"""
import streamlit as st


# 学术模板配置
SECTION_TEMPLATES = {
    "摘要": {"type": "概括性描述", "words": 300, "format": "纯文本"},
    "引言": {"type": "背景综述+问题提出", "words": 1000, "format": "纯文本"},
    "文献综述": {"type": "分类文献综述", "words": 2000, "format": "文本+分类表格"},
    "方法论": {"type": "方法描述与对比", "words": 1500, "format": "文本+变量表格"},
    "结果": {"type": "数据分析结果", "words": 1500, "format": "文本+数据表格+图表"},
    "讨论": {"type": "结果解读+政策启示", "words": 1200, "format": "纯文本"},
    "结论与展望": {"type": "总结+未来方向", "words": 500, "format": "纯文本"},
    "参考文献": {"type": "引用列表", "words": 0, "format": "带编号列表"},
}


def render_config_panel(sections: list[str], figures: list[dict] = None):
    """渲染生成配置器

    返回: dict[section_name, config] 或 None（未确认时）
    """
    st.markdown("### 🔧 生成配置")

    configs = {}
    with st.expander("展开配置面板", expanded=False):
        for sec_name in sections:
            template = SECTION_TEMPLATES.get(sec_name, {"type": "综合", "words": 1000, "format": "纯文本"})

            st.markdown(f"**{sec_name}**")
            col1, col2, col3 = st.columns(3)

            with col1:
                retrieval = st.selectbox(
                    "检索策略",
                    ["按主题检索", "按章节检索", "按论文逐一检索"],
                    key=f"retrieval_{sec_name}"
                )
            with col2:
                target_words = st.slider(
                    "目标字数",
                    min_value=100, max_value=3000,
                    value=template["words"],
                    key=f"words_{sec_name}"
                )
            with col3:
                output_format = st.selectbox(
                    "输出格式",
                    ["纯文本", "文本+表格", "文本+表格+图表"],
                    index=["纯文本", "文本+表格", "文本+表格+图表"].index(template["format"])
                    if template["format"] in ["纯文本", "文本+表格", "文本+表格+图表"] else 0,
                    key=f"format_{sec_name}"
                )

            # 重点标注
            highlight = st.text_input(
                "重点/特殊要求",
                placeholder=f"如：重点突出 MGWR 空间异质性",
                key=f"highlight_{sec_name}"
            )

            # 图表选择
            if figures and output_format != "纯文本":
                fig_options = [f"Page {f['page']}: {f['caption'][:40]}" for f in figures]
                selected_figs = st.multiselect(
                    "嵌入图表",
                    fig_options,
                    key=f"figs_{sec_name}"
                )
            else:
                selected_figs = []

            configs[sec_name] = {
                "section_name": sec_name,
                "retrieval_strategy": retrieval,
                "target_words": target_words,
                "output_format": output_format,
                "highlight_focus": highlight,
                "figures_to_embed": selected_figs,
                "content_type": template["type"],
            }

            st.divider()

    return configs


def render_batch_generate_button(configs: dict, project_id: str):
    """一键生成全部章节"""
    if st.button("🚀 一键生成全部章节", type="primary", use_container_width=True):
        return configs
    return None
