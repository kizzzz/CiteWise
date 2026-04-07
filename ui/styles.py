"""全局 CSS 样式"""

STYLES = """
<style>
/* 来源标注 */
.source-rag{background:linear-gradient(90deg,#dbeafe,#eff6ff);border-left:3px solid #3b82f6;padding:6px 12px;margin:4px 0;border-radius:0 6px 6px 0}
.source-web{background:linear-gradient(90deg,#dcfce7,#f0fdf4);border-left:3px solid #22c55e;padding:6px 12px;margin:4px 0;border-radius:0 6px 6px 0}
.source-llm{background:linear-gradient(90deg,#f3e8ff,#faf5ff);border-left:3px solid #a855f7;padding:6px 12px;margin:4px 0;border-radius:0 6px 6px 0}

/* 思考步骤 */
.thinking-step{color:#6b7280;font-size:.85em;padding:2px 0}

/* 卡片样式 */
.metric-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin:4px 0}
.insight-card{background:linear-gradient(135deg,#f0f9ff,#e0f2fe);border:1px solid #bae6fd;border-radius:10px;padding:16px;margin:8px 0}
.framework-card{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:16px;margin:8px 0}
.config-card{background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:12px;margin:6px 0}

/* 来源标签 */
.source-tag{display:inline-flex;align-items:center;gap:4px;font-size:.75em;padding:2px 8px;border-radius:4px;margin-right:4px}
.tag-rag{background:#dbeafe;color:#1d4ed8}
.tag-web{background:#dcfce7;color:#15803d}
.tag-llm{background:#f3e8ff;color:#7c3aed}

/* 图表索引 */
.figure-item{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px;margin:4px 0}
.figure-item:hover{border-color:#3b82f6;background:#eff6ff}
</style>
"""

SOURCE_LEGEND = """
<div style="display:flex;gap:12px;font-size:.82em;color:#666">
<span>来源：</span>
<span style="border-left:3px solid #3b82f6;padding-left:6px">📖 知识库</span>
<span style="border-left:3px solid #22c55e;padding-left:6px">🌐 联网</span>
<span style="border-left:3px solid #a855f7;padding-left:6px">🧠 推理</span>
</div>
"""
