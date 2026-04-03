"""联网搜索工具"""
import json
import logging
import re
import urllib.parse
import urllib.request

from src.core.llm import llm_client

logger = logging.getLogger(__name__)


def web_search(query: str, top_k: int = 5) -> list[dict]:
    """使用 Bing 搜索 API 或 DuckDuckGo 获取网页摘要"""
    results = []

    # 方法1: 用 LLM 基于自身知识回答（作为"联网搜索"的补充）
    # 方法2: 尝试用 urllib 抓取搜索结果

    try:
        # 使用 DuckDuckGo Instant Answer API（无需 API Key）
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # 提取摘要
        if data.get("AbstractText"):
            results.append({
                "title": data.get("AbstractSource", "DuckDuckGo"),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
                "source": "web",
            })

        # 提取相关主题
        for topic in (data.get("RelatedTopics") or [])[:top_k - 1]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:60],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                    "source": "web",
                })

    except Exception as e:
        logger.warning(f"DuckDuckGo 搜索失败: {e}")

    return results[:top_k]


def web_search_with_llm_summary(query: str) -> dict:
    """联网搜索 + LLM 总结，返回搜索结果和总结"""
    search_results = web_search(query)

    # 让 LLM 基于自身知识补充（标注为 llm_reasoning）
    llm_prompt = f"""基于你的知识，简要回答以下问题（100字以内）。请明确标注你的回答是基于自身知识。

问题：{query}"""

    llm_response = llm_client.chat(
        [{"role": "user", "content": llm_prompt}],
        temperature=0.5, max_tokens=300
    )

    return {
        "web_results": search_results,
        "llm_knowledge": llm_response,
        "query": query,
    }
