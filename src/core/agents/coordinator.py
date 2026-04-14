"""CoordinatorAgent — 兼容层，委托给 LangGraph"""
import logging

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """协调 Agent — 统一入口，委托 LangGraph 执行

    主对话走 LangGraph graph（在 chat.py 中直接调用），
    此类保留用于子对话和同步调用兼容。
    """

    def __init__(self):
        super().__init__("Coordinator")

    def process(self, user_input: str, project_id: str = None, **kwargs) -> dict:
        """同步处理 — 调用 LangGraph graph.invoke"""
        from src.core.graph import get_graph

        self.reset()
        graph = get_graph()

        intent_override = kwargs.get("intent")
        input_state = {
            "user_input": user_input,
            "project_id": project_id,
            "thinking_steps": [],
            "agent_events": [],
        }
        if intent_override:
            input_state["intent"] = intent_override
        if kwargs.get("target_content"):
            input_state["target_content"] = kwargs["target_content"]
        if kwargs.get("section_name"):
            input_state["section_name"] = kwargs["section_name"]
        if kwargs.get("gen_params"):
            input_state["gen_params"] = kwargs["gen_params"]

        config = {"configurable": {"thread_id": project_id or "default"}}
        result = graph.invoke(input_state, config)

        # 确保 thinking_steps 汇总
        result["thinking_steps"] = result.get("thinking_steps", []) + self.thinking_steps
        return result


# 全局单例
coordinator = CoordinatorAgent()
