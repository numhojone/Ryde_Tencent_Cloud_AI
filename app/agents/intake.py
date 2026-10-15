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

from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.extract import derive_requested_amount, extract_facts, ground_facts, missing_info, story_numbers
from app.i18n import L, CUR
from app.models import ExtractedFacts, TriageResult

# 平台当前支持的争议类型（与 fixtures/policies 一一对应）
SUPPORTED_TYPES = ("route_deviation", "no_show_charge", "fare_dispute", "property_damage", "safety_incident")

TYPE_LABELS = {  # Chinese labels (default English labels live in TYPE_LABELS_EN)
    "route_deviation": "绕路多收费",
    "no_show_charge": "爽约取消费",
    "fare_dispute": "车费争议",
    "property_damage": "财物损坏费用",
    "safety_incident": "安全事件",
}
TYPE_LABELS_EN = {
    "route_deviation": "Route deviation",
    "no_show_charge": "No-show charge",
    "fare_dispute": "Fare dispute",
    "property_damage": "Property damage",
    "safety_incident": "Safety incident",
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

_SIGNALS["fare_dispute"] = (
    "surge", "upfront", "quote", "quoted", "price was", "fare was", "higher than", "more than the price", "price changed", "charged more than",
    "not told", "wasn't told", "dynamic pricing", "peak pricing", "price jump", "报价", "预付", "加价", "动态定价", "涨价", "价格变", "比报价", "高于报价",
    "harga naik", "lonjakan", "விலை",
)
_SIGNALS["property_damage"] = (
    "cleaning fee", "clean fee", "cleaning charge", "vomit", "spill", "dirty", "mess", "stain", "damage fee", "damaged the car", "scratch", "dent",
    "清洁费", "清洗费", "弄脏", "呕吐", "污渍", "损坏", "划痕", "yuran pembersihan", "kotor", "muntah", "சுத்தம்",
)
SAFETY_SIGNALS = (
    "unsafe", "felt unsafe", "scared", "afraid", "threat", "threaten", "harass", "assault", "attacked", "hit me", "touched", "grope", "stalk",
    "reckless", "speeding", "red light", "drunk", "drink driving", "accident", "crash", "collision", "shouted at me", "abusive", "inappropriate",
    "不安全", "害怕", "威胁", "骚扰", "袭击", "危险驾驶", "超速", "闯红灯", "酒驾", "事故", "撞", "辱骂", "性骚扰",
    "tak selamat", "takut", "ancam", "ganggu", "bahaya", "பாதுகாப்பற்ற", "மிரட்டல்",
)


def detect_safety(text: str) -> list[str]:
    low = (text or "").lower()
    return [w for w in SAFETY_SIGNALS if w.lower() in low]


_AMOUNT_RE = re.compile(
    r"(?:¥|￥|s\$|sgd\s*|\$|rmb\s*)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元|块|块钱|块 RMB|dollars?|sgd)",
    re.IGNORECASE,
)


def classify_by_rules(text: str, trip_status: str | None = None) -> tuple[str, list[str]]:
    """Deterministic classification: keyword scoring, then trip status as a tie-breaker. Returns (type, signals)."""
    low = (text or "").lower()
    safety = detect_safety(text)
    if safety:                                            # policy 5.2: flag regardless of the type the filer chose
        return "safety_incident", safety
    hits = {t: [w for w in _SIGNALS.get(t, ()) if w.lower() in low] for t in SUPPORTED_TYPES if t != "safety_incident"}
    ranked = sorted(hits.items(), key=lambda kv: len(kv[1]), reverse=True)
    top, second = ranked[0], ranked[1]
    if len(top[1]) > len(second[1]):
        return top[0], top[1]
    tied = [k for k, v in ranked if v and len(v) == len(top[1])]
    return _fallback_by_status(trip_status, tied), (top[1] if top[1] else [])


def _fallback_by_status(trip_status: str | None, tied: list[str] | None = None) -> str:
    s = (trip_status or "").lower()
    if "cancel" in s:
        return "no_show_charge"
    if tied:
        return tied[0]
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


_CLAIMS = {
    "route_deviation": ("Driver took a longer route and overcharged the rider; rider requests a refund of the excess.", "司机绕路导致多收车费，请求退还超出部分。"),
    "no_show_charge": ("A no-show cancellation fee was charged although the rider says the driver did not arrive; rider requests a refund.", "乘客称司机未到达却被收取爽约取消费，请求退款。"),
    "fare_dispute": ("The final fare is higher than the upfront quote; rider requests a refund of the difference.", "最终车费高于预付报价，乘客请求退还差额。"),
    "property_damage": ("A cleaning/damage fee was charged to the rider; rider disputes it and requests reversal.", "乘客被收取清洁/损坏费，对此提出异议并请求撤销。"),
    "safety_incident": ("Rider reports a safety concern during the trip; case is flagged for mandatory human review.", "乘客报告行程中的安全问题；案件已标记，必须人工复核。"),
}
# Same vocabulary as the sample tickets (fixtures/disputes) where one exists.
_RESOLUTION = {"route_deviation": "refund_of_excess_fare", "no_show_charge": "full_refund_of_cancellation_fee", "fare_dispute": "refund_of_fare_difference",
               "property_damage": "reverse_fee", "safety_incident": "human_review"}


def requested_resolution(dtype: str, facts: dict) -> str:
    if dtype == "property_damage" and facts.get("fee_type") == "cleaning_fee":
        return "reverse_cleaning_fee"
    return _RESOLUTION[dtype]


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
            "1. route_deviation: the driver took a longer or different route and the rider was charged more.\n"
            "2. no_show_charge: a cancellation / no-show fee was charged although the rider says the driver never arrived or never waited.\n"
            "3. fare_dispute: the final fare is higher than the upfront quote (surge, price change) and the rider disputes the difference.\n"
            "4. property_damage: a cleaning or damage fee was charged to the rider for the vehicle.\n"
            "5. safety_incident: ANY safety indicator (reckless driving, speeding, harassment, threats, assault, inappropriate conduct, accident, feeling unsafe). "
            "Policy 5.2 says to flag these for human escalation regardless of what else the complaint says: set safety_flag true and choose safety_incident.\n\n"
            "How to work:\n"
            "1. Read the complaint and pick out the key signals (long route / overcharge vs. driver did not come / waited for nothing). "
            "The complaint may be in English, Singlish, Malay, Tamil or Chinese; understand it in whatever language it is written in.\n"
            "2. You may call get_trip_data to check the trip status: a cancelled trip cannot have a route-deviation dispute, "
            "and a completed trip is usually not a no-show. This is a strong signal but not the only one.\n"
            "3. Restate the claim in platform terms (normalized_claim) and list the signals from the original text that drove your decision.\n"
            "4. If the complaint states a specific amount, put it in requested_amount (a number, no currency symbol); otherwise null.\n"
            "5. Fill extracted_facts with ONLY what the complaint itself states (null or [] when it does not say it):\n"
            "   quoted_amount (upfront quote or the fare the rider expected), charged_amount (what they say they were charged), "
            "claimed_difference (a difference they state), fee_type (cleaning_fee | cancellation_fee | damage_fee | null), "
            "pickup_place, dropoff_place (as the rider wrote them), time_mentions (dates/times as written), "
            "driver_actions and rider_actions (short phrases, e.g. \"took a longer route\", \"waited at the pickup\"), "
            "safety_indicators (words in the text that indicate a safety issue), detected_language (en | en-SG | ms | ta | zh).\n"
            "   Never copy numbers or places from the trip record into extracted_facts: the record is a hint for classification only.\n"
            "6. missing_info: short phrases for what would help the case but the complaint does not say (e.g. \"Date or time of the trip\").\n\n"
            "Hard rule: judge only from the complaint and the trip data returned by the tool; do not invent details. "
            "If unsure, give a lower classification_confidence rather than pretending to be certain.\n\n"
            "Final output must be strict JSON (no code fences):\n"
            '{"dispute_type":"route_deviation","classification_confidence":0.9,'
            '"classification_reasoning":"...","normalized_claim":"...",'
            '"requested_amount":null,"requested_resolution":"refund_of_excess_fare",'
            '"detected_signals":["longer route","overcharged"],"safety_flag":false,'
            '"extracted_facts":{"quoted_amount":null,"charged_amount":null,"claimed_difference":null,"fee_type":null,'
            '"pickup_place":null,"dropoff_place":null,"time_mentions":[],"driver_actions":[],"rider_actions":[],'
            '"safety_indicators":[],"detected_language":"en"},"missing_info":[]}'
        )

    def build_user_message(self, context: dict) -> str:
        draft = context["draft"]
        return (
            "The rider's complaint, verbatim and unedited (read this text directly to decide):\n"
            "----------------\n"
            f"{draft['complaint']}\n"
            "----------------\n\n"
            f"Linked trip_id: {draft['trip_id']}\n"
            + _match_hint(draft.get("match"))
            + "Classify the dispute type, extract the facts the complaint states, and output the classification JSON."
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
        # More matched signals -> more certain; falling back on trip status alone -> low score
        conf = 0.45 if not signals else min(0.95, 0.55 + 0.15 * len(signals))
        label = type_label(dtype, lg)
        sep = ", " if lg == "en" else "、"
        facts = extract_facts(text, lg)
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
            "normalized_claim": _CLAIMS[dtype][0 if lg == "en" else 1],
            "requested_amount": derive_requested_amount(facts),
            "requested_resolution": requested_resolution(dtype, facts),
            "safety_flag": dtype == "safety_incident",
            "detected_signals": signals,
            "extracted_facts": facts,
            "missing_info": missing_info(dtype, facts, lg),
            "_summary": L(lg, f"Classified as {label} ({dtype}).", f"分类完成：{label}（{dtype}）。"),
        }

    def rule_result(self, context: dict, trip_status: str | None = None) -> TriageResult:
        """The rule-based result, used when the model's output cannot be validated."""
        return TriageResult.model_validate(
            {k: v for k, v in self.build_final(context, {"get_trip_data": {"status": trip_status}}).items()
             if not k.startswith("_")})

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
        data.setdefault("requested_resolution", None)
        data.setdefault("detected_signals", signals)

        # extracted_facts: validate the model's object; if it is malformed use the rule extractor.
        # Either way, anything the story does not support is dropped (never invent facts).
        rule_facts = extract_facts(text, self.lang)
        try:
            facts = ExtractedFacts.model_validate(data.get("extracted_facts")).model_dump() \
                if isinstance(data.get("extracted_facts"), dict) else None
        except ValidationError:
            facts = None
        facts = ground_facts(facts, text, rule_facts) if facts else rule_facts
        facts["safety_indicators"] = list(dict.fromkeys(rule_facts["safety_indicators"] + list(facts.get("safety_indicators") or [])))
        data["extracted_facts"] = facts

        # requested_amount must be a number the story gives (or the difference of two it gives)
        derived = derive_requested_amount(facts)
        ra = data.get("requested_amount")
        ok = isinstance(ra, (int, float)) and (
            any(abs(ra - n) < 0.011 for n in story_numbers(text)) or (derived is not None and abs(ra - derived) < 0.011))
        data["requested_amount"] = ra if ok else derived

        # Policy 5.2 is enforced in code: any safety indicator in the text overrides the model's choice.
        if detect_safety(text) or facts["safety_indicators"]:
            data["dispute_type"] = "safety_incident"
            data["safety_flag"] = True
        else:
            data["safety_flag"] = data.get("dispute_type") == "safety_incident"
        if data["dispute_type"] in _RESOLUTION and not data.get("requested_resolution"):
            data["requested_resolution"] = requested_resolution(data["dispute_type"], facts)
        mi = data.get("missing_info")
        if not (isinstance(mi, list) and all(isinstance(x, str) for x in mi)):
            data["missing_info"] = missing_info(data["dispute_type"], facts, self.lang)
        return data


def _match_hint(match: dict | None) -> str:
    """What the platform's trip matcher found, passed to the model as a classification hint."""
    if not match or not match.get("trip_id"):
        return ""
    from app.tools.fixtures import get_trip_data
    td = get_trip_data(match["trip_id"])
    keep = {k: td.get(k) for k in ("status", "start_time", "scheduled_time", "upfront_quote", "estimated_fare", "actual_fare",
                                   "fare_charged", "cancellation_fee", "cancellation_fee_charged", "cleaning_fee_charged",
                                   "route_deviated", "excess_distance_km") if td.get(k) is not None}
    return ("The platform matched this complaint to that trip from the rider's recent trips "
            f"(confidence {match.get('confidence')}; reasons: {'; '.join(match.get('reasons') or [])}).\n"
            f"Trip record summary (hint for classification only; do not copy into extracted_facts): "
            f"{match.get('route')} {keep}\n\n")
