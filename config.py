"""配置加载与掩码。敏感字段不入版控。"""
from __future__ import annotations

import json
import os

CONFIG_FILE = os.environ.get("WXBOT_CONFIG", "config.json")
DEFAULT_PROMPT = "你是「炸鸡」，一个活泼、贴心、话不多的AI助手。用中文简洁自然地回复，避免长篇大论。"


def mask_key(key: str) -> str:
    if not key:
        return "<empty>"
    if len(key) <= 10:
        return key
    return key[:5] + "*" * (len(key) - 10) + key[-5:]


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {"provider": "deepseek", "deepseek": {"api_key": "", "prompt": DEFAULT_PROMPT}}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"无法读取 {CONFIG_FILE}: {exc}") from exc
    cfg.setdefault("provider", "deepseek")
    cfg.setdefault("deepseek", {})
    deepseek = cfg["deepseek"]
    deepseek.setdefault("base_url", "https://api.deepseek.com")
    deepseek.setdefault("model", "deepseek-v4-flash")
    deepseek.setdefault("prompt", DEFAULT_PROMPT)
    deepseek.setdefault("api_key", "")
    return cfg


def get_deepseek_cfg() -> dict:
    cfg = load_config()
    return dict(cfg["deepseek"])
