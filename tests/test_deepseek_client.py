"""DeepSeek 客户端与配置掩码测试（不依赖真实网络）。"""

from deepseek_client import DeepSeekClient


def test_mask_key():
    from config import mask_key
    key = "sk-abcdefghijklmn"  # 17 字符
    masked = mask_key(key)
    assert masked.startswith("sk-ab")
    assert masked.endswith("jklmn")
    # 中间字符全部被星号替换
    assert masked[5:-5] == "*" * (len(key) - 10)
    # 长度不变
    assert len(masked) == len(key)
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
