# -*- coding: utf-8 -*-
"""Verify the thinking-budget fix against real Zhipu API.

Run: cd C:/Users/77230/CiteWise && OPENAI_API_KEY=<key> LLM_MODEL=glm-4.7 \
     python tests/test_thinking_budget.py

The puzzle prompt below previously produced EMPTY content (finish=length,
reasoning_tokens == max_tokens == 4000). After the fix both sync and stream
paths must return non-empty content.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.core.llm import llm_client, _request_max_tokens, _is_thinking_model

Q = ("三个 missionaries 和三个 cannibals 要过河，船最多载两人，任意一岸 cannibals 数量"
     "超过 missionaries 时 missionaries 会被吃掉。请一步一步严格推演每一步的合法状态转移，"
     "穷举验证不存在更短方案，然后给出完整渡河步骤表。")


def test_budget_floor():
    assert _request_max_tokens("glm-4.7", 4000) == 16000
    assert _request_max_tokens("glm-4.5-air", 4000) == 16000
    assert _request_max_tokens("glm-4-flash", 4000) == 4000
    assert _request_max_tokens("glm-4.7", 20000) == 20000
    assert _is_thinking_model("glm-4.7") and _is_thinking_model("glm-z1-air")
    assert not _is_thinking_model("glm-4-flash")
    print("[PASS] budget floor helpers")


def test_sync_puzzle():
    out = llm_client.chat([{"role": "user", "content": Q}],
                          temperature=0.7, max_tokens=4000)
    assert out and len(out) > 50, f"sync chat returned empty/short: {out!r}"
    print(f"[PASS] sync chat, content_len={len(out)}, preview={out[:60]!r}")


async def _stream_puzzle():
    tokens = []
    async for t in llm_client.achat_stream([{"role": "user", "content": Q}],
                                            temperature=0.7, max_tokens=4000):
        tokens.append(t)
    text = "".join(tokens)
    assert len(text) > 50, f"stream returned empty: {text!r}"
    print(f"[PASS] stream chat, content_len={len(text)}, preview={text[:60]!r}")


def test_stream_puzzle():
    asyncio.run(_stream_puzzle())


if __name__ == "__main__":
    test_budget_floor()
    test_sync_puzzle()
    test_stream_puzzle()
    print("ALL PASS")
