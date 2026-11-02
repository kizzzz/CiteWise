"""LLM 调用层 - 统一封装智谱 GLM (OpenAI 兼容接口)

支持同步 + 异步 + 流式调用。
"""
import json
import os
import re
import logging
from typing import AsyncGenerator, Optional
from openai import OpenAI
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL

# 确保 stdout/stderr 使用 UTF-8（Windows 兼容）
if os.name == 'nt':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    try:
        import sys
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用异常"""
    pass


# 思考型 GLM 模型（glm-4.5/4.6/4.7、glm-z1 系列）的思考 token 计入 max_tokens。
# 历史默认预算 4000 会被长推理整个吃掉：finish_reason=length、正文为空、且不抛异常，
# 用户侧表现为"回答为空"。对思考型模型把请求预算抬到下限，正文才有输出空间。
_THINKING_MODEL_PREFIXES = ("glm-4.5", "glm-4.6", "glm-4.7")
_THINKING_TOKEN_FLOOR = 16000


def _is_thinking_model(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith(_THINKING_MODEL_PREFIXES) or "glm-z" in m


def _request_max_tokens(model: str, max_tokens: int) -> int:
    if _is_thinking_model(model):
        return max(max_tokens, _THINKING_TOKEN_FLOOR)
    return max_tokens


class LLMClient:
    """统一的 LLM 调用客户端"""

    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
        self._async_client = None
        self.model = LLM_MODEL

    def _get_api_key(self, override: Optional[str] = None) -> str:
        """Get API key: override > default"""
        return override or OPENAI_API_KEY

    _override_key = None
    _override_url = None

    def set_override(self, api_key: str, base_url: str = None):
        """Temporarily override API key and base URL for user-provided keys."""
        self._override_key = api_key
        self._override_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url or OPENAI_BASE_URL)
        self._async_client = None  # Force re-creation

    def clear_override(self):
        """Reset to default API key."""
        self._override_key = None
        self._override_url = None
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        self._async_client = None

    @property
    def async_client(self):
        """延迟初始化异步客户端"""
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(
                api_key=OPENAI_API_KEY,
                base_url=OPENAI_BASE_URL,
            )
        return self._async_client

    def get_async_client(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """Get async client with optional user API key and base URL"""
        key = self._get_api_key(api_key)
        url = base_url or OPENAI_BASE_URL
        if key != OPENAI_API_KEY or url != OPENAI_BASE_URL:
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=key, base_url=url)
        return self.async_client

    # ===== 同步接口 (兼容旧代码) =====

    def chat(self, messages: list[dict], temperature: float = 0.7,
             max_tokens: int = 4000, model: Optional[str] = None) -> str:
        """基础对话接口

        Args:
            model: Optional model override. If None, uses ``self.model`` (the
                project default, currently ``glm-4.7``). Callers that need a
                specific model (e.g. submit endpoints pinning to glm-4.7 even
                if the default changes) pass it explicitly here.
        """
        use_model = model or self.model
        kwargs = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": _request_max_tokens(use_model, max_tokens),
        }
        try:
            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content
            if (not content and choice.finish_reason == "length"
                    and _is_thinking_model(use_model)):
                # 思考吃满预算、正文为空：关闭思考重试一次
                logger.warning(f"LLM 思考耗尽预算(max_tokens={kwargs['max_tokens']})，关闭思考重试: {use_model}")
                response = self.client.chat.completions.create(
                    **{**kwargs, "max_tokens": max_tokens,
                       "extra_body": {"thinking": {"type": "disabled"}}},
                )
                content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise LLMError(f"LLM 调用失败: {str(e)}") from e

    def chat_json(self, messages: list[dict], temperature: float = 0.3,
                  max_tokens: int = 4000, max_retries: int = 2,
                  model: Optional[str] = None) -> dict:
        """带 JSON 格式校验的对话，自动重试"""
        current_messages = list(messages)
        for attempt in range(max_retries + 1):
            text = self.chat(current_messages, temperature=temperature,
                             max_tokens=max_tokens, model=model)
            try:
                text = self._extract_json(text)
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                if attempt < max_retries:
                    current_messages = list(messages) + [
                        {"role": "user", "content": "上次输出格式有误，请严格按 JSON 格式输出，不要包含任何其他文字。只输出 JSON。"}
                    ]
                    logger.warning(f"JSON 格式错误，第 {attempt+1} 次重试")
                else:
                    logger.error(f"JSON 解析最终失败: {text[:200]}")
                    raise LLMError(f"JSON 格式解析最终失败: {text[:200]}")

    # ===== 异步接口 (LangGraph 流式用) =====

    async def achat(self, messages: list[dict], temperature: float = 0.7,
                    max_tokens: int = 4000) -> str:
        """异步对话接口"""
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=_request_max_tokens(self.model, max_tokens),
            )
            choice = response.choices[0]
            content = choice.message.content
            if (not content and choice.finish_reason == "length"
                    and _is_thinking_model(self.model)):
                logger.warning(f"LLM 思考耗尽预算，关闭思考重试: {self.model}")
                response = await self.async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            logger.error(f"LLM 异步调用失败: {e}")
            raise LLMError(f"LLM 异步调用失败: {str(e)}") from e

    async def achat_stream(self, messages: list[dict], temperature: float = 0.7,
                           max_tokens: int = 4000, api_key: Optional[str] = None,
                           base_url: Optional[str] = None, model: Optional[str] = None) -> AsyncGenerator[str, None]:
        """异步流式对话 — 逐 token yield"""
        client = self.get_async_client(api_key, base_url)
        use_model = model or self.model
        kwargs = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": _request_max_tokens(use_model, max_tokens),
            "stream": True,
        }
        try:
            for _attempt in range(2):
                yielded_any = False
                finish_reason = None
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    if delta and delta.content:
                        yielded_any = True
                        yield delta.content
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                if yielded_any or finish_reason != "length" or not _is_thinking_model(use_model):
                    break
                # 预算被思考全部耗尽且未 yield 任何内容（用户无感知），关闭思考重试一次
                logger.warning(f"LLM 流式思考耗尽预算(max_tokens={kwargs['max_tokens']})，关闭思考重试: {use_model}")
                kwargs = {
                    **kwargs,
                    "max_tokens": max_tokens,
                    "extra_body": {"thinking": {"type": "disabled"}},
                }
        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            raise LLMError(f"LLM 流式调用失败: {str(e)}") from e

    async def achat_json(self, messages: list[dict], temperature: float = 0.3,
                         max_tokens: int = 4000, max_retries: int = 2) -> dict:
        """异步 JSON 对话"""
        current_messages = list(messages)
        for attempt in range(max_retries + 1):
            text = await self.achat(current_messages, temperature=temperature, max_tokens=max_tokens)
            try:
                text = self._extract_json(text)
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                if attempt < max_retries:
                    current_messages = list(messages) + [
                        {"role": "user", "content": "上次输出格式有误，请严格按 JSON 格式输出，不要包含任何其他文字。只输出 JSON。"}
                    ]
                    logger.warning(f"JSON 异步格式错误，第 {attempt+1} 次重试")
                else:
                    raise LLMError(f"JSON 异步解析最终失败: {text[:200]}")

    # ===== 工具方法 =====

    def _extract_json(self, text: str) -> str:
        """从 LLM 输出中提取 JSON 块"""
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text, re.DOTALL)
        if match:
            extracted = match.group(1).strip()
            inner_match = re.match(r'^```(?:json)?\s*\n?([\s\S]*?)\n?```$', extracted, re.DOTALL)
            if inner_match:
                extracted = inner_match.group(1).strip()
            return extracted
        text = text.strip()
        if text.startswith('{') or text.startswith('['):
            return text
        return text


# 全局单例
llm_client = LLMClient()
