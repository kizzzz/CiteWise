"""论文投递 — 期刊推荐 + 格式检查 + 格式修改"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ========== Prompt 模板 ==========

_ANALYZE_PAPER_PROMPT = """## 任务：分析学术论文的研究方向

### 论文内容
{paper_content}

### 要求
分析上述论文内容，提取以下信息：
1. 主要研究领域和细分方向
2. 关键术语和研究方法
3. 论文的核心主题摘要

请用 JSON 格式回复：
```json
{{
  "research_fields": ["领域1", "领域2"],
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "methods": ["方法1", "方法2"],
  "paper_summary": "论文核心内容的100字摘要",
  "language": "中文/英文/中英混合"
}}
```
只回复 JSON，不要解释。"""

_RECOMMEND_JOURNALS_PROMPT = """## 任务：推荐合适的学术期刊

### 论文分析
- 研究领域：{research_fields}
- 关键词：{keywords}
- 研究方法：{methods}
- 论文摘要：{paper_summary}
- 论文语言：{language}

### 联网搜索结果
{web_results}

### 要求
基于论文内容和搜索结果，推荐 {top_k} 个最合适的投稿期刊。
请综合搜索结果和你的学术知识进行推荐。

请用 JSON 格式回复：
```json
{{
  "journals": [
    {{
      "name": "期刊全名",
      "publisher": "出版社",
      "level": "SCI-Q1/SCI-Q2/SCI-Q3/SCI-Q4/EI/CSSCI/北大核心/CSCD/普通期刊",
      "impact_factor": "影响因子（如 5.2，不确定填 N/A）",
      "match_score": 85,
      "match_reason": "匹配原因（一句话说明为什么适合这篇论文）",
      "submission_url": "投稿系统网址（不确定填 N/A）",
      "review_cycle": "审稿周期（如 2-3个月，不确定填 N/A）",
      "acceptance_rate": "录用率（如 25%，不确定填 N/A）"
    }}
  ]
}}
```
只回复 JSON。match_score 为 0-100 的整数，按匹配度从高到低排序。"""

_FORMAT_CHECK_PROMPT = """## 任务：对照期刊格式要求检查论文

### 目标期刊
{journal_name}

### 期刊投稿指南（联网搜索结果）
{web_requirements}

### 论文各章节内容
{paper_content}

### 要求
对照目标期刊的格式要求，逐项检查论文当前状态，生成修改建议清单。

请用 JSON 格式回复：
```json
{{
  "journal_name": "期刊名称",
  "requirements_summary": "该期刊格式要求的一百字概要",
  "checklist": [
    {{
      "id": 1,
      "category": "structure",
      "description": "期刊要求：应包含摘要、关键词、引言、方法、实验、结论等章节",
      "current_state": "当前论文有：xxx",
      "suggestion": "具体修改建议",
      "severity": "required"
    }}
  ]
}}
```

category 可选值：structure（结构）、formatting（排版格式）、citation（引用格式）、length（篇幅要求）、language（语言要求）、figures（图表要求）、abstract（摘要要求）
severity 可选值：required（必须）、recommended（建议）、optional（可选）

只回复 JSON，尽量覆盖所有维度，通常应有 8-15 条检查项。"""

_FORMAT_APPLY_PROMPT = """## 任务：按修改建议调整论文章节内容

### 当前章节内容
{section_content}

### 需要应用的修改建议
{suggestions_text}

### 要求
按照上述修改建议，对章节内容进行调整。注意：
1. 只修改建议中提到的方面，不要改变论文的核心学术内容
2. 保持原文的学术风格和专业术语
3. 如果建议涉及结构调整，按新结构调整内容
4. 输出修改后的完整章节内容（不要省略任何部分）

请直接输出修改后的章节全文，不要加任何说明或标记。"""


def recommend_journals(
    project_id: str,
    research_topic: str = "",
    top_k: int = 8,
) -> list[dict]:
    """推荐投稿期刊"""
    from src.core.memory import project_memory
    from src.core.llm import llm_client
    from src.tools.web_search import web_search

    # 1. 获取论文内容
    sections = project_memory.get_unique_sections(project_id)
    if not sections:
        return []

    paper_parts = []
    total_len = 0
    for s in sections:
        content = s.get("content", "")
        if content:
            paper_parts.append(f"### {s.get('section_name', '章节')}\n{content}")
            total_len += len(content)
        if total_len > 4000:
            break
    paper_content = "\n\n".join(paper_parts)[:5000]

    # 2. LLM 分析论文
    analysis = llm_client.chat_json(
        [
            {"role": "system", "content": "你是学术分析专家，只输出 JSON。"},
            {"role": "user", "content": _ANALYZE_PAPER_PROMPT.format(paper_content=paper_content)},
        ],
        temperature=0.3,
    )

    research_fields = analysis.get("research_fields", [])
    keywords = analysis.get("keywords", [])
    methods = analysis.get("methods", [])
    paper_summary = analysis.get("paper_summary", "")
    language = analysis.get("language", "中文")

    # 3. 联网搜索期刊
    web_results = []
    for field in research_fields[:2]:
        results = web_search(f"{field} 期刊 SCI 投稿 推荐", top_k=5)
        web_results.extend(results)
    for kw in keywords[:3]:
        results = web_search(f"{kw} journal impact factor submission", top_k=3)
        web_results.extend(results)

    # 去重
    seen_urls = set()
    unique_results = []
    for r in web_results:
        url = r.get("url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)
    web_results_text = "\n".join(
        f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('snippet', '')}"
        for r in unique_results[:15]
    )

    # 4. LLM 推荐期刊
    topic_hint = f"\n用户补充研究方向：{research_topic}" if research_topic else ""
    result = llm_client.chat_json(
        [
            {"role": "system", "content": "你是学术期刊推荐专家，只输出 JSON。"},
            {"role": "user", "content": _RECOMMEND_JOURNALS_PROMPT.format(
                research_fields=", ".join(research_fields),
                keywords=", ".join(keywords),
                methods=", ".join(methods),
                paper_summary=paper_summary,
                language=language,
                web_results=web_results_text,
                top_k=top_k,
            ) + topic_hint},
        ],
        temperature=0.5,
    )

    journals = result.get("journals", [])
    return journals[:top_k]


def check_format(
    project_id: str,
    journal_name: str,
) -> dict:
    """格式检查：对比论文内容与目标期刊要求"""
    from src.core.memory import project_memory
    from src.core.llm import llm_client
    from src.tools.web_search import web_search

    # 1. 获取论文内容
    sections = project_memory.get_unique_sections(project_id)
    if not sections:
        return {"journal_name": journal_name, "requirements_summary": "未找到论文内容", "checklist": []}

    paper_parts = []
    for s in sections:
        content = s.get("content", "")
        name = s.get("section_name", "章节")
        if content:
            paper_parts.append(f"### {name}\n{content[:800]}...")
    paper_content = "\n\n".join(paper_parts)[:5000]

    # 2. 联网搜索期刊格式要求
    web_reqs = []
    results_cn = web_search(f"{journal_name} 投稿指南 格式要求 author guidelines", top_k=5)
    web_reqs.extend(results_cn)
    results_en = web_search(f"{journal_name} paper format template requirements submission", top_k=3)
    web_reqs.extend(results_en)

    web_requirements = "\n".join(
        f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('snippet', '')}"
        for r in web_reqs[:10]
    )

    # 3. LLM 格式检查
    result = llm_client.chat_json(
        [
            {"role": "system", "content": "你是学术期刊格式审核专家，只输出 JSON。"},
            {"role": "user", "content": _FORMAT_CHECK_PROMPT.format(
                journal_name=journal_name,
                web_requirements=web_requirements,
                paper_content=paper_content,
            )},
        ],
        temperature=0.3,
    )

    return result


def apply_format_changes(
    project_id: str,
    section_name: str,
    suggestions: list[dict],
) -> dict:
    """应用选中的格式修改建议"""
    from src.core.memory import project_memory
    from src.core.llm import llm_client

    # 1. 获取目标章节
    sections = project_memory.get_unique_sections(project_id)
    target = None
    for s in sections:
        if s.get("section_name") == section_name:
            target = s
            break

    if not target:
        return {"status": "error", "message": f"未找到章节：{section_name}"}

    section_content = target.get("content", "")
    if not section_content:
        return {"status": "error", "message": "章节内容为空"}

    # 2. 格式化建议文本
    suggestions_text = "\n".join(
        f"- [{s.get('severity', 'recommended')}] {s.get('category', '')}: {s.get('suggestion', '')}"
        for s in suggestions
    )

    # 3. LLM 修改内容
    new_content = llm_client.chat(
        [
            {"role": "system", "content": "你是学术格式修改专家。只输出修改后的完整文本，不要加任何说明。"},
            {"role": "user", "content": _FORMAT_APPLY_PROMPT.format(
                section_content=section_content,
                suggestions_text=suggestions_text,
            )},
        ],
        temperature=0.3,
    )

    if not new_content or not new_content.strip():
        return {"status": "error", "message": "AI 修改结果为空"}

    # 4. 保存修改
    project_memory.save_section(project_id, section_name, new_content.strip())

    return {
        "status": "ok",
        "section_name": section_name,
        "content": new_content.strip(),
    }
