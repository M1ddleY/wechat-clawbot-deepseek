# 微信 ClawBot + DeepSeek 自动回复机器人 — 设计文档

- 日期：2026-09-04
- 状态：待评审
- 技术栈：Python 3.10+ / DeepSeek API / 腾讯微信 ClawBot（iLink）接口
- 运行环境：本机 Windows

## 1. 背景与目标

用户希望基于官方微信 ClawBot 插件，搭建一个部署在本机的 AI 自动回复机器人。
好友私聊自己微信号时，机器人在微信聊天窗内自动、智能地回复消息，全程不离开微信。
本人已确认微信 ClawBot 插件可用（iOS 8.0.70+ / 最新安卓版）。

目标：一个可长期运行、低维护成本的 Python 脚本应用，实现「收消息 → 问 DeepSeek → 发回复」的闭环。

## 2. 需求

### 2.1 用户故事
- 作为微信用户，我私聊自己的微信号，炸鸡（AI）根据我说的话智能回复。
- 作为微信好友，我无需安装任何额外 App，就能在微信对话里得到回复。
- 作为主人，我可调整 AI 人设、模型、密钥，无需改代码。

### 2.2 功能需求
- FR1: 扫码登录微信个人账号，持久化登录态，token 失效(-14)自动重新登录。
- FR2: 长轮询接收新消息，按 `get_updates_buf` 游标增量同步，不丢消息。
- FR3: 对所有私聊好友的**文字消息**自动回复；回复范围=全部（不启用白名单）。
- FR4: 按微信用户 ID 维护独立多轮对话上下文，支持 `/clear` 清空，滑动窗口控 token。
- FR5: 调用 DeepSeek 生成回复并发送，带「正在输入」状态（sendtyping）。
- FR6: 支持机器人指令：`/help`、`/clear`、`/time`。
- FR7: 图片/语音/文件等媒体消息提示「暂不支持」，不误送 AI。

### 2.3 非功能需求
- 稳定性：长轮询超时视为正常，连续失败按退避策略(2s→30s)重试，防限流。
- 安全：API Key / token / 状态文件不入版控；Key 显示时脱敏。
- 可维护：模块清晰，配置集中在 config.json。

## 3. 范围

### 3.1 范围内
- 文字私聊自动回复（官方 iLink 通道）
- DeepSeek 对话接入、多轮上下文
- 扫码登录、自动重连、优雅退出
- 基础指令

### 3.2 范围外（后续可扩展）
- 图片/语音/文件多模态收发（需 AES-128-ECB 加密与 CDN 上传下载）
- 知识库 / RAG、定时推送
- Web 管理面板、多账号
- 服务器/NAS 24h 在线部署

## 4. 架构设计

### 4.1 数据流
```
微信好友私聊
  → 手机微信 ClawBot 插件
  → 腾讯 iLink Bot API (ilinkai.weixin.qq.com)
  → 本机 Python 应用 getupdates 长轮询收消息
  → 提取文本，读取/更新该用户对话 session
  → DeepSeek API 生成回复
  → sendtyping(sendmessage) 发回
  → 微信好友收到回复
```

### 4.2 模块划分
| 文件 | 职责 |
|------|------|
| `auth.py` | 扫码登录：get_bot_qrcode → get_qrcode_status 状态机 → 保存 bot_token/baseurl/account_id；凭证持久化；-14 触发重新扫码 |
| `ilink_client.py` | iLink 通信层：getupdates 长轮询、sendtyping、sendmessage、getconfig；封装 X-WECHAT-UIN 等请求头；校验 ret/errcode |
| `deepseek_client.py` | DeepSeek(OpenAI 兼容) 客户端；按 user_id 维护 ChatSession；滑动窗口控 token；读取 config 模型/人设 |
| `bot.py` | 主循环：getupdates → 过滤 USER 消息 → 提炼文本 → 指令或 AI → 回复；重试/退避；优雅退出 |
| `config.json` | provider=deepseek；providers.deepseek{api_key,base_url,model,prompt} |
| `requirements.txt` | aiohttp / requests / qrcode[pil] |
| `.gitignore` | 忽略 config.json / weixin_state.json / *.token / 二维码 |
| `README.md` | 使用与配置说明 |

### 4.3 关键技术决策
- **不走 OpenClaw 框架**：直接调用 `@tencent-weixin/openclaw-weixin` 的公开 HTTP 行为（iLink），省去部署负载。
- **长轮询**：getupdates 需携带上次成功的 `get_updates_buf` 游标，服务端 hold 默认约 35s，超时视为空返回。
- **请求头**：`AuthorizationType: ilink_bot_token`、`X-WECHAT-UIN: <随机uint32十进制后base64>`、`iLink-App-Id: bot`、`Authorization: Bearer <token>`。
- **sendmessage**：`msg.context_token` 必须取当前入站消息的 token；`client_id` 每次唯一；HTTP 200 需再校验 JSON/业务码。
- **多轮上下文**：system prompt(persona=炸鸡) + 按用户的历史，滑动窗口(默认 20 条)。

## 5. 接口设计

### 5.1 iLink 登录
- `POST /ilink/bot/get_bot_qrcode?bot_type=3` → 二维码
- `GET /ilink/bot/get_qrcode_status?qrcode=...` → wait/scaned/scaned_but_redirect/confirmed(-14 重登)
- confirmed → 保存 bot_token、baseurl、account_id

### 5.2 iLink 消息
- `POST ilink/bot/getupdates`（带 get_updates_buf）
- `POST ilink/bot/getconfig`
- `POST ilink/bot/sendtyping {status=1/2}`
- `POST ilink/bot/sendmessage`

### 5.3 DeepSeek（OpenAI 兼容）
- `POST {base_url}/chat/completions`
- 默认 base_url `https://api.deepseek.com`；model 可配置（默认 `deepseek-v4-flash`，可按账号可用模型调整）

## 6. 错误处理
- 长轮询超时(AbortError)：返回空响应，继续下一轮。
- `ret=-14` / `errcode=-14`：token 失效，进入受控重新扫码。
- 连续失败：≤5 次等 2 秒，>5 次退避 30 秒。
- 连接到期：基础 24h 窗口，提前 2h 提醒，剩余 30 分钟强制重连（可配）。

## 7. 安全与合规
- 遵守《微信 ClawBot 功能使用条款》及当地法律法规。
- `config.json` / `weixin_state.json` / token / 二维码 不入版控。
- API Key 显示仅保留首尾各 5 位。
- 不模拟用户行为，不伪造交互事件。

## 8. 测试计划
- 单元：请求头/状态机/错误码解析、session 窗口维护。
- 集成：mock iLink 接口验证收→AI→发链路。
- 手动：真实扫码登录、多轮对话、/clear、媒体消息提示、断线重连。

## 9. 运行环境
- Python 3.10+；Windows 本机；依赖 aiohttp/requests/qrcode[pil]。
- 微信需 8.0.70+ 且已启用 ClawBot 插件。

## 10. 待办 / 开放问题
- 登录成功后从消息中确认自身 `ilink_bot_id`，便于后续加白名单(当前默认全量回复)。
- 确认 DeepSeek 账号可用的 model 名并写入 config。
