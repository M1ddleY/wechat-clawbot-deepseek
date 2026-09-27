"""腾讯 iLink (ClawBot) 协议层。

协议基线：@tencent-weixin/openclaw-weixin 2.4.6
接入域：https://ilinkai.weixin.qq.com
"""
from __future__ import annotations

import asyncio
import base64
import json
import secrets
import time
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "2.4.6"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 6)  # = 132102
BOT_AGENT = "weixin-ClawBot-API/1.2.0 (python)"

QR_STATUS_TIMEOUT = 35
LONG_POLL_TIMEOUT = 35
API_TIMEOUT = 15
CONFIG_TIMEOUT = 10
RETRY_DELAY = 2
BACKOFF_DELAY = 30
MAX_CONSECUTIVE_FAILURES = 3


class ILinkAPIError(RuntimeError):
    """iLink 的 HTTP、JSON 或业务层错误。"""

    def __init__(self, message, *, path="", status=None, ret=None, errcode=None,
                 response=None, network_type=None):
        super().__init__(message)
        self.path = path
        self.status = status
        self.ret = ret
        self.errcode = errcode
        self.response = response or {}
        self.network_type = network_type

    @property
    def code(self):
        return self.ret if self.ret not in (None, 0) else self.errcode

    @property
    def is_stale_token(self):
        return self.code == -14


def make_common_headers() -> dict:
    return {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }


def make_headers(token: Optional[str] = None) -> dict:
    uin = str(secrets.randbits(32))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
        **make_common_headers(),
    }
    if token and str(token).strip():
        headers["Authorization"] = "Bearer {}".format(str(token).strip())
    return headers


def base_info() -> dict:
    return {
        "channel_version": CHANNEL_VERSION,
        "bot_agent": BOT_AGENT,
    }


def generate_client_id() -> str:
    return "openclaw-weixin:%d-%s" % (int(time.time() * 1000), secrets.token_hex(4))


def _parse_json_response(text: str, path: str, status: int) -> dict:
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ILinkAPIError("GET/POST {} 返回非 JSON".format(path), path=path, status=status) from exc
    if not isinstance(data, dict):
        raise ILinkAPIError("GET/POST {} 返回非对象".format(path), path=path, status=status)
    return data


def ensure_business_success(data: dict, path: str) -> dict:
    ret = data.get("ret")
    errcode = data.get("errcode")
    if ret not in (None, 0) or errcode not in (None, 0):
        message = data.get("errmsg") or "iLink 业务请求失败"
        raise ILinkAPIError(
            "{0} ret={1!r} errcode={2!r}: {3}".format(path, ret, errcode, message),
            path=path, ret=ret, errcode=errcode, response=data,
        )
    return data


async def api_get(session: aiohttp.ClientSession, path: str, base_url: Optional[str] = None,
                  *, timeout: Optional[float] = QR_STATUS_TIMEOUT, long_poll: bool = False) -> dict:
    url = "{0}/{1}".format((base_url or BASE_URL).rstrip("/"), path.lstrip("/"))
    try:
        t = aiohttp.ClientTimeout(total=timeout) if timeout else None
        async with session.get(url, headers=make_common_headers(), timeout=t) as res:
            text = await res.text()
            if not 200 <= res.status < 300:
                error_data = {}
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        error_data = parsed
                except (TypeError, ValueError):
                    pass
                raise ILinkAPIError(
                    "GET {0} HTTP {1}: {2}".format(path, res.status, error_data.get("errmsg", "")).rstrip(),
                    path=path, status=res.status, ret=error_data.get("ret"),
                    errcode=error_data.get("errcode"), response=error_data,
                )
            return _parse_json_response(text, path, res.status)
    except asyncio.TimeoutError as exc:
        if long_poll:
            return {"status": "wait", "_timeout": True}
        raise ILinkAPIError("GET {} 超时".format(path), path=path, network_type="timeout") from exc
    except asyncio.CancelledError:
        raise
    except ILinkAPIError:
        raise
    except (aiohttp.ClientError, OSError) as exc:
        raise ILinkAPIError("GET {0} 网络错误: {1}".format(path, exc), path=path,
                            network_type=type(exc).__name__) from exc


async def api_post(session: aiohttp.ClientSession, path: str, body: dict,
                   token: Optional[str] = None, base_url: Optional[str] = None,
                   *, timeout: Optional[float] = API_TIMEOUT, long_poll: bool = False,
                   fallback_cursor: str = "") -> dict:
    url = "{0}/{1}".format((base_url or BASE_URL).rstrip("/"), path.lstrip("/"))
    try:
        t = aiohttp.ClientTimeout(total=timeout) if timeout else None
        async with session.post(url, json=body, headers=make_headers(token), timeout=t) as res:
            text = await res.text()
            if not 200 <= res.status < 300:
                error_data = {}
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        error_data = parsed
                except (TypeError, ValueError):
                    pass
                raise ILinkAPIError(
                    "POST {0} HTTP {1}: {2}".format(path, res.status, error_data.get("errmsg", "")).rstrip(),
                    path=path, status=res.status, ret=error_data.get("ret"),
                    errcode=error_data.get("errcode"), response=error_data,
                )
            return _parse_json_response(text, path, res.status)
    except asyncio.TimeoutError as exc:
        if long_poll:
            return {"ret": 0, "msgs": [], "get_updates_buf": fallback_cursor, "_timeout": True}
        raise ILinkAPIError("POST {} 超时".format(path), path=path, network_type="timeout") from exc
    except asyncio.CancelledError:
        raise
    except ILinkAPIError:
        raise
    except (aiohttp.ClientError, OSError) as exc:
        raise ILinkAPIError("POST {0} 网络错误: {1}".format(path, exc), path=path,
                            network_type=type(exc).__name__) from exc


# ---------------- 消息原语 ----------------

async def get_updates(session, token, base_url, get_updates_buf: str,
                      timeout: float = LONG_POLL_TIMEOUT) -> dict:
    result = await api_post(
        session,
        "ilink/bot/getupdates",
        {"get_updates_buf": get_updates_buf, "base_info": base_info()},
        token,
        base_url or BASE_URL,
        timeout=timeout,
        long_poll=True,
        fallback_cursor=get_updates_buf,
    )
    ensure_business_success(result, "getupdates")
    return result


async def send_message(session, token, base_url, to_id: str, context_token: str, text: str) -> dict:
    result = await api_post(
        session,
        "ilink/bot/sendmessage",
        {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_id,
                "client_id": generate_client_id(),
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
                "item_list": [{"type": 1, "text_item": {"text": text}}],
            },
            "base_info": base_info(),
        },
        token,
        base_url or BASE_URL,
    )
    ensure_business_success(result, "sendmessage")
    return result


async def send_typing(session, token, base_url, user_id: str, typing_ticket: str, status: int) -> bool:
    if not user_id or not typing_ticket:
        return False
    try:
        result = await api_post(
            session,
            "ilink/bot/sendtyping",
            {
                "ilink_user_id": user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": base_info(),
            },
            token,
            base_url or BASE_URL,
            timeout=CONFIG_TIMEOUT,
        )
        ensure_business_success(result, "sendtyping")
        return True
    except ILinkAPIError as exc:
        if exc.is_stale_token:
            raise
        return False


async def get_typing_ticket(session, token, base_url, user_id: str, context_token: str,
                            cache: dict) -> str:
    now = time.time()
    entry = cache.get(user_id) if isinstance(cache.get(user_id), dict) else None
    if entry is None or now >= float(entry.get("next_fetch_at", 0)):
        try:
            result = await api_post(
                session,
                "ilink/bot/getconfig",
                {"ilink_user_id": user_id, "context_token": context_token, "base_info": base_info()},
                token,
                base_url or BASE_URL,
                timeout=CONFIG_TIMEOUT,
            )
            ensure_business_success(result, "getconfig")
            cache[user_id] = {
                "typing_ticket": str(result.get("typing_ticket") or ""),
                "next_fetch_at": now + secrets.randbelow(24 * 60 * 60 + 1),
            }
        except ILinkAPIError as exc:
            if exc.is_stale_token:
                raise
            cache[user_id] = {"typing_ticket": "", "next_fetch_at": now + 2, "retry_delay": 2}
    cached = cache.get(user_id) or {}
    return str(cached.get("typing_ticket") or "")


async def notify_lifecycle(session, endpoint, token, base_url):
    """发送 notifystart / notifystop 生命周期通知（尽力而为）。"""
    try:
        result = await api_post(
            session,
            endpoint,
            {"base_info": base_info()},
            token,
            base_url or BASE_URL,
            timeout=CONFIG_TIMEOUT,
        )
        ensure_business_success(result, endpoint)
        return True
    except ILinkAPIError as exc:
        if exc.is_stale_token:
            raise
        print("[生命周期] {} 通知失败: {}".format(endpoint, exc))
        return False


def extract_message_text(msg: dict) -> str:
    parts = []
    for item in msg.get("item_list") or []:
        if not isinstance(item, dict):
            continue
        text_item = item.get("text_item") or {}
        if text_item.get("text"):
            parts.append(str(text_item["text"]))
            continue
        voice_item = item.get("voice_item") or {}
        if voice_item.get("text"):
            parts.append(str(voice_item["text"]))
    return "\n".join(parts).strip()
