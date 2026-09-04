import asyncio

import pytest

from deepseek_client import DeepSeekClient


async def _stub_call(messages):
    # 模拟 _chat_completion
    messages.append({"role": "assistant", "content": "好的"})
    return "好的"


def test_mask_key():
    from config import mask_key
    assert mask_key("sk-abcdefghijklmn") == "sk-ab******klmn"[:15]
    assert mask_key("short") == "short"


def test_sessions_per_user():
    c = DeepSeekClient("k", "https://api.deepseek.com", "m", "p", max_history=2)
    c.sessions["a"] = [{"role": "user", "content": "x"}]
    c.sessions["b"] = [{"role": "user", "content": "y"}]
    assert c.sessions["a"] != c.sessions["b"]


def test_slide_window():
    c = DeepSeekClient("k", "https://api.deepseek.com", "m", "p", max_history=3)
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    trimmed = history[-c.max_history:]
    assert len(trimmed) == 3
    assert trimmed[-1]["content"] == "9"


def test_clear():
    c = DeepSeekClient("k", "https://api.deepseek.com", "m", "p")
    c.sessions["a"] = [{"role": "user", "content": "x"}]
    c.clear("a")
    assert "a" not in c.sessions
