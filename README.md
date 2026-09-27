# 微信 ClawBot · 炸鸡自动回复

基于腾讯官方 **微信 ClawBot 插件（iLink 协议）** + **DeepSeek** 的微信个人号自动回复机器人。
好友私聊这个微信号，AI 会自动智能回复；实现基于微信 ClawBot 插件（iLink 协议），不涉及 Hook。

## 功能
- 扫码登录微信个人账号，token 失效(-14)自动重登
- 长轮询接收新消息，不丢消息
- 对**所有**私聊好友的文字消息自动回复
- 按用户维护独立多轮对话上下文，`/clear` 可清空
- 指令：`/help`、`/clear`、`/time`、`/重新连接`
- 图片/语音/文件等消息会提示暂不支持

## 环境
需要 **Python 3.13+**（开发和测试用的是 3.13.15），依赖见 `requirements.txt`：

    pip install -r requirements.txt
- 手机微信需 **iOS 8.0.70+ / 最新安卓版**，并在「我 → 设置 → 插件」启用 **微信ClawBot**
- 需要一个 **DeepSeek API Key**（https://platform.deepseek.com ）

## 配置
复制 `config.example.json` 为 `config.json`，填入你的 DeepSeek Key：
```json
{
  "provider": "deepseek",
  "deepseek": {
    "api_key": "sk-你的key",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "prompt": "你是「炸鸡」，一个活泼、贴心、话不多的AI助手。用中文简洁自然地回复，避免长篇大论。"
  }
}
```
- `model`：按你 DeepSeek 账号实际可用的模型名调整。
- `prompt`：AI 人设，可自由修改。

## 运行
双击 `run.bat`，或手动：
```bash
python bot.py
```
首次运行会显示二维码，用手机微信扫码并确认；成功后登录态保存到 `weixin_state.json`，下次启动自动复用。

## 使用
- 登录后在微信里给这个账号发消息，炸鸡会回复。
- 常见指令见 `/help`。

## 测试
```bash
python -m pytest tests/ -v
```

## 注意
- `config.json`、`weixin_state.json`、二维码图片等**含敏感凭据，已加入 .gitignore，勿提交**。
- 请遵守《微信 ClawBot 功能使用条款》及当地法律法规。
- 本机运行，电脑关机即下线；如需 24h 在线请部署到服务器/NAS。
