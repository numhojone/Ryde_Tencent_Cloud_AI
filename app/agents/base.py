"""Agent 基类：统一的工具调用循环，对 LLM / 确定性两种后端透明。

每个具体 agent 定义：
- system_prompt / role
- build_playbook(context) -> list[dict]   确定性模式下要依次调用的工具
- build_final(context, gathered) -> dict  确定性模式下最终结构化输出
- parse_schema                              最终输出的 pydantic 模型（校验）

循环逻辑（run）：
  while iter < max:
    action = await decide(messages, context, gathered)   # LLM 或 scripted
    emit thought
    if action.tool_calls: 执行工具 -> emit tool_call/tool_result -> 追加消息 -> 继续
    if action.final:     解析/校验 -> emit agent_final -> 返回
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel, ValidationError

import logging

from app.config import settings
from app.i18n import L, lang_rule

_log = logging.getLogger("uvicorn.error")
from app.llm import llm_client
from app.tools import TOOL_SCHEMAS, call_tool, summarize_for_log


# 事件回调：async emit(event_dict)
EventEmitter = Callable[[dict], Awaitable[None]]


@dataclass
class AgentAction:
    """一次 decide 的结果：要么调用工具，要么给出最终输出。"""
    thought: Optional[str] = None
    tool_calls: Optional[list[dict]] = None  # [{name, args, id?}]
    final: Any = None  # dict（确定性）或 str（LLM 的 JSON 文本）


@dataclass
class AgentResult:
    agent: str
    role: str
    output: Any  # 校验后的 pydantic 实例
    raw_output: Any
    transcript: list[dict] = field(default_factory=list)


# 效率约束：鼓励模型一次并行发起多个工具调用，而不是逐个串行等待。
# 既减少请求数（规避免费额度限流），也让 demo 的工具调用更集中可见。
_EFFICIENCY_HINT = (
    "\n\n[Efficiency] In a single reply, request ALL the tool calls you need in parallel "
    "instead of one at a time; once the evidence is gathered, output the final JSON in one go."
)


def _to_api_tool_call(tc: dict) -> dict:
    """把内部工具调用转回 OpenAI 消息格式。

    关键：必须原样保留 extra_content（如 Gemini 3 的 thought_signature）。
    缺失时模型会以 400 "Function call is missing a thought_signature" 拒绝后续请求。
    """
    out = {
        "id": tc.get("id", f"call_{tc['name']}"),
        "type": "function",
        "function": {
            "name": tc["name"],
            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
        },
    }
    if tc.get("extra_content"):
        out["extra_content"] = tc["extra_content"]
    return out


def _extract_json(text: str) -> Any:
    """从可能带 markdown 围栏的文本中抽取 JSON。

    逐级降级解析，任何一级失败都继续尝试下一级；全部失败返回 None
    （由 _finalize 负责告警并回退），绝不向上抛异常中断整场裁决。
    """
    if not text:
        return None
    raw = text.strip()

    # 1) 整段本身就是合法 JSON
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        pass

    # 2) ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:  # noqa: BLE001
            pass

    # 3) 第一个 { 到最后一个 }
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        block = m.group(0)
        try:
            return json.loads(block)
        except Exception:  # noqa: BLE001
            pass
        # 4) 单引号 / Python 字面量风格兜底（部分模型会吐 {'a': 1}）
        try:
            import ast
            v = ast.literal_eval(block)
            if isinstance(v, (dict, list)):
                return v
        except Exception:  # noqa: BLE001
            pass
    return None


class BaseAgent:
    role: str = "base"
    name: str = "base"
    parse_schema: type[BaseModel] = BaseModel

    def __init__(self, emit: EventEmitter, mode: str | None = None, lang: str = "en") -> None:
        self.emit = emit
        self.lang = lang
        self._mode_override = mode  # None => 跟随全局 settings
        self._gathered: dict[str, Any] = {}  # 工具名 -> 最近一次结果（确定性 final 用）
        self._transcript: list[dict] = []

    # ---- 供子类实现 ----
    def system_prompt(self) -> str:
        raise NotImplementedError

    def build_user_message(self, context: dict) -> str:
        raise NotImplementedError

    def build_playbook(self, context: dict) -> list[dict]:
        """确定性模式：依次执行的工具调用列表。"""
        return []

    def build_final(self, context: dict, gathered: dict[str, Any]) -> dict:
        """确定性模式：从已收集的工具结果计算最终输出。"""
        raise NotImplementedError

    # ---- 工具集合：默认全部 8 个 ----
    def tool_schemas(self) -> list[dict]:
        return TOOL_SCHEMAS

    # =========================================================
    def _mode(self) -> str:
        return self._mode_override or settings.effective_mode

    async def _emit(self, **kw):
        kw.setdefault("agent", self.name)
        kw.setdefault("role", self.role)
        await self.emit(kw)

    async def decide(
        self, messages: list[dict], context: dict, gathered: dict[str, Any], iteration: int
    ) -> AgentAction:
        if self._mode() == "llm":
            return await self._llm_decide(messages)
        return self._scripted_decide(context, gathered, iteration)

    async def _llm_decide(self, messages: list[dict]) -> AgentAction:
        resp = await llm_client.chat(messages=messages, tools=self.tool_schemas())
        if resp.finish_reason == "error":
            # never fail silently: a visible notice in the chat, and the error in the server console (no key)
            from app.agents.story_intake import _failure_kind, _scrub
            kind = _failure_kind(resp.content or "")
            _log.warning("Live AI call failed in %s (%s): %s", self.name, kind, _scrub(resp.content or ""))
            await self._emit(type="warning", notice=True,
                             content=L(self.lang, f"Live AI is unavailable ({kind}). Using offline rules.",
                                       f"实时 AI 不可用（{kind}），改用离线规则。"))
        if resp.has_tool_calls:
            tcs = [{"id": tc.id, "name": tc.name, "args": tc.arguments,
                    "extra_content": tc.extra_content} for tc in resp.tool_calls]
            return AgentAction(thought=resp.content, tool_calls=tcs)
        return AgentAction(thought=None, final=resp.content)

    def _scripted_decide(
        self, context: dict, gathered: dict[str, Any], iteration: int
    ) -> AgentAction:
        playbook = self.build_playbook(context)
        if iteration < len(playbook):
            step = playbook[iteration]
            thought = step.get("_thought", f"Calling {step['name']} to gather evidence.")
            return AgentAction(thought=thought, tool_calls=[step])
        # playbook 跑完，产出最终答案
        final = self.build_final(context, gathered)
        return AgentAction(thought=final.get("_summary", L(self.lang, "Evidence gathered; building the conclusion.", "证据收集完毕，构建结论。")), final=final)

    # ---- 工具执行 ----
    async def _exec_tool(self, call: dict) -> dict:
        name = call["name"]
        args = call.get("args", {}) or {}
        call_id = call.get("id", f"{name}_{id(call)}")
        await self._emit(type="tool_call", tool=name, args=args,
                         summary=summarize_for_log(name, args))
        res = call_tool(name, args)
        if res["ok"]:
            self._gathered[name] = res["result"]
        # 结果摘要（截断，避免刷屏）
        preview = _preview(res)
        await self._emit(type="tool_result", tool=name, ok=res["ok"], result=preview)
        return res

    # =========================================================
    async def run(self, context: dict) -> AgentResult:
        await self._emit(type="agent_start", mode=self._mode())
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt() + _EFFICIENCY_HINT + lang_rule(self.lang)},
            {"role": "user", "content": self.build_user_message(context)},
        ]
        max_iter = settings.llm_max_iterations
        for iteration in range(max_iter):
            action = await self.decide(messages, context, self._gathered, iteration)
            # 1) thinking
            if action.thought:
                await self._emit(type="thinking", content=action.thought)
                self._transcript.append({"role": "assistant_thought", "content": action.thought})
            # 2) 工具调用
            if action.tool_calls:
                # OpenAI/混元契约：assistant(tool_calls) 必须出现在对应 tool 结果消息之前，否则 400。
                # 因此先构造并 append assistant 消息，再依次 append 各 tool 结果。
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": action.thought or "",
                    "tool_calls": [_to_api_tool_call(tc) for tc in action.tool_calls],
                }
                messages.append(assistant_msg)
                for tc in action.tool_calls:
                    res = await self._exec_tool(tc)
                    content = json.dumps(res, ensure_ascii=False)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{tc['name']}"),
                        "content": content,
                    })
                continue
            # 3) 最终输出
            if action.final is not None:
                parsed = await self._finalize(action.final, context)
                return AgentResult(agent=self.name, role=self.role,
                                   output=parsed, raw_output=action.final,
                                   transcript=self._transcript)
        # 超过迭代上限
        await self._emit(type="thinking", content=L(self.lang, "Reached the maximum number of reasoning rounds; stopping.", "已达最大推理轮数，停止。"))
        return AgentResult(agent=self.name, role=self.role, output=None,
                           raw_output=None, transcript=self._transcript)

    async def _finalize(self, final: Any, context: dict) -> Any:
        try:
            data = final if isinstance(final, dict) else _extract_json(str(final))
        except Exception as e:  # noqa: BLE001
            # 解析异常不得中断整场裁决：告警并保留模型原始输出以便排查
            await self._emit(type="warning",
                             content=f"Final JSON parse error: {type(e).__name__}: {e} | raw output: {str(final)[:800]}")
            data = None
        if data is None:
            await self._emit(type="warning", content=L(self.lang, "Final output could not be parsed as JSON; falling back to raw text.", "最终输出无法解析为 JSON，回退为原始文本。"))
            data = {"raw": str(final)}
        # 补默认字段，便于 LLM 漏字段时仍可校验
        data = self._fill_defaults(data, context)
        try:
            obj = self.parse_schema.model_validate(data)
            await self._emit(type="agent_final", output=obj.model_dump())
            return obj
        except ValidationError as e:
            await self._emit(type="warning", content=f"Output validation failed: {e.errors()}")
            return data

    def _fill_defaults(self, data: dict, context: dict) -> dict:
        # LLM 可能漏字段，补默认值以提升校验通过率（子类如 Judge 可进一步覆盖）
        data.setdefault("agent", self.name)
        data.setdefault("evidence_cited", [])
        data.setdefault("policy_clauses_referenced", [])
        return data


def _preview(res: dict) -> Any:
    """工具结果预览：保留结构但截断长数组。"""
    if not res.get("ok"):
        return res
    r = res["result"]
    return _truncate(r)


def _truncate(obj: Any, limit: int = 4) -> Any:
    """递归截断数组/长字符串，便于事件流展示。"""
    if isinstance(obj, list):
        if len(obj) > limit:
            return [_truncate(x, limit) for x in obj[:limit]] + [f"...(+{len(obj)-limit} more)"]
        return [_truncate(x, limit) for x in obj]
    if isinstance(obj, dict):
        return {k: _truncate(v, limit) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."
    return obj
