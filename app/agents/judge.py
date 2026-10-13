"""Judge agent: read-only, neutral arbiter.

Receives both advocates' cases, then independently re-queries the tools (it does not take either side's word),
applies the policy thresholds / refund formula and outputs a ruling JSON.
Confidence below the escalation threshold -> escalate to a human instead of ruling.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents import analysis
from app.config import settings
from app.i18n import L, CUR
from app.models import Ruling


class Judge(BaseAgent):
    role = "judge"
    name = "judge"
    parse_schema = Ruling

    def system_prompt(self) -> str:
        return (
            "You are the JUDGE AGENT of the RydeResolve ride-hailing dispute platform: a neutral, read-only arbiter.\n\n"
            "Duties:\n"
            "1. You receive the cases built by the rider advocate and the driver advocate.\n"
            "2. Do NOT trust either side. Independently call the tools to verify the key evidence "
            "(GPS, app events, traffic reference, policy).\n"
            "3. Apply the numeric thresholds and refund formula from the relevant policy to reach a ruling. "
            "Cite policy clauses by ID (CN-1..CN-4, RD-1..RD-3) in evidence_cited.\n"
            "4. Give a confidence_score (0-1). If it is below 0.6 you must not issue a final ruling: "
            "output escalation_required=true with a case summary instead.\n\n"
            "Output strict JSON (no code fences):\n"
            '{"dispute_id":"...","ruling":"upheld|rejected|partial|escalated",'
            '"refund_amount":null,"confidence_score":0.0,"reasoning":"...",'
            '"evidence_cited":[],"escalation_required":false,"escalation_summary":null}'
        )

    def build_user_message(self, context: dict) -> str:
        t = context["ticket"]
        cases = context.get("cases", [])
        # Join parts; do not write `... + X if c else "" + ...` (+ binds tighter than the ternary).
        parts = ["Dispute ticket:\n" + json.dumps(t, ensure_ascii=False, indent=2)]
        if cases:
            parts.append("Rider advocate's case:\n" + json.dumps(cases[0], ensure_ascii=False, indent=2))
        if len(cases) > 1:
            parts.append("Driver advocate's case:\n" + json.dumps(cases[1], ensure_ascii=False, indent=2))
        parts.append("Independently call the tools to verify the key evidence, then output the ruling JSON.")
        return "\n\n".join(parts)

    def build_playbook(self, context: dict) -> list[dict]:
        lg = self.lang
        t = context["ticket"]
        trip_id = t["trip_id"]
        dtype = t["dispute_type"]
        steps = [
            {"_thought": L(lg, "Independent check: re-fetch the trip data.", "独立核验：重新调取行程数据。"), "name": "get_trip_data", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Independent check: re-fetch the GPS trace.", "独立核验：重新调取 GPS 轨迹。"), "name": "get_gps_telemetry", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Independent check: re-fetch the chat log.", "独立核验：重新调取聊天记录。"), "name": "get_chat_logs", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Independent check: re-fetch the app events.", "独立核验：重新调取 App 事件。"), "name": "get_app_events", "args": {"trip_id": trip_id}},
        ]
        if dtype == "route_deviation":
            steps.append({"_thought": L(lg, "Independent check: re-fetch the traffic reference.", "独立核验：重新调取交通参考。"), "name": "get_traffic_reference", "args": {"trip_id": trip_id}})
        steps += [
            {"_thought": L(lg, "Check the rider profile.", "核验乘客画像。"), "name": "get_rider_profile", "args": {"rider_id": t["rider_id"]}},
            {"_thought": L(lg, "Check the driver profile.", "核验司机画像。"), "name": "get_driver_profile", "args": {"driver_id": t["driver_id"]}},
            {"_thought": L(lg, "Fetch the applicable policy and rule by its thresholds and formula.", "调取适用政策，按阈值与公式裁决。"), "name": "get_policy", "args": {"dispute_type": dtype}},
        ]
        return steps

    def build_final(self, context: dict, gathered: dict) -> dict:
        t = context["ticket"]
        if t["dispute_type"] == "route_deviation":
            return self._route_deviation_ruling(t, gathered, context)
        return self._no_show_ruling(t, gathered, context)

    # ---------------- route deviation ----------------
    def _route_deviation_ruling(self, t: dict, g: dict, ctx: dict) -> dict:
        lg = self.lang
        f = analysis.route_deviation_facts(
            g.get("get_trip_data", {}), g.get("get_policy", {}),
            (g.get("get_traffic_reference") or {}).get("traffic_reference"), lg)
        conf = 0.6
        if (g.get("get_traffic_reference") or {}).get("traffic_reference"):
            conf += 0.2
        if f["deviation_pct"] > f["tolerance_pct"] + 5:
            conf += 0.1
        if g.get("get_trip_data", {}).get("fare_breakdown"):
            conf += 0.02
        conf = round(min(0.9, conf), 2)

        refund = f["policy_refund"]
        full_overcharge = round(f["fare_charged"] - f["optimal_fare"], 2)
        if refund == 0:
            ruling = "rejected"
        elif refund >= full_overcharge - 0.01:
            ruling = "upheld"
        else:
            ruling = "partial"

        evidence = [
            L(lg, f"Independent check: actual {f['actual_km']} km vs optimal {f['optimal_km']} km, deviation {f['deviation_pct']}% (tolerance {f['tolerance_pct']}%)",
                  f"独立核验：实际 {f['actual_km']}km vs 最优 {f['optimal_km']}km，偏差 {f['deviation_pct']}%（阈值 {f['tolerance_pct']}%）"),
            L(lg, f"Independent check: {f['traffic_note']}", f"独立核验：{f['traffic_note']}"),
            L(lg, f"Refund formula (RD-2): max(0, {f['actual_km']} - {f['optimal_km']}*1.15) * {f['per_km_rate']} = {CUR}{refund}",
                  f"退费公式 (RD-2)：max(0, {f['actual_km']}-{f['optimal_km']}*1.15)*{f['per_km_rate']} = {CUR}{refund}"),
        ]
        reasoning = L(lg,
            f"Trip data independently shows a {f['deviation_pct']}% deviation, above the {f['tolerance_pct']}% tolerance (RD-1). "
            f"{f['traffic_note']}, so the RD-3 traffic exemption does not apply. "
            f"Under RD-2 the excess is refunded: {CUR}{refund} (rider claimed {CUR}{full_overcharge}, only partly supported).",
            f"GPS/行程数据独立核验偏差 {f['deviation_pct']}% 超 {f['tolerance_pct']}% 阈值。"
            f"{f['traffic_note']}，故不适用 RD-3 豁免。"
            f"依 RD-2 退超出阈值部分 {CUR}{refund}（乘客主张 {CUR}{full_overcharge}，仅部分支持）。")

        if conf < settings.escalation_threshold:
            return self._escalate(t, ctx, conf, evidence, reasoning)
        return {
            "dispute_id": t["dispute_id"], "ruling": ruling, "refund_amount": refund,
            "confidence_score": conf, "reasoning": reasoning, "evidence_cited": evidence,
            "escalation_required": False, "escalation_summary": None,
            "_summary": L(lg, f"Ruling {ruling}, confidence {conf}.", f"裁决 {ruling}，置信度 {conf}。"),
        }

    # ---------------- no-show cancellation fee ----------------
    def _no_show_ruling(self, t: dict, g: dict, ctx: dict) -> dict:
        lg = self.lang
        f = analysis.no_show_facts(
            g.get("get_trip_data", {}), g.get("get_gps_telemetry", {}),
            g.get("get_app_events", {}), g.get("get_chat_logs", {}),
            g.get("get_policy", {}))
        points = len((g.get("get_gps_telemetry") or {}).get("points", []))
        ev_arrived = any(e.get("event_type") == "driver_arrived" for e in (g.get("get_app_events") or {}).get("events", []))
        contradiction = ev_arrived and f["near_points"] == 0
        conf = 0.6
        conf += 0.15 if points >= 4 else 0
        conf += 0.1 if f["contact_attempts"] >= 1 else 0
        conf += 0.1 if (f["driver_arrived"] and f["dwell_min"] >= f["free_wait_min"]) else 0
        if contradiction:
            conf -= 0.25
        if points < 3:
            conf -= 0.1
        conf = round(max(0.1, min(0.9, conf)), 2)

        refund = f["policy_refund"]
        if refund == 0:
            ruling = "rejected"
        elif refund >= f["no_show_fee"] - 0.01:
            ruling = "upheld"
        else:
            ruling = "partial"

        cm = f["conditions_met"]
        evidence = [
            L(lg, f"Independent GPS check (CN-1): {f['near_points']} stopped point(s) within {f['pickup_proximity_m']} m of pickup, arrived={f['driver_arrived']}",
                  f"独立核验 GPS：上车点 {f['pickup_proximity_m']}m 内停车点 {f['near_points']} 个，到达={f['driver_arrived']}"),
            L(lg, f"Independent wait check (CN-2): dwell {f['dwell_min']} min vs free wait {f['free_wait_min']} min, met={cm['dwell_past_free_window']}",
                  f"独立核验等待：停留 {f['dwell_min']} 分钟，免费等待 {f['free_wait_min']} 分钟，达标={cm['dwell_past_free_window']}"),
            L(lg, f"Independent contact check (CN-3): {f['contact_attempts']} contact attempt(s) (required {f['min_contact_attempts']})",
                  f"独立核验联系：联系尝试 {f['contact_attempts']} 次（要求 {f['min_contact_attempts']}）"),
            L(lg, f"Policy conditions: {cm}", f"政策条件：{cm}"),
        ]
        reasoning = L(lg,
            f"Independent check: arrived={cm['driver_arrived_proximity']}, waited long enough={cm['dwell_past_free_window']}, "
            f"contacted rider={cm['contact_attempted']}. ",
            f"独立核验：到达={cm['driver_arrived_proximity']}、等待达标={cm['dwell_past_free_window']}、联系达标={cm['contact_attempted']}。")
        if f["all_conditions_met"]:
            reasoning += L(lg, "All conditions met, so under CN-4 the cancellation fee stands; no refund.",
                               "全部条件满足，依 CN-4 取消费有效，不予退费。")
        else:
            missing = [k for k, v in cm.items() if not v]
            reasoning += L(lg, f"Conditions not all met ({missing}); under CN-4 refund {CUR}{refund}.",
                               f"条件未全满足（{missing}），依 CN-4 应退 {CUR}{refund}。")

        if conf < settings.escalation_threshold:
            return self._escalate(t, ctx, conf, evidence, reasoning)
        return {
            "dispute_id": t["dispute_id"], "ruling": ruling, "refund_amount": refund,
            "confidence_score": conf, "reasoning": reasoning, "evidence_cited": evidence,
            "escalation_required": False, "escalation_summary": None,
            "_summary": L(lg, f"Ruling {ruling}, confidence {conf}.", f"裁决 {ruling}，置信度 {conf}。"),
        }

    def _escalate(self, t: dict, ctx: dict, conf: float, evidence: list[str], reasoning: str) -> dict:
        lg = self.lang
        cases = ctx.get("cases", [])
        rc = cases[0].get("claim") if cases else "N/A"
        dc = cases[1].get("claim") if len(cases) > 1 else "N/A"
        thr = settings.escalation_threshold
        summary = L(lg,
            f"Confidence {conf} < {thr}: the evidence is not enough for an automatic ruling; escalated to a human. "
            f"Rider's claim: {rc}; driver's claim: {dc}. Verification found: {reasoning}",
            f"置信度 {conf} < {thr}，证据不足以自动裁决，升级人工。乘客方主张：{rc}；司机方主张：{dc}。核验发现：{reasoning}")
        return {
            "dispute_id": t["dispute_id"], "ruling": "escalated", "refund_amount": None,
            "confidence_score": conf, "reasoning": reasoning, "evidence_cited": evidence,
            "escalation_required": True, "escalation_summary": summary,
            "_summary": L(lg, f"Confidence {conf} too low; escalating for human review.", f"置信度 {conf} 不足，升级人工复核。"),
        }

    def _fill_defaults(self, data: dict, context: dict) -> dict:
        # In LLM mode the model may omit dispute_id / escalation fields; fill them in.
        data.setdefault("dispute_id", context["ticket"]["dispute_id"])
        data.setdefault("refund_amount", None)
        data.setdefault("confidence_score", 0.5)
        data.setdefault("evidence_cited", [])
        data.setdefault("escalation_required", False)
        data.setdefault("escalation_summary", None)
        return data
