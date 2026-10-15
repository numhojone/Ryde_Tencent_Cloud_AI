"""Judge agent: read-only, neutral arbiter working under Ryde Dispute Resolution Policy v2.1.

Receives both advocates' cases, re-queries the tools itself, applies the clause rules, calibrates a confidence
score from the four factors in policy 6.3 and applies the section 6 thresholds in code (app/thresholds.py).
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents import analysis as A
from app.agents import cases
from app.config import settings
from app.i18n import L, CUR
from app.models import Ruling
from app import thresholds

CLAUSE_WORDS = {
    "route_deviation": "1.2 to 1.4", "no_show_charge": "2.1 to 2.4", "fare_dispute": "3.2 to 3.4", "property_damage": "4.2 to 4.4",
}


def case_tags(dtype: str, f: dict) -> set[str]:
    t: set[str] = set()
    if dtype == "route_deviation":
        if f.get("traffic_justified"): t.add("traffic_justified")
        if not f.get("rider_informed"): t.add("rider_not_informed")
        if f.get("over_tolerance"): t.add("deviation_over_1km")
    elif dtype == "no_show_charge":
        if f.get("arrived_in_time"): t.add("driver_arrived")
        if f.get("driver_messages") == 0: t.add("no_message")
        if f.get("driver_calls") == 0: t.add("no_call")
        if f.get("policy_refund", 0) > 0: t.add("fee_voided")
    elif dtype == "fare_dispute":
        if f.get("surge_increased"): t.add("surge_increase")
        if not f.get("rider_notified"): t.add("rider_not_notified")
        if f.get("surge_only"): t.add("surge_only_difference")
    return t


def precedent_alignment(dtype: str, f: dict, label: str, prec: dict | None) -> tuple[float, str | None]:
    plist = (prec or {}).get("precedents") or []
    if not plist:
        return 0.7, None
    mine = case_tags(dtype, f)
    best = max(plist, key=lambda p: len(mine & set(p.get("tags", []))))
    overlap = len(mine & set(best.get("tags", [])))
    if best.get("ruling") == label or (best.get("ruling") == "upheld" and label == "partial"):
        return 1.0, best["case_id"]
    if overlap >= 2:
        return 0.5, best["case_id"]          # same facts, different outcome: a real conflict
    return 0.9, best["case_id"]              # distinguishable facts


def completeness(dtype: str, g: dict) -> float:
    n = lambda tool, key: len((g.get(tool) or {}).get(key, []) or [])
    checks = {
        "route_deviation": [n("get_gps_telemetry", "points") >= 3, n("get_chat_logs", "messages") >= 2, bool((g.get("get_traffic_reference") or {}).get("traffic_conditions")), bool((g.get("get_fare_breakdown") or {}).get("fare_breakdown"))],
        "no_show_charge": [n("get_gps_telemetry", "points") >= 3, n("get_chat_logs", "messages") >= 2, n("get_app_events", "events") >= 2],
        "fare_dispute": [bool((g.get("get_fare_breakdown") or {}).get("surge_pricing_log")), bool((g.get("get_fare_breakdown") or {}).get("fare_breakdown")), n("get_chat_logs", "messages") >= 1],
        "property_damage": [bool(((g.get("get_damage_evidence") or {}).get("damage_evidence") or {}).get("photos")), n("get_chat_logs", "messages") >= 1, n("get_app_events", "events") >= 1],
    }.get(dtype, [False])
    return round(sum(checks) / len(checks), 2)


def clarity(dtype: str, f: dict) -> float:
    if dtype == "route_deviation":
        return {"within_tolerance": 1.0, "unjustified": 0.95, "justified_and_informed": 0.9, "justified_not_informed": 0.75}.get(f["outcome"], 0.7)
    if dtype == "no_show_charge":
        return 0.4 if f.get("gps_app_contradiction") else 1.0
    if dtype == "fare_dispute":
        return 0.6 if f["outcome"] == "unexplained_difference" else 1.0
    if dtype == "property_damage":
        return 0.95
    return 0.5


class Judge(BaseAgent):
    role = "judge"
    name = "judge"
    parse_schema = Ruling

    def system_prompt(self) -> str:
        return (
            "You are the JUDGE AGENT of the RydeResolve ride-hailing dispute platform: a neutral, read-only arbiter applying the "
            "Ryde Dispute Resolution Policy v2.1.\n\n"
            "Duties:\n"
            "1. You receive the rider advocate's and driver advocate's cases. Do NOT trust either side: independently call the tools to verify the key "
            "evidence (trip data, GPS, chat, app events, traffic reference, fare breakdown / surge log, damage evidence, policy, search_precedents).\n"
            "2. Apply the numbered clauses: route deviation 1.2-1.4 (tolerance 1 km; refund = deviation km x distance rate; traffic-justified deviations exempt; "
            "driver must inform the rider), no-show 2.1-2.4 (5 min free wait; driver must message AND call; fee S$5; driver no-show voids the fee), "
            "fare 3.2-3.4 (surge increase without notification is refunded), property damage 4.2-4.4 (photos within 24 h, in-app camera, linked to trip; "
            "cleaning capped at S$50). Cite clauses by number in evidence_cited.\n"
            "3. Safety incidents (section 5) are never ruled by AI. If you see safety indicators, set ruling escalated and say so.\n"
            "4. Give confidence_score (0-1) from: evidence completeness, policy clarity, precedent alignment, party credibility (6.3). "
            "Escalation thresholds from section 6 are enforced separately in code after your answer; report your honest assessment.\n"
            "5. If the policy gives a partial remedy, use ruling partial with the exact computed amount; goodwill credits (2.4) go in goodwill_credit, not refund_amount.\n\n"
            "Output strict JSON (no code fences):\n"
            '{"dispute_id":"...","ruling":"upheld|rejected|partial|escalated","refund_amount":null,"confidence_score":0.0,'
            '"reasoning":"...","evidence_cited":[],"escalation_required":false,"escalation_summary":null,"goodwill_credit":null,"policy_clauses":[]}'
        )

    def build_user_message(self, context: dict) -> str:
        parts = ["Dispute ticket:\n" + json.dumps(context["ticket"], ensure_ascii=False, indent=2)]
        cs = context.get("cases", [])
        if cs:
            parts.append("Rider advocate's case:\n" + json.dumps(cs[0], ensure_ascii=False, indent=2))
        if len(cs) > 1:
            parts.append("Driver advocate's case:\n" + json.dumps(cs[1], ensure_ascii=False, indent=2))
        parts.append("Independently call the tools to verify the key evidence, then output the ruling JSON.")
        return "\n\n".join(parts)

    def build_playbook(self, context: dict) -> list[dict]:
        return cases.playbook(self.lang, context["ticket"])

    def build_final(self, context: dict, g: dict) -> dict:
        lg = self.lang
        t = context["ticket"]
        dtype = t["dispute_type"]
        f = cases.compute_facts(dtype, g)
        label = f["ruling_label"]
        refund = f["policy_refund"]
        goodwill = f.get("goodwill_credit") or None
        prec_score, prec_id = precedent_alignment(dtype, f, label, g.get("search_precedents"))
        cred = A.credibility_score(g.get("get_rider_profile"), g.get("get_driver_profile"))
        comp, clar = completeness(dtype, g), clarity(dtype, f)
        conf = A.calibrate_confidence(comp, clar, prec_score, cred)
        profiles = [g.get("get_rider_profile") or {}, g.get("get_driver_profile") or {}]
        th = thresholds.assess(dtype, f, conf, profiles, lg)

        evidence = cases.evidence_lines(dtype, f, lg)
        if prec_id:
            evidence.append(L(lg, f"Precedent {prec_id} considered (alignment {prec_score})", f"参考先例 {prec_id}（一致度 {prec_score}）"))
        reasoning = self._reason(dtype, f, lg)
        out = {
            "dispute_id": t["dispute_id"], "ruling": label, "refund_amount": refund, "goodwill_credit": goodwill,
            "confidence_score": conf, "reasoning": reasoning, "evidence_cited": evidence,
            "policy_clauses": cases.clauses_for(dtype, f), "escalation_required": False, "escalation_summary": None,
            "confidence_breakdown": {"evidence_completeness": comp, "policy_clarity": clar, "precedent_alignment": prec_score, "party_credibility": cred},
            "precedent_id": prec_id,
        }
        return self.apply_thresholds(out, th, lg, strict=settings.strict_escalation)

    @staticmethod
    def apply_thresholds(out: dict, th: dict, lg: str, strict: bool = False) -> dict:
        out["policy_path"] = {"path": th["path"], "required_confidence": th["required_confidence"], "fraud_flag": th["fraud_flag"],
                              "clause": th["clause"], "reasons": th["reasons"], "human_approval_only": th["human_approval_only"]}
        if not th["escalation_required"]:
            out["_summary"] = L(lg, f"Ruling {out['ruling']}, confidence {out['confidence_score']}.", f"裁决 {out['ruling']}，置信度 {out['confidence_score']}。")
            return out
        out["escalation_required"] = True
        why = ("; " if lg == "en" else "；").join(th["reasons"])
        if th["human_approval_only"] and not strict:
            # AI recommendation stands, but a human must approve before it is executed
            out["escalation_summary"] = L(lg, f"AI recommendation ({out['ruling']}, {CUR}{out['refund_amount']}) requires human approval: {why}",
                                              f"AI 建议（{out['ruling']}，{CUR}{out['refund_amount']}）需人工批准：{why}")
            out["_summary"] = L(lg, "Recommendation issued; human approval required.", "已给出建议，需人工批准。")
            return out
        out["recommendation"] = {"ruling": out["ruling"], "refund_amount": out["refund_amount"]}
        out["escalation_summary"] = L(lg, f"Escalated under policy section 6: {why} AI recommendation: {out['ruling']}, {CUR}{out['refund_amount']}.",
                                          f"依政策第 6 节升级人工：{why} AI 建议：{out['ruling']}，{CUR}{out['refund_amount']}。")
        out["ruling"], out["refund_amount"] = "escalated", None
        out["_summary"] = L(lg, "Thresholds not met; escalating.", "未达阈值，升级人工。")
        return out

    def post_process_llm(self, ruling: dict, ticket: dict, g: dict) -> dict:
        """LLM path: the model decides; section 6 thresholds are still enforced in code using the facts the tools returned."""
        lg, dtype = self.lang, ticket["dispute_type"]
        if not isinstance(ruling, dict) or dtype not in cases.RULABLE:
            return ruling
        try:
            f = cases.compute_facts(dtype, g)
        except Exception:  # noqa: BLE001
            return ruling
        conf = float(ruling.get("confidence_score") or 0.5)
        profiles = [g.get("get_rider_profile") or {}, g.get("get_driver_profile") or {}]
        th = thresholds.assess(dtype, f, conf, profiles, lg)
        ruling.setdefault("policy_clauses", cases.clauses_for(dtype, f))
        if ruling.get("ruling") == "escalated":
            ruling["escalation_required"] = True
            ruling["policy_path"] = {"path": "human_review", "required_confidence": th["required_confidence"], "fraud_flag": th["fraud_flag"], "clause": th["clause"], "reasons": th["reasons"], "human_approval_only": False}
            return ruling
        # keep the model's numbers; add the deterministic cross-check
        ruling["policy_check"] = {"ruling": f["ruling_label"], "refund_amount": f["policy_refund"],
                                  "agrees": f["ruling_label"] == ruling.get("ruling") and abs((ruling.get("refund_amount") or 0) - f["policy_refund"]) < 0.02}
        return self.apply_thresholds(ruling, th, lg, strict=settings.strict_escalation)

    def _reason(self, dtype: str, f: dict, lg: str) -> str:
        if dtype == "route_deviation":
            return L(lg,
                f"The trip ran {f['deviation_km']} km over the estimate, beyond the 1 km tolerance (1.3). "
                f"{'Traffic incidents ' + ', '.join(f['matched_incidents']) + ' justify the reroute (1.4), so the full excess is not owed. ' if f['traffic_justified'] else 'No traffic incident justifies it (1.4). '}"
                f"{'The driver did inform the rider (1.2). ' if f['rider_informed'] else 'The driver did not inform the rider (1.2). '}"
                f"Refund = {f['deviation_km']} km x {CUR}{f['distance_rate']} = {CUR}{f['policy_refund']}.",
                f"行程比预估多 {f['deviation_km']} 公里，超出 1 公里容忍范围（1.3）。"
                f"{'交通事件 ' + ', '.join(f['matched_incidents']) + ' 使改道合理（1.4），故不必退全部超出费用。' if f['traffic_justified'] else '没有交通事件能说明绕行合理（1.4）。'}"
                f"{'司机已告知乘客（1.2）。' if f['rider_informed'] else '司机未告知乘客（1.2）。'}"
                f"退款 = {f['deviation_km']} 公里 x {CUR}{f['distance_rate']} = {CUR}{f['policy_refund']}。")
        if dtype == "no_show_charge":
            ok = f["outcome"] == "fee_valid"
            return L(lg,
                f"Driver arrived in time={f['arrived_in_time']}, waited the free period={f['waited_free_period']}, messages={f['driver_messages']}, calls={f['driver_calls']}. "
                + ("All conditions of 2.1 to 2.3 are met, so the S$5 fee stands (2.2)." if ok else f"Outcome {f['outcome']} (clause {f['clause']}): fee reversed."),
                f"司机按时到达={f['arrived_in_time']}，等满免费期={f['waited_free_period']}，消息 {f['driver_messages']} 条，通话 {f['driver_calls']} 次。"
                + ("条款 2.1 至 2.3 的条件均满足，S$5 费用成立（2.2）。" if ok else f"结果 {f['outcome']}（条款 {f['clause']}）：撤销费用。"))
        if dtype == "fare_dispute":
            return L(lg,
                f"Surge rose from {f['surge_quote']}x to {f['surge_trip_start']}x before pickup and the rider was {'' if f['rider_notified'] else 'not '}notified (3.3). "
                f"The {CUR}{f['difference']} difference equals the surge amount, so it is refunded in full ({CUR}{f['policy_refund']}) (3.4).",
                f"上车前动态系数由 {f['surge_quote']}x 升至 {f['surge_trip_start']}x，乘客{'已' if f['rider_notified'] else '未'}被通知（3.3）。"
                f"{CUR}{f['difference']} 差额等于动态加价，全额退还 {CUR}{f['policy_refund']}（3.4）。")
        return L(lg,
            f"Claim {f['claim_type']} of {CUR}{f['claimed_amount']}: verifiable photos {f['verifiable_photos']}, submitted within 24 h {f['submitted_in_24h']} (4.2). "
            f"{'The claim is valid.' if f['claim_valid'] else 'The evidence does not meet the requirements, so the fee is reversed (4.4): ' + CUR + str(f['policy_refund']) + '.'}",
            f"{f['claim_type']} 索赔 {CUR}{f['claimed_amount']}：可核验照片 {f['verifiable_photos']} 张，24 小时内提交={f['submitted_in_24h']}（4.2）。"
            f"{'索赔成立。' if f['claim_valid'] else '证据不符合要求，撤销费用（4.4）：' + CUR + str(f['policy_refund']) + '。'}")

    def _fill_defaults(self, data: dict, context: dict) -> dict:
        data.setdefault("dispute_id", context["ticket"]["dispute_id"])
        data.setdefault("refund_amount", None)
        data.setdefault("confidence_score", 0.5)
        data.setdefault("evidence_cited", [])
        data.setdefault("escalation_required", False)
        data.setdefault("escalation_summary", None)
        return data
