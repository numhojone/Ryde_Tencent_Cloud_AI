"""Ruling thresholds from Ryde Dispute Resolution Policy v2.1 section 6, applied deterministically.

6.1 categories, 6.2 monetary tiers, 6.3 confidence. Pure code: the same facts always give the same path.
"""
from __future__ import annotations

from app.i18n import L, CUR
from app.agents.analysis import has_fraud_flag

BASE_CONF = 0.80
FRAUD_CONF = 0.95
ROUTE_MAX_KM = 2.0


def assess(dtype: str, facts: dict, confidence: float, profiles: list[dict], lang: str = "en") -> dict:
    fraud = has_fraud_flag(*profiles)
    required = FRAUD_CONF if fraud else None            # 6.3: fraud flag raises the bar to 95% whatever the value
    reasons: list[str] = []
    path = "ai_final"
    human_approval = False                               # AI may recommend, human must approve
    clause = "6.1"

    if dtype == "safety_incident":
        return {"path": "human_review", "required_confidence": None, "escalation_required": True, "human_approval_only": False,
                "fraud_flag": fraud, "clause": "5.2", "reasons": [L(lang, "Safety incident: AI may not rule or recommend (policy 5.2).", "安全事件：AI 不得裁决或建议处理方案（政策 5.2）。")]}

    if dtype == "route_deviation":
        required = max(required or 0, BASE_CONF)
        path = "ai_ruling_if_confident"; clause = "6.1"
        if facts.get("deviation_km", 0) > ROUTE_MAX_KM:
            human_approval = True; path = "human_review"
            reasons.append(L(lang, f"Deviation {facts['deviation_km']} km exceeds the {ROUTE_MAX_KM} km limit for AI rulings (6.1): the AI recommendation needs human approval.",
                                   f"偏差 {facts['deviation_km']} 公里超过 AI 自行裁决的 {ROUTE_MAX_KM} 公里上限（6.1）：AI 建议需人工批准。"))
    elif dtype == "fare_dispute":
        amt = abs(facts.get("difference", 0))
        clause = "6.2"
        if amt > 50:
            path = "human_review"; human_approval = True
            reasons.append(L(lang, f"Disputed amount {CUR}{amt} is over {CUR}50: always human review (6.2).", f"争议金额 {CUR}{amt} 超过 {CUR}50：必须人工复核（6.2）。"))
        elif amt >= 10:
            required = max(required or 0, BASE_CONF); path = "ai_ruling_if_confident"
        else:
            path = "ai_final"
    elif dtype == "property_damage":
        clause = "6.1"
        if facts.get("claim_type") == "repair" or facts.get("claimed_amount", 0) > 50:
            path = "human_review"; human_approval = True
            reasons.append(L(lang, "Repair claims (over S$50) always go to human review (6.1).", "维修类索赔（超过 S$50）必须人工复核（6.1）。"))
        else:
            required = max(required or 0, BASE_CONF); path = "ai_ruling_if_confident"
    else:                                                # no_show_charge
        path = "ai_final"; clause = "6.1"

    esc = human_approval
    if required is not None and confidence < required:
        esc = True; human_approval = False
        reasons.append(L(lang, f"Confidence {confidence:.2f} is below the required {required:.2f}" + (" (raised to 95% because a party has a fraud flag, 6.3)" if fraud else " (6.2)") + ".",
                               f"置信度 {confidence:.2f} 低于所需的 {required:.2f}" + ("（因当事人有欺诈标记，门槛提高到 95%，6.3）" if fraud else "（6.2）") + "。"))
        path = "human_review"
    return {"path": path, "required_confidence": required, "escalation_required": esc, "human_approval_only": human_approval,
            "fraud_flag": fraud, "clause": clause, "reasons": reasons}
