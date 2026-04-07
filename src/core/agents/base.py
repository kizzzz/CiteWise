"""Agent 基类 — 定义统一的接口和思考过程记录"""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """所有 Agent 的基类"""

    def __init__(self, name: str):
        self.name = name
        self.thinking_steps: list[str] = []

    def think(self, step: str) -> None:
        """记录思考步骤"""
        self.thinking_steps.append(step)
        logger.info(f"[{self.name}] {step}")

    def reset(self) -> None:
        """重置思考步骤"""
        self.thinking_steps = []

    @abstractmethod
    def process(self, user_input: str, project_id: str | None = None, **kwargs) -> dict:
        """处理输入，返回结果 — 子类必须实现"""
        ...
