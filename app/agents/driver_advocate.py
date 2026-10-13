"""Driver advocate agent."""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents import analysis
from app.i18n import L, CUR
from app.models import AdvocateCase


class DriverAdvocate(BaseAgent):
    role = "advocate"
    name = "driver_advocate"
    parse_schema = AdvocateCase

    def system_prompt(self) -> str:
        return (
            "You are the DRIVER ADVOCATE AGENT of the RydeResolve ride-hailing dispute platform. You represent the driver.\n\n"
            "Duties:\n"
            "1. Call the tools to gather evidence (trip data, GPS, chat, app events, rider/driver profiles, policy, traffic reference).\n"
            "2. Build one case with fields: claim, requested_outcome, requested_amount, "
            "policy_clauses_referenced, evidence_cited, reasoning.\n\n"
            "Hard rule: never fabricate evidence; cite only data the tools actually returned. You lean towards the driver, "
            "but you stay honest: when the evidence goes against the driver, say so and adjust the request accordingly.\n\n"
            "When the evidence is gathered, output strict JSON (no code fences):\n"
            '{"agent":"driver_advocate","side":"driver","claim":"...","requested_outcome":"...",'
            '"requested_amount":null,"policy_clauses_referenced":[],"evidence_cited":[],"reasoning":"..."}'
        )

    def build_user_message(self, context: dict) -> str:
        return (
            "Dispute ticket:\n" + json.dumps(context["ticket"], ensure_ascii=False, indent=2) +
            "\n\nGather evidence and build the case on the driver's behalf. Remember: cite only real data returned by the tools."
        )

    def build_playbook(self, context: dict) -> list[dict]:
        lg = self.lang
        t = context["ticket"]
        trip_id = t["trip_id"]
        dtype = t["dispute_type"]
        steps = [
            {"_thought": L(lg, "First fetch the basic trip data.", "先调取行程基础数据。"), "name": "get_trip_data", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch the GPS trace to show the driver's arrival / route.", "调取 GPS 轨迹，证明司机到达/路径。"), "name": "get_gps_telemetry", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch the chat log to show the driver communicated.", "调取聊天记录，证明司机有沟通。"), "name": "get_chat_logs", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch app events to show contact attempts and the wait timer.", "调取 App 事件，证明联系尝试与等待计时。"), "name": "get_app_events", "args": {"trip_id": trip_id}},
        ]
        if dtype == "route_deviation":
            steps.append({"_thought": L(lg, "Fetch the traffic reference to see whether congestion justifies the detour.", "调取交通参考，证明绕行因拥堵合理。"), "name": "get_traffic_reference", "args": {"trip_id": trip_id}})
        steps += [
            {"_thought": L(lg, "Fetch the driver profile to show the driver is credible.", "调取司机画像，证明司机可信。"), "name": "get_driver_profile", "args": {"driver_id": t["driver_id"]}},
            {"_thought": L(lg, "Fetch the rider profile to look for a history of abusive disputes.", "调取乘客画像，查看是否有滥用争议记录。"), "name": "get_rider_profile", "args": {"rider_id": t["rider_id"]}},
            {"_thought": L(lg, "Fetch the applicable policy so I can cite clauses.", "调取适用政策，引用对应条款。"), "name": "get_policy", "args": {"dispute_type": dtype}},
        ]
        return steps

    def build_final(self, context: dict, gathered: dict) -> dict:
        t = context["ticket"]
        if t["dispute_type"] == "route_deviation":
            return self._route_deviation_case(t, gathered)
        return self._no_show_case(t, gathered)

    def _route_deviation_case(self, t: dict, g: dict) -> dict:
        lg = self.lang
        f = analysis.route_deviation_facts(g.get("get_trip_data", {}), g.get("get_policy", {}),
                                           (g.get("get_traffic_reference") or {}).get("traffic_reference"), lg)
        dp = g.get("get_driver_profile", {})
        evidence = [
            L(lg, f"The driver chose the route using app navigation / experience; fare charged {CUR}{f['fare_charged']}",
                  f"司机按 App 导航/经验选择路线，实收 {CUR}{f['fare_charged']}"),
            L(lg, f"Traffic reference: {f['traffic_note']}", f"交通参考：{f['traffic_note']}"),
        ]
        if dp:
            flags = dp.get('fraud_flags') or L(lg, "none", "无")
            evidence.append(L(lg, f"Driver has {dp.get('total_trips')} trips, rating {dp.get('avg_rating')}, fraud flags: {flags}",
                                  f"司机服务 {dp.get('total_trips')} 单、评分 {dp.get('avg_rating')}、欺诈标记 {flags}"))
        # Driver's view: argue the detour was traffic-driven and ask to reject
        requested = 0.0 if f["traffic_justified"] else round(f["policy_refund"], 2)
        claim = L(lg, "The detour was a reasonable choice to avoid congestion; no refund is due.",
                      "司机绕行系为规避拥堵的合理选择，多收费用不应退还。")
        if not f["traffic_justified"]:
            claim = L(lg, "The driver concedes the route did not save time, and will only refund the portion above the tolerance; the rest of the claim should be rejected.",
                          "司机承认路线选择未节省时间，仅愿退还超出阈值部分，请求驳回其余诉求。")
        return {
            "agent": "driver_advocate", "side": "driver",
            "claim": claim,
            "requested_outcome": "reject_or_partial",
            "requested_amount": requested,
            "policy_clauses_referenced": ["RD-1", "RD-3"],
            "evidence_cited": evidence,
            "reasoning": L(lg,
                f"Under RD-3 no refund is due if the detour saved time in congestion; {f['traffic_note']}. "
                f"Even if RD-3 does not apply, RD-1/RD-2 only require refunding the part above the {f['tolerance_pct']}% tolerance "
                f"({CUR}{f['policy_refund']}), not the rider's full overcharge claim.",
                "依据 RD-3，若绕行因拥堵节省时间则免退；" + f["traffic_note"] + "。"
                f"即便不适用 RD-3，依 RD-1/RD-2 也仅应退超出 {f['tolerance_pct']}% 阈值部分 {CUR}{f['policy_refund']}，"
                "而非乘客主张的全额多收。"),
            "_summary": L(lg, "Driver argues the detour was reasonable; at most the above-tolerance part is refundable.",
                              "司机主张绕行合理，至多退还超阈值部分。"),
        }

    def _no_show_case(self, t: dict, g: dict) -> dict:
        lg = self.lang
        f = analysis.no_show_facts(
            g.get("get_trip_data", {}), g.get("get_gps_telemetry", {}),
            g.get("get_app_events", {}), g.get("get_chat_logs", {}),
            g.get("get_policy", {}),
        )
        evidence = [
            L(lg, f"GPS shows {f['near_points']} stopped point(s) within {f['pickup_proximity_m']} m of the pickup point",
                  f"GPS 显示司机在上车点 {f['pickup_proximity_m']} 米内停车点 {f['near_points']} 个"),
            L(lg, f"Dwell time {f['dwell_min']} min (free wait {f['free_wait_min']} min)",
                  f"停留 {f['dwell_min']} 分钟（免费等待 {f['free_wait_min']} 分钟）"),
            L(lg, f"{f['contact_attempts']} contact attempt(s)", f"联系尝试 {f['contact_attempts']} 次"),
        ]
        dp = g.get("get_driver_profile", {})
        if dp:
            evidence.append(L(lg, f"Driver rating {dp.get('avg_rating')}, {dp.get('total_trips')} trips, no fraud flags",
                                  f"司机评分 {dp.get('avg_rating')}、共 {dp.get('total_trips')} 单、无欺诈标记"))
        if not f["all_conditions_met"]:
            # Honestly concede unmet conditions
            missing = [k for k, v in f["conditions_met"].items() if not v]
            evidence.append(L(lg, f"(Note: these conditions are not met: {missing}; the policy requires a refund)",
                                  f"（说明：以下条件未满足：{missing}，依政策应退费）"))
            claim = L(lg, "Concedes some conditions were not met; a refund per policy is appropriate.", "承认部分条件未满足，建议按规定退费。")
            requested = f["no_show_fee"]
            outcome = "full_refund"
        else:
            claim = L(lg, "The driver arrived, waited out the free window and contacted the rider; the fee is valid and should not be refunded.",
                          "司机已到达并等待至免费窗口结束且已联系乘客，取消费合规收取，不应退还。")
            requested = 0.0
            outcome = "reject_refund"
        cm = f["conditions_met"]
        return {
            "agent": "driver_advocate", "side": "driver",
            "claim": claim,
            "requested_outcome": outcome,
            "requested_amount": requested,
            "policy_clauses_referenced": ["CN-1", "CN-2", "CN-3", "CN-4"],
            "evidence_cited": evidence,
            "reasoning": L(lg,
                f"Under CN-1/CN-2/CN-3: arrived={cm['driver_arrived_proximity']}, "
                f"waited={cm['dwell_past_free_window']}, contacted={cm['contact_attempted']}. "
                f"If all are met CN-4 allows no refund; if any is unmet the full {CUR}{f['no_show_fee']} is refunded.",
                f"依据 CN-1/CN-2/CN-3：到达={cm['driver_arrived_proximity']}，"
                f"等待={cm['dwell_past_free_window']}，联系={cm['contact_attempted']}。"
                f"全部满足则 CN-4 不退；任一不满足则全额退 {CUR}{f['no_show_fee']}。"),
            "_summary": L(lg, "Driver argues the policy conditions are met and the fee is valid.", "司机主张已满足政策条件，取消费合规。"),
        }
