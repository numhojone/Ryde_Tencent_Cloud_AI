"""Intake / triage agent.

自由文本投诉进来时，第一步不是跑辩护智能体，而是先判定「这到底是什么类型的争议」。
真实乘客只会说「司机绕远路多收我钱」「我等了半天没人来」，不会自己在下拉框里选
`route_deviation` 还是 `no_show_charge` —— 这一步必须由系统读懂。

设计要点：
- LLM 模式：模型读原文 + 调工具看一眼行程状态（completed / cancelled 是强信号），输出分类。
- 确定性模式：同一套关键词规则兜底，保证没有 API key 也能跑完整流程。
- 无论哪条路径，模型/规则给出的分类都要能被下游校验：非法类型一律回落到规则结果。
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import BaseAgent
from app.i18n import L, CUR
from app.models import TriageResult

# 平台当前支持的争议类型（与 fixtures/policies 一一对应）
SUPPORTED_TYPES = ("route_deviation", "no_show_charge")

TYPE_LABELS = {  # Chinese labels (default English labels live in TYPE_LABELS_EN)
    "route_deviation": "绕路多收费",
    "no_show_charge": "爽约取消费",
}
TYPE_LABELS_EN = {
    "route_deviation": "Route deviation",
    "no_show_charge": "No-show charge",
}


def type_label(dtype: str, lang: str = "en") -> str:
    return (TYPE_LABELS if lang == "zh" else TYPE_LABELS_EN).get(dtype, dtype)

# 关键词信号：中英文都要覆盖，评委可能用任意一种语言投诉
_SIGNALS: dict[str, tuple[str, ...]] = {
    "route_deviation": (
        "绕路", "绕远", "绕道", "绕行", "绕圈", "兜圈", "走远", "多收", "多扣", "超收",
        "里程", "路线", "车费高", "计价", "多花钱", "绕了一大圈", "故意绕",
        "out of the way", "longer route", "long way", "detour", "overcharge", "overcharged",
        "over-charged", "charged more", "extra money", "mileage", "took longer", "scenic",
        "go round", "round and round", "so far", "ambil jalan jauh", "jalan jauh", "caj lebih", "caj terlalu", "kena caj lebih",
        "சுற்றி", "அதிக கட்டணம்", "நீண்ட வழி",
    ),
    "no_show_charge": (
        "没来", "没到", "没出现", "没见到", "没接", "没接到", "等不到", "白等", "空等",
        "取消费", "取消单", "爽约", "放鸽子", "等了", "等半天", "等很久", "没人来",
        "司机未到", "未出现", "取消还扣", "没上车",
        "no-show", "no show", "nobody showed", "nobody came", "didn't show", "did not show",
        "never came", "never showed", "didn't arrive", "waited forever", "waited", "waiting",
        "cancellation fee", "cancel fee", "charged for cancelling", "no one came", "no one showed",
        "never turn up", "never turn up", "didn't turn up", "never arrive", "kena charge cancel", "tak datang", "tidak datang",
        "tak sampai", "tidak sampai", "tunggu lama", "yuran pembatalan", "caj pembatalan",
        "வரவில்லை", "காத்திருந்தேன்", "ரத்து கட்டணம்",
    ),
}

_AMOUNT_RE = re.compile(
    r"(?:¥|￥|s\$|sgd\s*|\$|rmb\s*)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|块|块钱|块 RMB|dollars?|sgd)",
    re.IGNORECASE,
)


def classify_by_rules(text: str, trip_status: str | None = None) -> tuple[str, list[str]]:
    """确定性分类：关键词打分 + 行程状态兜底。返回 (dispute_type, 命中的信号)。"""
    low = (text or "").lower()
    hits: dict[str, list[str]] = {t: [] for t in SUPPORTED_TYPES}
    for dtype, words in _SIGNALS.items():
        for w in words:
            if w.lower() in low:
                hits[dtype].append(w)

    rd, ns = hits["route_deviation"], hits["no_show_charge"]
    if len(rd) > len(ns):
        return "route_deviation", rd
    if len(ns) > len(rd):
        return "no_show_charge", ns
    if rd and ns and len(rd) == len(ns):
        # 平手：行程状态说话。被取消的行程不可能有绕路争议。
        return _fallback_by_status(trip_status), rd + ns
    # 一个都没命中：只看行程状态
    return _fallback_by_status(trip_status), []


def _fallback_by_status(trip_status: str | None) -> str:
    s = (trip_status or "").lower()
    if "cancel" in s:
        return "no_show_charge"
    return "route_deviation"


def extract_amount(text: str) -> float | None:
    """从原文里抽取乘客主张的金额（¥30 / 30元 / $12.5）。抽不到就返回 None。"""
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class IntakeAgent(BaseAgent):
    """Reads a free-text complaint -> decides dispute_type -> normalises the claim."""

    role = "intake"
    name = "intake"
    parse_schema = TriageResult

    def system_prompt(self) -> str:
        return (
            "You are the INTAKE / TRIAGE AGENT of the RydeResolve ride-hailing dispute platform. "
            "You classify a rider's plain-language complaint into one of the dispute types the platform supports.\n\n"
            "Supported types (choose exactly one):\n"
            "1. route_deviation: rider says the driver took a longer or wrong route, mileage looks wrong, or they were overcharged.\n"
            "2. no_show_charge: rider says the driver never arrived / never picked them up / made them wait, yet a cancellation fee was charged.\n\n"
            "How to work:\n"
            "1. Read the complaint and pick out the key signals (long route / overcharge vs. driver did not come / waited for nothing). "
            "The complaint may be in English, Singlish, Malay, Tamil or Chinese; understand it in whatever language it is written in.\n"
            "2. You may call get_trip_data to check the trip status: a cancelled trip cannot have a route-deviation dispute, "
            "and a completed trip is usually not a no-show. This is a strong signal but not the only one.\n"
            "3. Restate the claim in platform terms (normalized_claim) and list the signals from the original text that drove your decision.\n"
            "4. If the complaint states a specific amount, put it in requested_amount (a number, no currency symbol); otherwise null.\n\n"
            "Hard rule: judge only from the complaint and the trip data returned by the tool; do not invent details. "
            "If unsure, give a lower classification_confidence rather than pretending to be certain.\n\n"
            "Final output must be strict JSON (no code fences):\n"
            '{"dispute_type":"route_deviation","classification_confidence":0.9,'
            '"classification_reasoning":"...","normalized_claim":"...",'
            '"requested_amount":null,"requested_resolution":"full_refund_of_overcharge",'
            '"detected_signals":["longer route","overcharged"]}'
        )

    def build_user_message(self, context: dict) -> str:
        draft = context["draft"]
        return (
            "The rider's complaint, verbatim and unedited (read this text directly to decide):\n"
            "----------------\n"
            f"{draft['complaint']}\n"
            "----------------\n\n"
            f"Linked trip_id: {draft['trip_id']}\n"
            "Classify the dispute type and output the classification JSON."
        )

    # Only the trip-data tool: classification should not dig through GPS / chat logs.
    def tool_schemas(self) -> list[dict]:
        from app.tools.registry import TOOL_SCHEMAS
        return [s for s in TOOL_SCHEMAS
                if s["function"]["name"] in ("get_trip_data",)]

    def build_playbook(self, context: dict) -> list[dict]:
        return [{
            "_thought": L(self.lang,
                          "First check the trip status: completed or cancelled is a strong classification signal.",
                          "先看行程状态：已完成还是被取消，这是分类的强信号。"),
            "name": "get_trip_data",
            "args": {"trip_id": context["draft"]["trip_id"]},
        }]

    def build_final(self, context: dict, gathered: dict) -> dict:
        lg = self.lang
        draft = context["draft"]
        text = draft["complaint"]
        status = (gathered.get("get_trip_data") or {}).get("status")
        dtype, signals = classify_by_rules(text, status)
        amount = extract_amount(text)
        # More matched signals -> more certain; falling back on trip status alone -> low score
        conf = 0.45 if not signals else min(0.95, 0.55 + 0.15 * len(signals))
        label = type_label(dtype, lg)
        sep = ", " if lg == "en" else "、"
        return {
            "dispute_type": dtype,
            "classification_confidence": round(conf, 2),
            "classification_reasoning": L(lg,
                f"Rule-based classification: matched '{label}' signals "
                + (sep.join(signals[:6]) if signals else "none (fell back on trip status)")
                + f"; trip status={status or 'unknown'}.",
                f"确定性分类规则：命中「{label}」信号 "
                + (sep.join(signals[:6]) if signals else "无（按行程状态兜底）")
                + f"；行程 status={status or '未知'}。"),
            "normalized_claim": (
                L(lg, "Driver took a longer route and overcharged the rider; rider requests a refund of the excess.",
                      "司机绕路导致多收车费，请求退还超出部分。")
                if dtype == "route_deviation" else
                L(lg, "Driver did not arrive / did not pick the rider up but a cancellation fee was charged; rider requests a refund.",
                      "司机未按时到达/未接到乘客却被收取消费，请求退还取消费。")
            ),
            "requested_amount": amount,
            "requested_resolution": (
                "full_refund_of_overcharge" if dtype == "route_deviation"
                else "full_refund_of_cancellation_fee"
            ),
            "detected_signals": signals,
            "_summary": L(lg, f"Classified as {label} ({dtype}).", f"分类完成：{label}（{dtype}）。"),
        }

    def _fill_defaults(self, data: dict, context: dict) -> dict:
        """If the classification is missing fields, fall back to rules; never let an illegal type downstream."""
        if not isinstance(data, dict):
            return data
        text = (context.get("draft") or {}).get("complaint", "")
        dtype, signals = classify_by_rules(text, None)
        if data.get("dispute_type") not in SUPPORTED_TYPES:
            data["dispute_type"] = dtype
            data.setdefault("classification_reasoning",
                            L(self.lang, "Model output a type outside the supported list; fell back to rules.",
                              "模型输出的类型不在支持列表内，已按规则回落。"))
        data.setdefault("classification_confidence", 0.6)
        data.setdefault("classification_reasoning", "")
        data.setdefault("normalized_claim", text[:120])
        data.setdefault("requested_amount", extract_amount(text))
        data.setdefault("requested_resolution", None)
        data.setdefault("detected_signals", signals)
        return data
