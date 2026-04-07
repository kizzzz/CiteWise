"""AnalystAgent — 数据分析 + 图表生成"""
import json
import logging
from typing import Optional

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """分析 Agent — 负责数据分析、洞察生成、图表工具"""

    def __init__(self):
        super().__init__("Analyst")
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            from src.core.llm import llm_client
            self._llm = llm_client
        return self._llm

    def analyze_project(self, project_id: str) -> dict:
        """分析项目数据，生成洞察"""
        self.reset()
        from src.core.memory import project_memory

        state = project_memory.get_project_state(project_id)
        if not state:
            return {"type": "text", "content": "项目不存在"}

        papers = state.get("papers", [])
        extractions = project_memory.get_extractions(project_id)

        self.think(f"分析 {len(papers)} 篇论文, {len(extractions)} 条提取记录")

        # 统计分析
        methods = {}
        years = {}
        for p in papers:
            year = p.get("year", 0)
            if year:
                years[year] = years.get(year, 0) + 1

        for e in extractions:
            fields = e.get("fields", {})
            method = fields.get("研究方法", fields.get("核心方法", "未知"))
            if method:
                methods[method] = methods.get(method, 0) + 1

        insights = []
        if methods:
            top_method = max(methods, key=methods.get)
            insights.append(f"主要研究方法: {top_method} ({methods[top_method]} 篇)")
        if years:
            insights.append(f"年份分布: {dict(sorted(years.items()))}")

        # 框架推荐
        framework = self._recommend_framework(papers, extractions, state.get("topic", ""))
        self.think("分析完成，生成建议")

        return {
            "type": "analysis",
            "insights": insights,
            "method_distribution": methods,
            "year_distribution": years,
            "framework": framework,
            "thinking_steps": self.thinking_steps,
        }

    def _recommend_framework(self, papers, extractions, topic: str) -> dict:
        """基于数据推荐论文框架"""
        from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE

        summary_data = json.dumps(
            [{"paper": e.get("paper_id", ""), "fields": e.get("fields", {})}
             for e in extractions],
            ensure_ascii=False, indent=2
        )

        task_prompt = prompt_engine.build_framework_prompt(
            summary_data=summary_data,
            paper_count=len(papers),
            research_topic=topic or "研究综述",
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_BASE},
            {"role": "user", "content": task_prompt},
        ]

        result = self.llm.chat_json(messages, temperature=0.5)
        return result

    def split_table(self, table_content: str, split_by: str = "columns") -> dict:
        """拆分表格"""
        self.reset()
        self.think(f"拆分表格，按 {split_by}")

        prompt = f"""将以下表格按 "{split_by}" 拆分为两个子表格。
输出 JSON: {{"table_a": "markdown", "table_b": "markdown", "split_note": "说明"}}

表格内容:
{table_content}"""

        messages = [{"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages, temperature=0.3)
        return {
            "type": "table_split",
            "content": result,
            "thinking_steps": self.thinking_steps,
        }

    def merge_descriptions(self, desc_a: str, desc_b: str) -> dict:
        """合并两个图表描述为对比描述"""
        self.reset()
        self.think("合并图表描述为对比图")

        prompt = f"""将以下两个图表描述合并为一个对比描述。
输出 JSON: {{"combined_description": "markdown", "comparison_note": "对比说明"}}

描述 A:
{desc_a}

描述 B:
{desc_b}"""

        messages = [{"role": "user", "content": prompt}]
        result = self.llm.chat_json(messages, temperature=0.3)
        return {
            "type": "chart_merge",
            "content": result,
            "thinking_steps": self.thinking_steps,
        }

    def process(self, user_input: str, project_id: str = None, **kwargs) -> dict:
        intent = kwargs.get("intent", "analyze")
        if intent == "analyze":
            return self.analyze_project(project_id or "")
        elif intent == "split_table":
            return self.split_table(
                kwargs.get("table_content", ""),
                kwargs.get("split_by", "columns")
            )
        elif intent == "merge_chart":
            return self.merge_descriptions(
                kwargs.get("desc_a", ""),
                kwargs.get("desc_b", "")
            )
        else:
            return self.analyze_project(project_id or "")
