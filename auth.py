"""微信 iLink 登录：扫码状态机、凭证持久化、二维码渲染。"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import time
from urllib.parse import quote

import aiohttp

from ilink_client import (
    BASE_URL,
    QR_STATUS_TIMEOUT,
    ILinkAPIError,
    api_get,
    api_post,
    ensure_business_success,
)

STATE_FILE = "weixin_state.json"
QRCODE_SCAN_TIMEOUT = 480
MAX_QR_REFRESH = 3
QRCODE_PNG = "login_qrcode.png"


def _empty_state() -> dict:
    return {
        "bot_token": "",
        "baseurl": "",
        "ilink_bot_id": "",
        "ilink_user_id": "",
        "get_updates_buf": "",
    }


def load_state() -> dict:
    state = _empty_state()
    if not os.path.exists(STATE_FILE):
        return state
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            state.update({k: raw.get(k, v) for k, v in state.items()})
    except (OSError, ValueError, TypeError) as exc:
        print("[状态] 无法读取 {}，将从空状态开始: {}".format(STATE_FILE, exc))
    return state


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as exc:
        print("[状态] 保存失败: {}".format(exc))


# ---------------- 二维码渲染 ----------------

def _render_generated_qr(content: str) -> None:
    try:
        import qrcode
    except Exception:
        print("未安装 qrcode/Pillow，无法渲染二维码，请用下方链接打开。")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(content)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    print()
    for row in matrix:
        print("".join("\u2588\u2588" if cell else "  " for cell in row))
    print()


def _save_qr_png(content: str) -> bool:
    """尝试把 content 保存成 PNG 图片，成功返回 True。"""
    if not content:
        return False
    try:
        # data:image/png;base64,...
        if content.startswith("data:image/"):
            _, b64 = content.split(",", 1)
            raw = base64.b64decode(b64)
        else:
            # 直接 base64 图片字节
            raw = base64.b64decode(content)
        with open(QRCODE_PNG, "wb") as f:
            f.write(raw)
        print("二维码图片已保存到: {}".format(QRCODE_PNG))
        return True
    except Exception:
        return False


async def _render_qr_from_url(session, url: str) -> bool:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as res:
            data = await res.read()
        with open(QRCODE_PNG, "wb") as f:
            f.write(data)
        print("二维码图片已保存到: {}".format(QRCODE_PNG))
        return True
    except Exception:
        return False


async def render_qr(session, content: str) -> None:
    if not content:
        return
    print("扫码地址: {}".format(content))
    if content.startswith("data:image/") or content.startswith("<svg"):
        if _save_qr_png(content):
            return
    elif content.startswith("http"):
        if await _render_qr_from_url(session, content):
            return
    else:
        if _save_qr_png(content):
            return
    _render_generated_qr(content)


# ---------------- 底层登录原语 ----------------

async def fetch_login_qrcode(session, local_token_list=None):
    tokens = []
    for t in local_token_list or []:
        t = str(t or "").strip()
        if t and t not in tokens:
            tokens.append(t)
    data = await api_post(
        session,
        "ilink/bot/get_bot_qrcode?bot_type=3",
        {"local_token_list": tokens[:10]},
        None,
        BASE_URL,
        timeout=None,
    )
    ensure_business_success(data, "get_bot_qrcode")
    if data.get("qrcode"):
        return data
    # 旧版 GET 兜底
    data = await api_get(session, "ilink/bot/get_bot_qrcode?bot_type=3", BASE_URL, timeout=None)
    ensure_business_success(data, "get_bot_qrcode")
    return data


async def poll_login_status(session, qrcode: str, base_url: str = BASE_URL, verify_code: str = None) -> dict:
    endpoint = "ilink/bot/get_qrcode_status?qrcode={}".format(quote(qrcode, safe=""))
    if verify_code:
        endpoint += "&verify_code={}".format(quote(verify_code, safe=""))
    status = await api_get(session, endpoint, base_url or BASE_URL,
                           timeout=QR_STATUS_TIMEOUT, long_poll=True)
    if status.get("_timeout"):
        return {"status": "wait"}
    ensure_business_success(status, "get_qrcode_status")
    state = status.get("status", "")

    if state == "confirmed" or status.get("bot_token"):
        bot_token = status.get("bot_token")
        ilink_bot_id = status.get("ilink_bot_id")
        if not bot_token or not ilink_bot_id:
            return {"login_error": "confirmed 响应缺少 bot_token 或 ilink_bot_id"}
        return {
            "bot_token": bot_token,
            "baseurl": status.get("baseurl") or status.get("base_url") or base_url or BASE_URL,
            "ilink_bot_id": ilink_bot_id,
            "ilink_user_id": status.get("ilink_user_id", ""),
        }
    if state == "binded_redirect" or status.get("binded_redirect"):
        return {"already_connected": True}
    if state == "expired":
        return {"expired": True}
    if state == "scaned_but_redirect":
        redirect_host = status.get("redirect_host")
        if redirect_host:
            redirect_base = str(redirect_host)
            if not redirect_base.startswith("http"):
                redirect_base = "https://" + redirect_base
            return {"redirect_base": redirect_base.rstrip("/")}
        return {}
    if state == "scaned":
        return {"scanned": True, "verify_code_accepted": bool(verify_code)}
    if state in ("need_verifycode", "verify_code_blocked") or status.get("need_verifycode"):
        if state == "verify_code_blocked":
            return {"verify_code_blocked": True}
        return {"need_verifycode": True, "retry_verifycode": bool(verify_code)}
    return {"status": state}


async def wait_login_confirmation(session, qrcode: str, base_url: str = BASE_URL,
                                 timeout_seconds: float = None, allow_already_connected: bool = False) -> dict:
    timeout_seconds = timeout_seconds or QRCODE_SCAN_TIMEOUT
    deadline = time.time() + timeout_seconds
    current_base_url = base_url or BASE_URL
    pending_verify_code = None
    scanned_printed = False

    while True:
        if time.time() >= deadline:
            return {"timeout": True}
        try:
            result = await poll_login_status(session, qrcode, current_base_url, pending_verify_code)
        except ILinkAPIError as exc:
            print("[登录] 轮询失败({}): {}，稍后重试".format(exc.network_type or "业务", exc))
            await asyncio.sleep(1)
            continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[登录] 轮询异常: {}，稍后重试".format(exc))
            await asyncio.sleep(1)
            continue

        if result.get("bot_token"):
            return result
        if result.get("login_error"):
            return result
        if result.get("already_connected"):
            return result if allow_already_connected else {"already_connected": True}
        if result.get("expired") or result.get("verify_code_blocked"):
            return result
        if result.get("redirect_base"):
            current_base_url = result["redirect_base"]
            print("[登录] 扫码轮询切换到新节点: {}".format(current_base_url))
            continue
        if result.get("scanned"):
            if pending_verify_code and result.get("verify_code_accepted"):
                pending_verify_code = None
            if not scanned_printed:
                print("[登录] 已扫码，等待手机端确认...")
                scanned_printed = True
        if result.get("need_verifycode"):
            prompt = ("请重新输入数字配对码: " if result.get("retry_verifycode")
                      else "请输入手机微信显示的数字配对码: ")
            pending_verify_code = (await asyncio.to_thread(input, prompt)).strip()
            continue
        await asyncio.sleep(1)


async def login(session, existing_state: dict = None, on_qrcode=None) -> dict:
    """执行官方扫码登录，返回 {bot_token, baseurl, ilink_bot_id, ...}。"""
    existing_state = existing_state or {}
    refresh_count = 1
    deadline = time.time() + QRCODE_SCAN_TIMEOUT

    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("登录等待超时，请重新运行后再试。")
        data = await fetch_login_qrcode(session, [existing_state.get("bot_token")])
        qrcode = data.get("qrcode")
        if not qrcode:
            raise RuntimeError("二维码响应缺少 qrcode")
        qrcode_img_content = data.get("qrcode_img_content", "")
        qr_content = str(qrcode_img_content or qrcode)
        if on_qrcode:
            result = on_qrcode(qr_content)
            if asyncio.iscoroutine(result):
                await result
        await render_qr(session, qr_content)
        print("[登录] 等待扫码...")

        remaining = deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("登录等待超时，请重新运行后再试。")
        login_result = await wait_login_confirmation(
            session, qrcode, BASE_URL, timeout_seconds=remaining, allow_already_connected=True,
        )

        if login_result.get("bot_token"):
            return login_result
        if login_result.get("already_connected"):
            old_token = str(existing_state.get("bot_token") or "").strip()
            if old_token:
                print("[登录] 服务端提示已连接过，复用本地保存的 token。")
                return {
                    "bot_token": old_token,
                    "baseurl": existing_state.get("baseurl") or BASE_URL,
                    "ilink_bot_id": existing_state.get("ilink_bot_id", ""),
                    "ilink_user_id": existing_state.get("ilink_user_id", ""),
                    "already_connected": True,
                }
            print("[登录] 服务端提示此端已连接过，但本地没有可复用 token，将重新生成二维码。")
        elif login_result.get("expired"):
            print("[登录] 二维码已过期，正在重新生成...")
        elif login_result.get("verify_code_blocked"):
            print("[登录] 多次输入配对码错误，正在刷新二维码...")
        elif login_result.get("login_error"):
            raise RuntimeError(login_result["login_error"])
        elif login_result.get("timeout"):
            raise RuntimeError("登录等待超时，请重新运行后再试。")

        refresh_count += 1
        if refresh_count > MAX_QR_REFRESH:
            raise RuntimeError("二维码多次失效或登录失败，请稍后重试。")


def apply_new_login(state: dict, login_result: dict) -> dict:
    """把登录结果合并进持久化 state。"""
    state["bot_token"] = str(login_result.get("bot_token") or "")
    state["baseurl"] = str(login_result.get("baseurl") or BASE_URL)
    state["ilink_bot_id"] = str(login_result.get("ilink_bot_id") or "")
    state["ilink_user_id"] = str(login_result.get("ilink_user_id") or "")
    # 账号发生变化时清空游标
    save_state(state)
    return state
