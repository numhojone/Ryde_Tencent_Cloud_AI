"""Run disputes in real-LLM mode and print the full agent reasoning and ruling.

Usage:
    PYTHONPATH=. python3 run_real.py DISP-001
    PYTHONPATH=. python3 run_real.py DISP-001 DISP-002 DISP-003

Structured transcripts are also saved to transcripts/<ID>.json for review (git-ignored).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter

from app.orchestrator import resolve

W = 78


def hr(ch="="):
    print(ch * W)


async def collect(did: str):
    events = []
    t0 = time.time()
    async for ev in resolve(did):
        events.append(ev)
    return events, time.time() - t0


def show(did: str, events: list[dict], elapsed: float) -> None:
    hr()
    print(f"  {did}   ·   {elapsed:.1f}s")
    hr()

    dtype = next((e["ticket"]["dispute_type"] for e in events if e["type"] == "phase" and e.get("phase") == "intake"), "?")
    print(f"争议类型: {dtype}")
    mode = next((e.get("mode") for e in events if e["type"] == "agent_start"), "?")
    print(f"后端模式: {mode}")

    # ---- 按 agent 分组展示推理 + 工具调用 ----
    order, seen = [], set()
    for e in events:
        if e.get("role") and e["role"] not in seen:
            seen.add(e["role"])
            order.append(e["role"])

    for role in order:
        label = {"rider_advocate": "乘客辩护智能体", "driver_advocate": "司机辩护智能体",
                 "judge": "法官智能体", "safety_net": "安全网校验（确定性规则）"}.get(role, role)
        print(f"\n【{label}】 ({role})")

        # 模型自己产生的 thinking
        thinks = [e["content"] for e in events if e["type"] == "thinking" and e.get("role") == role and e.get("content")]
        for i, t in enumerate(thinks, 1):
            print(f"  ── 思考 {i}: {t.strip()[:400]}")

        # 模型自己发起的工具调用
        calls = [e for e in events if e["type"] == "tool_call" and e.get("role") == role]
        print(f"  ── 工具调用（模型自主发起，共 {len(calls)} 次）: {[c['tool'] for c in calls]}")

        warns = [e["content"] for e in events if e["type"] == "warning" and e.get("role") == role]
        for w in warns:
            print(f"  !! 警告: {w[:300]}")

    # ---- 双方案件（模型生成）----
    cs = next((e for e in events if e["type"] == "phase" and e.get("phase") == "cases_submitted"), None)
    if cs:
        print("\n" + "-" * W)
        for side, key in (("乘客方", "rider_case"), ("司机方", "driver_case")):
            c = cs.get(key)
            print(f"\n【{side}案件 — 模型生成】")
            if not c:
                print("   (空)")
                continue
            print(f"  主张 claim        : {c.get('claim')}")
            print(f"  诉求 outcome      : {c.get('requested_outcome')}  金额 {c.get('requested_amount')}")
            print(f"  引用政策 clauses   : {c.get('policy_clauses_referenced')}")
            print(f"  证据 evidence      :")
            for ev in c.get("evidence_cited", []):
                print(f"      · {ev}")
            print(f"  推理 reasoning     :\n      {c.get('reasoning')}")

    # ---- 裁决 ----
    r = next((e["ruling"] for e in events if e["type"] == "ruling"), None)
    print("\n" + "-" * W)
    if not r:
        print("【裁决】 未产出（见下方错误）")
    else:
        ma = r.get("model_assessment") or {}
        sn = r.get("safety_net") or {}
        print("【① 模型独立裁决 — 法官智能体生成（BEFORE 安全网）】")
        print(f"  裁决 ruling        : {ma.get('ruling')}")
        print(f"  退款 refund        : {ma.get('refund_amount')}")
        print(f"  置信度 confidence  : {ma.get('confidence_score')}")
        print(f"  升级人工 escalate  : {ma.get('escalation_required')}")
        print(f"  证据 evidence      :")
        for ev in ma.get("evidence_cited", []):
            print(f"      · {ev}")
        print(f"  推理 reasoning     :\n      {ma.get('reasoning')}")

        print("\n【② 安全网校验 — 确定性规则】")
        chk = sn.get("checks") or {}
        print(f"  独立证据点数       : {chk.get('distinct_evidence_points')} "
              f"(下限 {chk.get('min_evidence_points')})")
        for label, info in (chk.get("evidence_sources") or {}).items():
            flag = "近空 ✗" if info.get("near_empty") else "充足 ✓"
            print(f"  证据源 {label:14s}: {info.get('count')} 条 "
                  f"(下限 {info.get('threshold')}) → {flag}")
        print(f"  是否触发覆盖       : {sn.get('triggered')}")
        for reason in sn.get("reasons", []):
            print(f"      ✗ {reason}")

        print("\n【③ 最终裁决 — AFTER 安全网】")
        print(f"  裁决 ruling        : {r.get('ruling')}")
        print(f"  退款 refund        : {r.get('refund_amount')}")
        print(f"  置信度 confidence  : {r.get('confidence_score')}  (模型的原始置信度，保留供对照)")
        print(f"  升级人工 escalate  : {r.get('escalation_required')}")
        print(f"  结论               : {'已被安全网覆盖 → 升级人工' if sn.get('triggered') else '维持模型裁决'}")
        print(f"  推理 reasoning     :\n      {r.get('reasoning')}")
        if r.get("escalation_summary"):
            print(f"  升级摘要           :\n      {r.get('escalation_summary')}")

    errs = [e for e in events if e["type"] == "error"]
    if errs:
        for e in errs:
            print(f"\n!! 错误: {e['message'][:500]}")

    counts = Counter(e["type"] for e in events)
    print(f"\n  事件统计: {dict(counts)}")


async def main(ids: list[str]) -> None:
    os.makedirs("transcripts", exist_ok=True)
    for did in ids:
        events, elapsed = await collect(did)
        show(did, events, elapsed)
        with open(f"transcripts/{did}.json", "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        print(f"\n  transcript 已保存: transcripts/{did}.json\n")


if __name__ == "__main__":
    ids = sys.argv[1:] or ["DISP-001", "DISP-002", "DISP-003"]
    asyncio.run(main(ids))
