"""LLM 调用层 - 统一封装智谱 GLM (OpenAI 兼容接口)"""
import json
import re
import logging
from openai import OpenAI
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)


class LLMClient:
    """统一的 LLM 调用客户端"""

    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
        self.model = LLM_MODEL

    def chat(self, messages: list[dict], temperature: float = 0.7,
             max_tokens: int = 4000) -> str:
        """基础对话接口"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"[错误] LLM 调用失败: {str(e)}"

    def chat_json(self, messages: list[dict], temperature: float = 0.3,
                  max_tokens: int = 4000, max_retries: int = 2) -> dict:
        """带 JSON 格式校验的对话，自动重试"""
        for attempt in range(max_retries + 1):
            text = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
            try:
                text = self._extract_json(text)
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                if attempt < max_retries:
                    # 追加修正指令后重试（不修改原 messages）
                    retry_messages = list(messages) + [
                        {"role": "user", "content": "上次输出格式有误，请严格按 JSON 格式输出，不要包含任何其他文字。只输出 JSON。"}
                    ]
                    messages = retry_messages
                    logger.warning(f"JSON 格式错误，第 {attempt+1} 次重试")
                else:
                    logger.error(f"JSON 解析最终失败: {text[:200]}")
                    return {"error": "format_failed", "raw": text}

    def _extract_json(self, text: str) -> str:
        """从 LLM 输出中提取 JSON 块"""
        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 尝试直接解析
        text = text.strip()
        if text.startswith('{') or text.startswith('['):
            return text
        return text


# 全局单例
llm_client = LLMClient()
