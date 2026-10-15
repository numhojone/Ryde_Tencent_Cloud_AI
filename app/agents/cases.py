"""Shared pieces for the deterministic backend: tool playbooks, fact computation, advocate case builders."""
from __future__ import annotations

from app.agents import analysis as A
from app.i18n import L, CUR

RULABLE = ("route_deviation", "no_show_charge", "fare_dispute", "property_damage")

_T = {  # tool -> (en thought, zh thought)
    "get_trip_data": ("Fetch the trip record (times, distances, fare).", "调取行程记录（时间、里程、费用）。"),
    "get_gps_telemetry": ("Fetch the GPS trace.", "调取 GPS 轨迹。"),
    "get_chat_logs": ("Fetch the in-trip messages and calls.", "调取行程内消息与通话记录。"),
    "get_app_events": ("Fetch app events (arrival, wait timer, fee).", "调取 App 事件（到达、等待计时、收费）。"),
    "get_traffic_reference": ("Fetch the traffic incidents and the recommended route.", "调取交通事件与推荐路线。"),
    "get_fare_breakdown": ("Fetch the fare breakdown and surge log.", "调取费用明细与动态定价日志。"),
    "get_damage_evidence": ("Fetch the damage claim and photo metadata.", "调取损坏索赔与照片元数据。"),
    "get_rider_profile": ("Check the rider's history and flags.", "核验乘客历史与标记。"),
    "get_driver_profile": ("Check the driver's history and flags.", "核验司机历史与标记。"),
    "get_policy": ("Fetch the applicable policy sections and thresholds.", "调取适用的政策条款与阈值。"),
    "search_precedents": ("Search similar precedents.", "检索相似先例。"),
}
_TOOLS = {
    "route_deviation": ["get_trip_data", "get_gps_telemetry", "get_chat_logs", "get_app_events", "get_traffic_reference", "get_fare_breakdown"],
    "no_show_charge": ["get_trip_data", "get_gps_telemetry", "get_chat_logs", "get_app_events"],
    "fare_dispute": ["get_trip_data", "get_fare_breakdown", "get_chat_logs", "get_gps_telemetry"],
    "property_damage": ["get_trip_data", "get_damage_evidence", "get_chat_logs", "get_app_events"],
}
_TAGS = {"route_deviation": ["traffic_justified", "rider_not_informed"], "no_show_charge": ["driver_arrived", "contact_attempted"],
         "fare_dispute": ["surge", "rider_not_notified"], "property_damage": ["photo", "cleaning"]}


def playbook(lg: str, ticket: dict, with_precedents: bool = True) -> list[dict]:
    tid, dtype = ticket["trip_id"], ticket["dispute_type"]
    steps = []
    for n in _TOOLS.get(dtype, _TOOLS["no_show_charge"]):
        steps.append({"_thought": L(lg, *_T[n]), "name": n, "args": {"trip_id": tid}})
    steps.append({"_thought": L(lg, *_T["get_rider_profile"]), "name": "get_rider_profile", "args": {"rider_id": ticket["rider_id"]}})
    steps.append({"_thought": L(lg, *_T["get_driver_profile"]), "name": "get_driver_profile", "args": {"driver_id": ticket["driver_id"]}})
    steps.append({"_thought": L(lg, *_T["get_policy"]), "name": "get_policy", "args": {"dispute_type": dtype}})
    if with_precedents:
        steps.append({"_thought": L(lg, *_T["search_precedents"]), "name": "search_precedents",
                      "args": {"dispute_type": dtype, "tags": _TAGS.get(dtype, [])}})
    return steps


def compute_facts(dtype: str, g: dict) -> dict:
    trip = g.get("get_trip_data", {})
    if dtype == "route_deviation":
        return A.route_deviation_facts(trip, g.get("get_fare_breakdown", {}), g.get("get_traffic_reference", {}), g.get("get_chat_logs", {}), g.get("get_gps_telemetry", {}))
    if dtype == "no_show_charge":
        return A.no_show_facts(trip, g.get("get_gps_telemetry", {}), g.get("get_app_events", {}), g.get("get_chat_logs", {}))
    if dtype == "fare_dispute":
        return A.fare_facts(trip, g.get("get_fare_breakdown", {}))
    if dtype == "property_damage":
        return A.damage_facts(trip, g.get("get_damage_evidence", {}))
    return {}


def clauses_for(dtype: str, f: dict) -> list[str]:
    return {"route_deviation": ["1.2", "1.3", "1.4"], "no_show_charge": ["2.1", "2.3", "2.4"],
            "fare_dispute": ["3.2", "3.3", "3.4"], "property_damage": ["4.2", "4.3", "4.4"]}.get(dtype, [])


def evidence_lines(dtype: str, f: dict, lg: str) -> list[str]:
    """Neutral evidence lines (each cites a clause); both advocates and the judge draw from these."""
    if dtype == "route_deviation":
        return [
            L(lg, f"Distance: estimated {f['estimated_km']} km, actual {f['actual_km']} km, deviation {f['deviation_km']} km (tolerance 1.0 km, clause 1.3)",
                  f"里程：预估 {f['estimated_km']} 公里，实际 {f['actual_km']} 公里，偏差 {f['deviation_km']} 公里（容忍 1.0 公里，条款 1.3）"),
            L(lg, f"Excess distance fare: {f['deviation_km']} km x {CUR}{f['distance_rate']}/km = {CUR}{f['excess_distance_fare']} (clause 1.3)",
                  f"超出里程费：{f['deviation_km']} 公里 x {CUR}{f['distance_rate']}/公里 = {CUR}{f['excess_distance_fare']}（条款 1.3）"),
            L(lg, f"Traffic incidents overlapping the recommended route at trip start: {', '.join(f['matched_incidents']) or 'none'} (clause 1.4)",
                  f"行程开始时与推荐路线重叠的交通事件：{', '.join(f['matched_incidents']) or '无'}（条款 1.4）"),
            L(lg, f"Driver told the rider about the reroute before deviating: {'yes' if f['rider_informed'] else 'no'} (clause 1.2)",
                  f"司机在绕行前是否告知乘客：{'是' if f['rider_informed'] else '否'}（条款 1.2）"),
        ]
    if dtype == "no_show_charge":
        return [
            L(lg, f"Driver arrived within the free-wait window: {'yes' if f['arrived_in_time'] else 'no'}; stopped GPS points near pickup: {f['stopped_points']} (clause 2.4)",
                  f"司机是否在免费等待期内到达：{'是' if f['arrived_in_time'] else '否'}；上车点附近静止 GPS 点：{f['stopped_points']} 个（条款 2.4）"),
            L(lg, f"Waited the full 5-minute free period before cancelling: {'yes' if f['waited_free_period'] else 'no'} (clause 2.1)",
                  f"取消前是否等满 5 分钟免费等待：{'是' if f['waited_free_period'] else '否'}（条款 2.1）"),
            L(lg, f"Driver contact attempts: {f['driver_messages']} message(s) and {f['driver_calls']} call(s); both required (clause 2.3)",
                  f"司机联系尝试：{f['driver_messages']} 条消息、{f['driver_calls']} 次通话；两者都需要（条款 2.3）"),
            L(lg, f"Cancellation fee charged: {CUR}{f['no_show_fee']} (clause 2.2)", f"已收取消费：{CUR}{f['no_show_fee']}（条款 2.2）"),
        ]
    if dtype == "fare_dispute":
        return [
            L(lg, f"Upfront quote {CUR}{f['upfront_quote']}, final fare {CUR}{f['actual_fare']}, difference {CUR}{f['difference']} (clause 3.2)",
                  f"预付报价 {CUR}{f['upfront_quote']}，最终车费 {CUR}{f['actual_fare']}，差额 {CUR}{f['difference']}（条款 3.2）"),
            L(lg, f"Surge multiplier moved from {f['surge_quote']}x to {f['surge_trip_start']}x between quote and pickup (clause 3.3)",
                  f"动态系数在报价与上车之间由 {f['surge_quote']}x 升至 {f['surge_trip_start']}x（条款 3.3）"),
            L(lg, f"Rider notified of the surge increase: {'yes' if f['rider_notified'] else 'no'} (clause 3.3)",
                  f"是否通知乘客动态加价：{'是' if f['rider_notified'] else '否'}（条款 3.3）"),
            L(lg, f"Whole difference is explained by the surge amount ({CUR}{f['surge_differential']}): {'yes' if f['surge_only'] else 'no'} (clause 3.4)",
                  f"差额是否完全由动态加价构成（{CUR}{f['surge_differential']}）：{'是' if f['surge_only'] else '否'}（条款 3.4）"),
        ]
    if dtype == "property_damage":
        pc = f["photo_checks"][0] if f["photo_checks"] else {}
        return [
            L(lg, f"Claim: {f['claim_type']}, amount {CUR}{f['claimed_amount']} (cleaning cap {CUR}50, clause 4.3)", f"索赔类型：{f['claim_type']}，金额 {CUR}{f['claimed_amount']}（清洁上限 {CUR}50，条款 4.3）"),
            L(lg, f"Photos supplied: {len(f['photo_checks'])}; verifiable (within 24 h, in-app camera, linked to trip): {f['verifiable_photos']} (clause 4.2)",
                  f"提供照片 {len(f['photo_checks'])} 张；可核验（24 小时内、App 内拍摄、关联行程）：{f['verifiable_photos']} 张（条款 4.2）"),
            L(lg, f"First photo checks: within 24 h={pc.get('within_24h')}, in-app camera={pc.get('in_app_camera')}, linked to trip={pc.get('linked_to_trip')} (clause 4.2)",
                  f"首张照片核验：24 小时内={pc.get('within_24h')}，App 内拍摄={pc.get('in_app_camera')}，关联行程={pc.get('linked_to_trip')}（条款 4.2）"),
            L(lg, f"Claim submitted within 24 h of trip end: {'yes' if f['submitted_in_24h'] else 'no'} (clause 4.2)", f"是否在行程结束 24 小时内提交：{'是' if f['submitted_in_24h'] else '否'}（条款 4.2）"),
        ]
    return []


def advocate_case(side: str, dtype: str, f: dict, g: dict, lg: str) -> dict:
    ev = evidence_lines(dtype, f, lg)
    refund = f.get("policy_refund", 0.0)
    cl = clauses_for(dtype, f)
    rp = g.get("get_rider_profile") or {}
    dp = g.get("get_driver_profile") or {}
    rider = side == "rider"
    prof = rp if rider else dp
    if prof:
        ff = prof.get("fraud_flags")
        ev = ev + [L(lg, f"{side.capitalize()} profile: {prof.get('total_trips')} trips, rating {prof.get('avg_rating')}, fraud flags {ff or 0}",
                         f"{'乘客' if rider else '司机'}画像：{prof.get('total_trips')} 单，评分 {prof.get('avg_rating')}，欺诈标记 {ff or 0}")]
    if dtype == "route_deviation":
        if rider:
            claim = L(lg, "The trip ran well past the 1 km tolerance and the driver never told me about the reroute; the excess distance fare should be refunded.",
                          "行程明显超出 1 公里容忍范围，司机也没有告知改道；应退还超出里程费。")
            amount = f["excess_distance_fare"]
            reason = L(lg, f"Clause 1.3 refunds the excess distance fare ({CUR}{amount}) when deviation exceeds 1 km. Clause 1.2 required the driver to tell me. "
                           f"The notification is {'absent' if not f['rider_informed'] else 'present'} in the chat log"
                           + (", and I asked about the route and got a dismissive answer." if f["rider_queried_route"] else "."),
                       f"条款 1.3：偏差超过 1 公里应退超出里程费（{CUR}{amount}）。条款 1.2 要求司机告知乘客，聊天记录中{'没有' if not f['rider_informed'] else '有'}告知"
                       + ("，我询问路线时得到的回复很敷衍。" if f["rider_queried_route"] else "。"))
            outcome = "refund_of_excess_distance_fare"
        else:
            claim = L(lg, "The reroute was a safety-motivated response to a real incident on the recommended route and did not add meaningful delay; no refund is owed.",
                          "改道是对推荐路线上真实事故的安全应对，并未造成明显延误；无需退款。")
            amount = 0.0
            reason = L(lg, f"Clause 1.4 exempts deviations justified by traffic: incidents {', '.join(f['matched_incidents']) or 'none found'} overlap the recommended route. "
                           f"Trip duration stayed close to the estimate. I accept I did not message the rider in time (clause 1.2), so I accept a partial adjustment at most.",
                       f"条款 1.4 豁免因交通状况而产生的偏差：事件 {', '.join(f['matched_incidents']) or '未找到'} 与推荐路线重叠。行程时长接近预估。"
                       "我承认没有及时告知乘客（条款 1.2），最多接受部分调整。")
            outcome = "no_refund_or_partial"
    elif dtype == "no_show_charge":
        if rider:
            claim = L(lg, "I did not see the driver, so the cancellation fee should be reversed.", "我没有见到司机，取消费应予撤销。")
            amount = f["no_show_fee"]
            reason = L(lg, f"Clause 2.4 reverses the fee if the driver did not arrive within the free-wait window. Arrived in time per data: {f['arrived_in_time']}. "
                           f"Contact attempts logged: {f['driver_messages']} message(s), {f['driver_calls']} call(s).",
                       f"条款 2.4：司机未在免费等待期内到达则撤销费用。数据显示是否按时到达：{f['arrived_in_time']}。记录的联系：{f['driver_messages']} 条消息、{f['driver_calls']} 次通话。")
            outcome = "full_refund_of_cancellation_fee"
        else:
            claim = L(lg, "I arrived on time, waited the full free period, messaged and called; the fee is valid.", "我按时到达、等满免费等待期，并发送消息和致电；费用有效。")
            amount = 0.0
            reason = L(lg, f"Clauses 2.1-2.3 are met if: arrived in time={f['arrived_in_time']}, waited={f['waited_free_period']}, messaged={f['driver_messages']}, called={f['driver_calls']}.",
                       f"条款 2.1-2.3 的满足情况：按时到达={f['arrived_in_time']}，等满={f['waited_free_period']}，消息={f['driver_messages']}，通话={f['driver_calls']}。")
            outcome = "fee_stands"
    elif dtype == "fare_dispute":
        if rider:
            claim = L(lg, "The fare rose by the surge amount and I was never told; I want the difference refunded.", "车费因动态加价上涨而我从未被告知；请求退还差额。")
            amount = f["difference"]
            reason = L(lg, f"Clause 3.3: a surge increase between quote and pickup without notification is refunded. Surge {f['surge_quote']}x to {f['surge_trip_start']}x, notified={f['rider_notified']}.",
                           f"条款 3.3：报价与上车之间动态加价而未通知，应退还。动态系数 {f['surge_quote']}x 升至 {f['surge_trip_start']}x，已通知={f['rider_notified']}。")
            outcome = "refund_of_surge_difference"
        else:
            claim = L(lg, "The fare reflects the live surge multiplier in force at pickup.", "车费反映上车时生效的实时动态系数。")
            amount = 0.0
            reason = L(lg, "Surge pricing is set by the platform, not the driver. I have no record of notifying the rider, which is a platform-side obligation under clause 3.3.",
                           "动态定价由平台设定而非司机。我没有通知乘客的记录，按条款 3.3 这是平台一侧的义务。")
            outcome = "no_driver_fault"
    else:  # property_damage
        if rider:
            claim = L(lg, "The cleaning fee is not supported by verifiable evidence; please reverse it.", "清洁费没有可核验证据支持；请求撤销。")
            amount = f["fee_charged"]
            reason = L(lg, f"Clause 4.2 needs photos within 24 h from the in-app camera and linked to the trip; verifiable photos: {f['verifiable_photos']}. Clause 4.4 reverses unsupported claims.",
                           f"条款 4.2 要求 24 小时内、App 内相机拍摄且关联行程的照片；可核验照片：{f['verifiable_photos']}。条款 4.4：证据不足的索赔应撤销。")
            outcome = "reverse_cleaning_fee"
        else:
            claim = L(lg, "The vehicle needed cleaning after the trip and I reported it.", "行程后车辆需要清洁，我已上报。")
            amount = 0.0
            reason = L(lg, f"I filed a {f['claim_type']} claim of {CUR}{f['claimed_amount']}. I accept the photo evidence must meet clause 4.2; submitted within 24 h: {f['submitted_in_24h']}.",
                           f"我提交了 {f['claim_type']} 索赔 {CUR}{f['claimed_amount']}。我承认照片必须符合条款 4.2；是否 24 小时内提交：{f['submitted_in_24h']}。")
            outcome = "claim_stands"
    return {"agent": f"{side}_advocate", "side": side, "claim": claim, "requested_outcome": outcome, "requested_amount": amount,
            "policy_clauses_referenced": cl, "evidence_cited": ev, "reasoning": reason,
            "_summary": L(lg, "Case built from the tool data.", "已基于工具数据构建案件。")}
