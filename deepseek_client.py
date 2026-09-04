"""DeepSeek 对话客户端（OpenAI 兼容），按微信用户维护独立多轮上下文。"""
from __future__ import annotations

import aiohttp

DEFAULT_MAX_HISTORY = 20


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str, model: str, prompt: str,
                 max_history: int = DEFAULT_MAX_HISTORY):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.model = model or "deepseek-v4-flash"
        self.prompt = prompt
        self.max_history = max_history
        self._session = None
        # user_id -> list[{role, content}]
        self.sessions: dict = {}

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def aclose(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def chat(self, user_id: str, text: str) -> str:
        """接收用户文本，返回模型回复；自动维护该用户多轮上下文。"""
        self.sessions.setdefault(user_id, [])
        history = self.sessions[user_id]
        history.append({"role": "user", "content": text})
        if len(history) > self.max_history:
            history = history[-self.max_history:]
            self.sessions[user_id] = history

        messages = [{"role": "system", "content": self.prompt}] + list(history)
        reply = await self._chat_completion(messages)

        history.append({"role": "assistant", "content": reply})
        if len(history) > self.max_history + 1:
            self.sessions[user_id] = history[-(self.max_history + 1):]
        return reply

    async def _chat_completion(self, messages: list) -> str:
        url = self.base_url + "/chat/completions"
        payload = {"model": self.model, "messages": messages}

        async with self._ensure_session().post(
            url,
            json=payload,
            headers={
                "Authorization": "Bearer {}".format(self.api_key.strip()),
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            body = await resp.json()
            if resp.status != 200:
                msg = body.get("error", {}).get("message", resp.status) if isinstance(body, dict) else resp.status
                raise RuntimeError("DeepSeek API 错误: {}".format(msg))
            try:
                reply = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("DeepSeek API 返回格式异常: {}".format(body)) from exc
        if not reply:
            return "（炸鸡没收到回复，请稍后再试）"
        return str(reply).strip()

    def clear(self, user_id: str) -> None:
        self.sessions.pop(user_id, None)
