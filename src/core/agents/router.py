"""RouterAgent — 意图路由 + 任务分发"""
import logging
from typing import Optional

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)

INTENT_MAP = {
    "summarize": ["总结", "提取", "梳理", "对比", "字段", "表格", "结构化"],
    "generate": ["写", "生成", "撰写", "帮我写", "章节"],
    "framework": ["框架", "思路", "大纲", "怎么写", "结构"],
    "modify": ["修改", "调整", "改写", "重写", "换", "拆分", "合并"],
    "export": ["导出", "下载", "保存", "输出"],
    "chart": ["图表", "柱状图", "饼图", "可视化", "绘图"],
    "websearch": ["最新", "新闻", "最近", "当前", "联网", "搜索"],
    "figures": ["图表索引", "图片", "figure", "fig", "图表列表"],
    "analyze": ["分析", "洞察", "建议", "推荐", "模式"],
}

# Intents that should win in ties (higher priority)
_PRIORITY_INTENTS = {"export", "websearch", "modify"}


class RouterAgent(BaseAgent):
    """意图路由 Agent — 分析用户输入， 分配给合适的子 Agent"""

    def __init__(self):
        super().__init__("Router")

    def route(self, user_input: str) -> str:
        """识别意图并返回"""
        # 规则1: 问句检测
        if any(c in user_input for c in '？？'):
            return "explore"

        # 规则2: 关键词匹配
        intent_scores = {}
        for intent, keywords in INTENT_MAP.items():
            score = sum(1 for kw in keywords if kw in user_input)
            if score > 0:
                intent_scores[intent] = score

        if not intent_scores:
            return "explore"

        # 规则3: 优先级意图（export/websearch/modify）在平局时优先
        max_score = max(intent_scores.values())
        top_intents = [i for i, s in intent_scores.items() if s == max_score]
        if len(top_intents) > 1:
            for pi in _PRIORITY_INTENTS:
                if pi in top_intents:
                    return pi

        best = max(intent_scores, key=intent_scores.get)

        # generate 需要比 explore 分高
        if best == "generate" and "explore" in intent_scores:
            if intent_scores.get("generate", 0) <= intent_scores.get("explore", 0):
                return "explore"

        return best

    def process(self, user_input: str, project_id: str = None, **kwargs) -> dict:
        """路由入口 — 返回路由结果"""
        self.reset()
        intent = self.route(user_input)
        self.think(f"意图识别 → {intent}")

        # 分配给对应的 Agent
        agent_map = {
            "explore": "researcher",
            "summarize": "researcher",
            "websearch": "researcher",
            "generate": "writer",
            "modify": "writer",
            "framework": "writer",
            "export": "writer",
            "chart": "analyst",
            "figures": "analyst",
            "analyze": "analyst",
        }

        target_agent = agent_map.get(intent, "researcher")

        return {
            "intent": intent,
            "target_agent": target_agent,
            "thinking_steps": self.thinking_steps,
        }
