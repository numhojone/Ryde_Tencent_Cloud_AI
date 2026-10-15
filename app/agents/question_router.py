"""Question router: should a support agent's question go to the rider or to the driver?

Deterministic first. The question is scored for each party:
- who it is about: the party named first ("did the driver ...", "was the rider ...") scores 3
- topic words: what only the driver can say (waiting, calling, messaging, arriving at pickup, the route taken
  and why, traffic or closures, the vehicle, drop-off, the driver's account) or only the rider can say
  (where they were, photos or evidence they hold, what they saw, felt or were told, their luggage, their account)
A clear lead (2 points or more) decides. Otherwise it is "unsure": in Live AI mode one short model call may
decide; if that is not available or fails, it goes to the rider, and the console shows the choice so the
person can change it before anything is sent.
"""
from __future__ import annotations

import json
import re

from app.i18n import L

DRIVER_WORDS = ("wait", "waited", "waiting", "call", "called", "calling", "phone", "message", "messaged", "texted",
                "arrive", "arrived", "arrival", "pickup point", "pick-up point", "route", "detour", "took the", "go through",
                "went through", "drive", "drove", "driving", "road", "traffic", "jam", "closure", "closed", "fire",
                "expressway", "pie", "ecp", "cte", "aye", "vehicle", "car", "seat", "clean", "stain", "drop-off",
                "dropoff", "drop off", "dropped", "cancel", "cancelled", "cancelling", "speed", "brake",
                "司机", "等", "打电话", "路线", "绕路", "路况", "堵车", "车辆", "下车")
RIDER_WORDS = ("where were", "where was the rider", "whereabouts", "photo", "picture", "screenshot", "evidence",
               "receipt", "saw", "see", "seen", "felt", "feel", "unsafe", "scared", "told", "luggage", "bag", "lobby",
               "wearing", "notified", "notification", "quote", "booked", "booking", "乘客", "照片", "行李", "看到", "感觉")
_DRIVER_SUBJ = re.compile(r"\b(?:the\s+)?driver(?:'s)?\b|司机")
_RIDER_SUBJ = re.compile(r"\b(?:the\s+)?(?:rider|passenger|customer)(?:'s)?\b|乘客")
# the grammatical subject of a question: "(why|where|...) did|was|... <subject> ..."
_SUBJECT = re.compile(r"^\s*(?:(?:why|where|when|how|what|which|who)\s+)?(?:did|do|does|was|were|is|are|has|have|had|can|could|"
                      r"would|will)\s+(the\s+driver|the\s+rider|the\s+passenger|you|u|ya)\b")


def _hits(low: str, words) -> list[str]:
    out = []
    for w in words:
        if re.search(r"[㐀-鿿]", w):
            if w in low:
                out.append(w)
        elif re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
            out.append(w)
    return out


def route_question(question: str, lang: str = "en") -> dict:
    """{recipient: rider | driver, confident: bool, scores, reason}. Deterministic, on the spelling-corrected text."""
    from app.agents.rephrase import fix_text
    low = fix_text(question or "").lower()
    d_hits, r_hits = _hits(low, DRIVER_WORDS), _hits(low, RIDER_WORDS)
    d_score, r_score = float(len(d_hits)), float(len(r_hits))
    dm, rm = _DRIVER_SUBJ.search(low), _RIDER_SUBJ.search(low)
    subj = _SUBJECT.search(low)
    first = None
    if subj and subj.group(1) in ("you", "u", "ya"):
        # written as if speaking to one party: "did you call the rider?" is for the driver, and the other way round
        if rm and not dm:
            first = "driver"; d_score += 3
        elif dm and not rm:
            first = "rider"; r_score += 3
    elif subj:
        first = "driver" if "driver" in subj.group(1) else "rider"
        if first == "driver":
            d_score += 3
        else:
            r_score += 3
    elif dm and (not rm or dm.start() < rm.start()):
        first = "driver"; d_score += 3
    elif rm:
        first = "rider"; r_score += 3
    lead = d_score - r_score
    if abs(lead) >= 2:
        who = "driver" if lead > 0 else "rider"
        words = (d_hits if who == "driver" else r_hits)[:3]
        about = ([L(lang, f"about the {who}", "关于司机" if who == "driver" else "关于乘客")] if first == who else []) + words
        return {"recipient": who, "confident": True, "scores": {"driver": d_score, "rider": r_score},
                "reason": L(lang, "Auto: " + ", ".join(about), "自动：" + "、".join(about))}
    return {"recipient": "rider", "confident": False, "scores": {"driver": d_score, "rider": r_score},
            "reason": L(lang, "Auto: unsure who this is about, so it goes to the rider. Change it if needed.",
                              "自动：无法确定问题针对谁，默认发给乘客。如有需要请修改。")}


async def route(question: str, *, mode: str | None = None, lang: str = "en") -> dict:
    """Deterministic routing; when it is unsure and Live AI is on, one short model call may decide."""
    res = route_question(question, lang)
    if res["confident"]:
        return {**res, "used_model": False}
    from app.config import settings
    if (mode or settings.effective_mode) != "llm" or not settings.has_api_key:
        return {**res, "used_model": False}
    try:
        from app.llm import llm_client
        r = await llm_client.chat(messages=[
            {"role": "system", "content": "A ride-hailing support agent wrote a question about a dispute. Who can answer it: "
                                          'the rider or the driver? Reply with JSON only: {"recipient":"rider"} or {"recipient":"driver"}.'},
            {"role": "user", "content": question[:400]}], max_tokens=20, temperature=0)
        who = (json.loads(re.search(r"\{.*\}", r.content or "", re.S).group(0)) or {}).get("recipient")
        if who in ("rider", "driver"):
            return {**res, "recipient": who, "used_model": True,
                    "reason": L(lang, f"Auto (model): the {who}", "自动（模型）：" + ("司机" if who == "driver" else "乘客"))}
    except Exception:  # noqa: BLE001
        pass
    return {**res, "used_model": False}
