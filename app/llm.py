"""LLM 客户端抽象。

两条路径：
1. OpenAICompatClient —— 走腾讯混元 OpenAI 兼容接口，支持 function calling。
   需要 HUNYUAN_API_KEY。这是比赛真正要展示的智能体推理路径。
2. 确定性回退由各 agent 内部的 scripted_decide() 实现（见 agents/*.py），
   无需 API key，保证 demo 在任何环境都能跑通，且工具调用全程可见。

返回统一归一化结构 LLMResponse，使 agent 循环对两种后端透明。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

# 全局节流：免费额度 RPM 很紧，串行化并强制最小间隔，避免 429 雪崩
_MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "3.0"))
_rl_lock = asyncio.Lock()
_next_allowed = 0.0


async def _throttle() -> None:
    """保证两次请求之间至少间隔 _MIN_INTERVAL 秒（全局，跨 agent 生效）。"""
    global _next_allowed
    loop = asyncio.get_event_loop()
    async with _rl_lock:
        now = loop.time()
        if now < _next_allowed:
            await asyncio.sleep(_next_allowed - now)
            now = loop.time()
        _next_allowed = now + _MIN_INTERVAL


_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "5"))
_BASE_BACKOFF = float(os.environ.get("LLM_BASE_BACKOFF", "6"))
_MAX_BACKOFF = float(os.environ.get("LLM_MAX_BACKOFF", "70"))


def _is_retryable(e: Exception) -> bool:
    """判断异常是否值得重试：限流(429)与服务端错误(5xx)。"""
    status = getattr(e, "status_code", None) or getattr(e, "code", None) or getattr(e, "http_status", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    s = str(e).lower()
    return any(k in s for k in ("429", "rate limit", "rate_limit", "quota",
                                "resource exhausted", "overloaded", "temporarily"))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    raw: Any = None
    # 供应商特有字段，例如 Gemini 3 的 extra_content.google.thought_signature。
    # 这类字段必须原样回传，否则模型会以 400 "missing a thought_signature" 拒绝后续请求。
    extra_content: Any = None


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OpenAICompatClient:
    """Async client for any OpenAI-compatible chat endpoint (Gemini, Tencent Hunyuan, ...)."""

    def __init__(self) -> None:
        # 延迟构造，避免无 key 时 import 即失败
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # 延迟导入
            if not settings.has_api_key:
                raise RuntimeError(
                    "LLM_API_KEY is not set; cannot use LLM mode. "
                    "Set LLM_API_KEY or keep LLM_MODE=deterministic."
                )
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float | None = None,
        max_tokens: int | None = 3072,
    ) -> LLMResponse:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature if temperature is None else temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        # 混元自定义参数（仅对混元官方 endpoint 启用；Token Plan 等其他兼容端点跳过，避免未知字段被拒）
        if "hunyuan" in (settings.llm_base_url or ""):
            kwargs["extra_body"] = {"enable_enhancement": True}

        # 429/5xx 指数退避重试。免费额度 RPM 很低，不重试几乎必然中途失败。
        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                await _throttle()
                resp = await client.chat.completions.create(**kwargs)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if _is_retryable(e) and attempt < _MAX_RETRIES - 1:
                    wait = min(_MAX_BACKOFF, _BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 1.5)
                    await asyncio.sleep(wait)
                    continue
                # 把异常转成可读内容，便于在事件流里看到失败原因
                return LLMResponse(content=f"[LLM 调用失败] {type(e).__name__}: {e}", finish_reason="error")
        else:
            return LLMResponse(
                content=f"[LLM 调用失败] 重试 {_MAX_RETRIES} 次仍失败: {type(last_err).__name__}: {last_err}",
                finish_reason="error")

        choice = resp.choices[0]
        msg = choice.message
        content = msg.content or ""
        tcs: list[ToolCall] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:  # noqa: BLE001
                    args = {"_raw": tc.function.arguments}
                tcs.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args, raw=tc,
                                    extra_content=getattr(tc, "extra_content", None)))
        usage = None
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return LLMResponse(content=content or None, tool_calls=tcs, finish_reason=choice.finish_reason, usage=usage)


# 单例
llm_client = OpenAICompatClient()
hunyuan_client = llm_client  # legacy alias
