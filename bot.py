"""微信 ClawBot + DeepSeek 自动回复机器人主程序。"""
from __future__ import annotations

import asyncio
import time
import aiohttp

import auth
from config import get_deepseek_cfg, mask_key
from deepseek_client import DeepSeekClient
from ilink_client import (
    BACKOFF_DELAY,
    BASE_URL,
    MAX_CONSECUTIVE_FAILURES,
    RETRY_DELAY,
    ILinkAPIError,
    extract_message_text,
    get_typing_ticket,
    get_updates,
    send_message,
    send_typing,
)

HELP_MSG = (
    "你好，我是炸鸡～\n"
    "可用指令：\n"
    "/help  查看指令\n"
    "/clear 清空对话记忆\n"
    "/time  查看连接状态\n"
    "/重新连接  重新登录（扫码）"
)
MEDIA_TIP = "我暂时只支持文字消息哦，图片/语音先不处理啦～"


async def ensure_login(session, state: dict) -> dict:
    if state.get("bot_token"):
        return state
    print("[登录] 检测到未登录或凭证为空，开始扫码登录...")
    login_result = await auth.login(session, existing_state=state)
    return auth.apply_new_login(state, login_result)


async def send_reply(session, token_ref, base_url_ref, from_id, context_token, text) -> None:
    if not from_id or not context_token:
        return
    try:
        await send_message(session, token_ref[0], base_url_ref[0], from_id, context_token, text)
    except ILinkAPIError as exc:
        if exc.is_stale_token:
            raise
        print("[发送] 失败: {}".format(exc))


async def handle_message(session, client, msg, token_ref, base_url_ref,
                         typing_cache, state, relogin_flag, start_time) -> None:
    if not isinstance(msg, dict):
        return
    # 只处理用户发来的消息 (message_type == 1)
    if msg.get("message_type") != 1:
        return

    from_id = str(msg.get("from_user_id") or "")
    context_token = str(msg.get("context_token") or "")
    if not from_id or not context_token:
        print("[消息] 缺少 from_user_id/context_token，跳过")
        return

    text = extract_message_text(msg)
    if not text:
        print("[消息] 收到非文本/空消息，提示暂时不支持")
        await send_reply(session, token_ref, base_url_ref, from_id, context_token, MEDIA_TIP)
        return

    # ---- 指令处理 ----
    if text in ("/help", "/指令"):
        await send_reply(session, token_ref, base_url_ref, from_id, context_token, HELP_MSG)
        return
    if text == "/clear":
        client.clear(from_id)
        await send_reply(session, token_ref, base_url_ref, from_id, context_token, "已清空对话记忆～")
        return
    if text == "/time":
        elapsed = int(time.monotonic() - start_time[0])
        h, m = divmod(int(elapsed // 60), 60)
        await send_reply(session, token_ref, base_url_ref, from_id, context_token,
                         "连接运行时长：{} 小时 {} 分钟".format(h, m))
        return
    if text in ("/重新连接", "/reconnect"):
        relogin_flag[0] = True
        await send_reply(session, token_ref, base_url_ref, from_id, context_token,
                         "好的，正在重新连接，请留意新的二维码...")
        return

    # ---- AI 回复 ----
    typing_ticket = await get_typing_ticket(
        session, token_ref[0], base_url_ref[0], from_id, context_token, typing_cache
    )
    try:
        await send_typing(session, token_ref[0], base_url_ref[0], from_id, typing_ticket, 1)
        reply_text = await client.chat(from_id, text)
        await send_message(session, token_ref[0], base_url_ref[0], from_id, context_token, reply_text)
    except ILinkAPIError as exc:
        if exc.is_stale_token:
            raise
        print("[处理] 发送异常: {}".format(exc))
    except Exception as exc:
        print("[处理] AI/发送异常: {}".format(exc))
    finally:
        try:
            await send_typing(session, token_ref[0], base_url_ref[0], from_id, typing_ticket, 2)
        except Exception:
            pass


async def main() -> None:
    print("\n" + "=" * 50)
    print("   微信 ClawBot · 炸鸡自动回复")
    print("   (DeepSeek 驱动)")
    print("=" * 50)

    cfg = get_deepseek_cfg()
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key:
        print("\n[错误] 尚未配置 DeepSeek API Key。")
        print("请先在 config.json 的 deepseek.api_key 填入你的 Key，再重新运行。")
        return

    print("模型: {} | Key: {}".format(cfg.get("model"), mask_key(api_key)))
    client = DeepSeekClient(
        api_key=api_key,
        base_url=cfg.get("base_url"),
        model=cfg.get("model"),
        prompt=cfg.get("prompt"),
    )

    state = auth.load_state()
    typing_cache: dict = {}
    relogin_flag = [False]
    start_time = [time.monotonic()]
    consecutive_failures = 0

    async with aiohttp.ClientSession() as session:
        state = await ensure_login(session, state)
        token_ref = [state.get("bot_token") or ""]
        base_url_ref = [state.get("baseurl") or BASE_URL]
        get_updates_buf = str(state.get("get_updates_buf") or "")

        print("\n[运行] 机器人已上线。在微信里发消息给这个账号，炸鸡就会回你～")
        print("按 Ctrl+C 停止。\n")

        try:
            while True:
                try:
                    result = await get_updates(session, token_ref[0], base_url_ref[0], get_updates_buf)
                    get_updates_buf = str(result.get("get_updates_buf") or get_updates_buf)
                    state["get_updates_buf"] = get_updates_buf
                    auth.save_state(state)

                    for msg in result.get("msgs") or []:
                        await handle_message(
                            session, client, msg, token_ref, base_url_ref,
                            typing_cache, state, relogin_flag, start_time,
                        )

                    if relogin_flag[0]:
                        relogin_flag[0] = False
                        print("[登录] 收到重新连接指令，开始重新扫码...")
                        login_result = await auth.login(session, existing_state=state)
                        auth.apply_new_login(state, login_result)
                        token_ref[0] = state.get("bot_token") or ""
                        base_url_ref[0] = state.get("baseurl") or BASE_URL

                    consecutive_failures = 0
                except ILinkAPIError as exc:
                    if exc.is_stale_token:
                        print("[iLink] token 已失效(-14)，重新登录...")
                        login_result = await auth.login(session, existing_state=state)
                        auth.apply_new_login(state, login_result)
                        token_ref[0] = state.get("bot_token") or ""
                        base_url_ref[0] = state.get("baseurl") or BASE_URL
                        continue
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        delay = BACKOFF_DELAY
                        consecutive_failures = 0
                    else:
                        delay = RETRY_DELAY
                    print("[iLink] getupdates 失败({}): {}；{}s 后重试".format(
                        exc.network_type or "业务", exc, delay))
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        delay = BACKOFF_DELAY
                        consecutive_failures = 0
                    else:
                        delay = RETRY_DELAY
                    print("[主循环] 未分类异常: {}；{}s 后重试".format(exc, delay))
                    await asyncio.sleep(delay)
        except KeyboardInterrupt:
            print("\n已停止 Bot。")
        finally:
            await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已停止 Bot。")

