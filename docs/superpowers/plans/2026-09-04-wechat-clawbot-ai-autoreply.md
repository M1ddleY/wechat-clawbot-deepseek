# 微信 ClawBot + DeepSeek 自动回复 实现计划

**Goal:** 在本机 Windows 上跑一个 Python 应用，微信好友私聊时由「炸鸡」(DeepSeek) 自动回复。

**Architecture:** 直接调腾讯 iLink Bot API（ilinkai.weixin.qq.com，ClawBot 官方通道），扫码登录个人微信号 → getupdates 长轮询收消息 → DeepSeek 生成回复 → sendmessage 发回。不走 OpenClaw 框架。

**Tech Stack:** Python 3.10+ / aiohttp / requests / qrcode[pil] / DeepSeek(OpenAI 兼容)

**Spec:** docs/superpowers/specs/2026-09-04-wechat-clawbot-ai-autoreply-design.md

## Global Constraints
- Python >= 3.10；Windows 本机。
- 协议基线：openclaw-weixin 2.4.6；BASE_URL=`https://ilinkai.weixin.qq.com`。
- `sendmessage`：message_type=2, message_state=2, item_list=[{type:1,text_item:{text}}], context_token 必须取入站消息。
- 收消息判定：message_type != 1 跳过。
- `ret/errcode == -14` = token 失效 → 触发重新扫码。
- 敏感文件不入版控：config.json / weixin_state.json / qrcode.* / __pycache__。

## 文件
| 文件 | 职责 |
|---|---|
| requirements.txt | aiohttp, requests, qrcode[pil] |
| config.json | DeepSeek 配置（api_key/base_url/model/prompt=炸鸡人设） |
| config.py | 加载口罩掩码配置 |
| ilink_client.py | 协议：headers/base_info/api_get/api_post/ILinkAPIError/登录/消息 |
| deepseek_client.py | DeepSeek 对话，按用户 session，滑动窗口 |
| bot.py | 主循环：getupdates → 文本 → 指令或 AI → 发送 |
| README.md | 使用说明 |
| tests/test_*.py | 关键单元测试（mock 网络） |

## 任务
- Task 1: 基础文件 requirements/config.json/.gitignore/config.py
- Task 2: ilink_client.py（请求头、api、ILinkAPIError、登录、消息收发）
- Task 3: deepseek_client.py（炸鸡人设、多轮上下文）
- Task 4: bot.py（主循环、指令、重连）
- Task 5: tests + README + 冒烟验证
- 每任务后 commit。

## 执行方式
用户已授权开发（"你开发吧"），采用 Inline Execution，逐任务实现并 commit。
