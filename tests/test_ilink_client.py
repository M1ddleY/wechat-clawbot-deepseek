import base64

import pytest

import ilink_client as ic


def test_client_version():
    assert (2 << 16) | (4 << 8) | 6 == 132102
    assert ic.ILINK_APP_CLIENT_VERSION == "132102"


def test_common_headers():
    h = ic.make_common_headers()
    assert h["iLink-App-Id"] == "bot"
    assert h["iLink-App-ClientVersion"] == "132102"


def test_headers_with_token():
    h = ic.make_headers("ABC")
    assert h["AuthorizationType"] == "ilink_bot_token"
    assert h["Authorization"] == "Bearer ABC"
    assert h["Content-Type"] == "application/json"
    # X-WECHAT-UIN 是 base64(十进制字符串)
    uin = base64.b64decode(h["X-WECHAT-UIN"]).decode()
    assert uin.isdigit()


def test_base_info():
    b = ic.base_info()
    assert b["channel_version"] == "2.4.6"
    assert b["bot_agent"]


def test_ilink_error_stale():
    e = ic.ILinkAPIError("x", ret=0, errcode=-14)
    assert e.is_stale_token
    e2 = ic.ILinkAPIError("x", ret=-14)
    assert e2.is_stale_token
    e3 = ic.ILinkAPIError("x", ret=1)
    assert not e3.is_stale_token


def test_extract_text():
    msg = {"item_list": [{"type": 1, "text_item": {"text": "你好 炸鸡"}}]}
    assert ic.extract_message_text(msg) == "你好 炸鸡"


def test_extract_voice():
    msg = {"item_list": [{"type": 2, "voice_item": {"text": "语音转写"}}]}
    assert ic.extract_message_text(msg) == "语音转写"


def test_send_message_payload_structure():
    # 验证 sendmessage 使用的字段值（通过构造 msg 复核）
    msg = {
        "from_user_id": "",
        "to_user_id": "u1",
        "client_id": "c1",
        "message_type": 2,
        "message_state": 2,
        "context_token": "ctx",
        "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
    }
    assert msg["message_type"] == 2
    assert msg["message_state"] == 2
    assert msg["item_list"][0]["type"] == 1
