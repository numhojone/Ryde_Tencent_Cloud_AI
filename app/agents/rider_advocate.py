"""Rider advocate agent."""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents import analysis
from app.i18n import L, CUR
from app.models import AdvocateCase


class RiderAdvocate(BaseAgent):
    role = "advocate"
    name = "rider_advocate"
    parse_schema = AdvocateCase

    def system_prompt(self) -> str:
        return (
            "You are the RIDER ADVOCATE AGENT of the RydeResolve ride-hailing dispute platform. You represent the rider.\n\n"
            "Duties:\n"
            "1. Call the tools to gather evidence (trip data, GPS, chat, app events, rider/driver profiles, policy, traffic reference).\n"
            "2. Build one case with fields: claim (one-sentence position), requested_outcome, requested_amount, "
            "policy_clauses_referenced, evidence_cited (specific data points), reasoning (your argument).\n\n"
            "Hard rule: never fabricate evidence; cite only data the tools actually returned. You lean towards the rider, "
            "but you stay honest: when the evidence goes against the rider, say so and adjust the request accordingly.\n\n"
            "When the evidence is gathered, output strict JSON (no code fences):\n"
            '{"agent":"rider_advocate","side":"rider","claim":"...","requested_outcome":"...",'
            '"requested_amount":0.0,"policy_clauses_referenced":[],"evidence_cited":[],"reasoning":"..."}'
        )

    def build_user_message(self, context: dict) -> str:
        return (
            "Dispute ticket:\n" + json.dumps(context["ticket"], ensure_ascii=False, indent=2) +
            "\n\nGather evidence and build the case on the rider's behalf. Remember: cite only real data returned by the tools."
        )

    def build_playbook(self, context: dict) -> list[dict]:
        lg = self.lang
        t = context["ticket"]
        trip_id = t["trip_id"]
        dtype = t["dispute_type"]
        steps = [
            {"_thought": L(lg, "First fetch the basic trip data to confirm fare and distance.", "先调取行程基础数据，确认费用与里程。"), "name": "get_trip_data", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch the GPS trace to check the route actually driven.", "调取 GPS 轨迹，核对实际行驶路径。"), "name": "get_gps_telemetry", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch the chat log to see what was said between the two sides.", "调取聊天记录，了解双方沟通。"), "name": "get_chat_logs", "args": {"trip_id": trip_id}},
            {"_thought": L(lg, "Fetch app events to rebuild the key timeline.", "调取 App 系统事件，还原关键时间线。"), "name": "get_app_events", "args": {"trip_id": trip_id}},
        ]
        if dtype == "route_deviation":
            steps.append({"_thought": L(lg, "Fetch the third-party traffic reference to see whether the detour was due to congestion.", "调取第三方交通参考，判断绕行是否因拥堵。"), "name": "get_traffic_reference", "args": {"trip_id": trip_id}})
        steps += [
            {"_thought": L(lg, "Fetch the rider profile to support the rider's credibility.", "调取乘客画像，佐证乘客可信度。"), "name": "get_rider_profile", "args": {"rider_id": t["rider_id"]}},
            {"_thought": L(lg, "Fetch the driver profile to look for dispute / fraud history.", "调取司机画像，查看是否有争议/欺诈记录。"), "name": "get_driver_profile", "args": {"driver_id": t["driver_id"]}},
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
        full_overcharge = round(f["fare_charged"] - f["optimal_fare"], 2)
        evidence = [
            L(lg, f"Actual distance {f['actual_km']} km vs optimal {f['optimal_km']} km: {f['deviation_pct']}% deviation, above the {f['tolerance_pct']}% tolerance (RD-1)",
                  f"实际里程 {f['actual_km']}km vs 最优 {f['optimal_km']}km，偏差 {f['deviation_pct']}%，超出 {f['tolerance_pct']}% 容忍阈值"),
            L(lg, f"Fare charged {CUR}{f['fare_charged']}; on the optimal route it would be {CUR}{f['optimal_fare']}, i.e. about {CUR}{full_overcharge} extra",
                  f"实收车费 {CUR}{f['fare_charged']}，按最优里程应收 {CUR}{f['optimal_fare']}，多收约 {CUR}{full_overcharge}"),
            L(lg, f"Traffic reference: {f['traffic_note']}", f"交通参考：{f['traffic_note']}"),
        ]
        rp = g.get("get_rider_profile", {})
        if rp:
            flags = rp.get('fraud_flags') or L(lg, "none", "无")
            evidence.append(L(lg,
                f"Rider account age {rp.get('account_age_days')} days, {rp.get('total_trips')} trips, rating {rp.get('avg_rating')}, fraud flags: {flags}",
                f"乘客账龄 {rp.get('account_age_days')} 天、共 {rp.get('total_trips')} 单、评分 {rp.get('avg_rating')}、欺诈标记 {flags}"))
        return {
            "agent": "rider_advocate", "side": "rider",
            "claim": L(lg, "The driver's detour overcharged the rider; the fare above the tolerance should be refunded.",
                           "司机绕路导致多收费，应退还超出容忍阈值部分的费用。"),
            "requested_outcome": "full_refund_of_overcharge",
            "requested_amount": full_overcharge,
            "policy_clauses_referenced": ["RD-1", "RD-2", "RD-3"],
            "evidence_cited": evidence,
            "reasoning": L(lg,
                f"Under RD-1/RD-2 the {f['deviation_pct']}% deviation exceeds the {f['tolerance_pct']}% threshold, so the excess "
                f"{f['overcharged_km']} km should be refunded at {CUR}{f['per_km_rate']}/km. "
                f"The traffic reference shows the detour did not save time ({f['traffic_note']}), so the RD-3 exemption does not apply. "
                f"The rider therefore requests the overcharge back: {CUR}{full_overcharge}.",
                f"依据政策 RD-1/RD-2，偏差 {f['deviation_pct']}% 已超 {f['tolerance_pct']}% 阈值，"
                f"超出部分 {f['overcharged_km']}km 应按 {CUR}{f['per_km_rate']}/km 退还。"
                f"交通参考显示绕行未节省时间（{f['traffic_note']}），不适用 RD-3 豁免。"
                f"故请求退还多收费用 {CUR}{full_overcharge}。"),
            "_summary": L(lg, "Evidence shows the detour exceeded the threshold and was not justified by congestion; requesting the overcharge back.",
                              "证据表明绕路超阈值且未被拥堵合理化，请求退还多收费用。"),
        }

    def _no_show_case(self, t: dict, g: dict) -> dict:
        lg = self.lang
        f = analysis.no_show_facts(
            g.get("get_trip_data", {}), g.get("get_gps_telemetry", {}),
            g.get("get_app_events", {}), g.get("get_chat_logs", {}),
            g.get("get_policy", {}),
        )
        fee = f["no_show_fee"]
        # Rider's view: stress anything that weakens "the driver arrived"
        evidence = [L(lg, f"The rider was charged a cancellation fee of {CUR}{fee}", f"乘客被收取取消费 {CUR}{fee}")]
        if not f["driver_arrived"]:
            evidence.append(L(lg,
                f"GPS shows the driver never stopped within {f['pickup_proximity_m']} m of the pickup point (nearby points: {f['near_points']})",
                f"GPS 显示司机未在上车点 {f['pickup_proximity_m']} 米范围内停车（附近点数 {f['near_points']}）"))
        if f["contact_attempts"] == 0:
            evidence.append(L(lg, "No driver contact attempt (call / message) was recorded", "未记录到任何司机联系尝试（电话/消息）"))
        if f["dwell_min"] < f["free_wait_min"]:
            evidence.append(L(lg, f"Dwell time {f['dwell_min']} min, short of the {f['free_wait_min']} min free wait",
                                  f"停留 {f['dwell_min']} 分钟，未满免费等待 {f['free_wait_min']} 分钟"))
        if f["all_conditions_met"]:
            evidence.append(L(lg, "(Note: system data shows the driver arrived and waited, but the rider did not see the car; asking for verification)",
                                  "（需说明：系统数据虽显示司机到达并等待，但乘客现场未见车辆，仍请求核实）"))
        rp = g.get("get_rider_profile", {})
        if rp and not rp.get("fraud_flags"):
            evidence.append(L(lg, f"Rider has no fraud flags, rating {rp.get('avg_rating')}", f"乘客无欺诈标记，评分 {rp.get('avg_rating')}"))
        return {
            "agent": "rider_advocate", "side": "rider",
            "claim": L(lg, "The driver did not arrive / did not wait as required, so the cancellation fee should not apply; full refund requested.",
                           "乘客主张司机未到达/未按规定等待，取消费不应收取，请求全额退还。"),
            "requested_outcome": "full_refund_of_cancellation_fee",
            "requested_amount": fee,
            "policy_clauses_referenced": ["CN-1", "CN-3", "CN-4"],
            "evidence_cited": evidence,
            "reasoning": L(lg,
                "Under CN-1/CN-3 the driver must arrive and contact the rider before a fee can be charged. "
                f"Contact attempts: {f['contact_attempts']}; stopped points near pickup: {f['near_points']}. "
                "If any condition is unmet, CN-4 requires a full refund.",
                "依据政策 CN-1/CN-3，司机需到达并联系乘客方可收费。"
                f"联系尝试 {f['contact_attempts']} 次，附近停车点 {f['near_points']} 个。"
                "若任一条件不满足，按 CN-4 应全额退费。"),
            "_summary": L(lg, "Rider requests a refund of the cancellation fee, checked against the policy conditions.",
                              "乘客请求退还取消费，依据政策条件核验。"),
        }
