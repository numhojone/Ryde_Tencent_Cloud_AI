# RydeResolve

> **Title**: RydeResolve
>
> **Subtitle**: A multi-agent dispute resolution system with a deterministic evidence-sufficiency safety net
>
> **Blurb (8 words)**: *Autonomous dispute resolution where every ruling is evidence-audited.*

> **Live demo**: https://a530bc9f1a32e974f.sg2.agentos-app.run
> Type a complaint in your own words (English, Singlish, Malay, Tamil or Chinese) and the system works out the dispute type itself. An EN / 中文 toggle switches the interface and the language of the agents' output. The dropdown at the top right replays four preset disputes, including the official Ryde sample.

---

## 1. Project Overview

**Target scenario.** Riders and drivers on a ride-hailing platform like Ryde file disputes after a trip ends. We built two dispute types: **route deviation** (the rider says the driver took a longer route and overcharged) and **no-show charge** (the rider says the driver never arrived but a cancellation fee was applied). Today these go to human agents, who pull GPS logs, chat history, app events and policy pages from separate tools. The challenge brief puts resolution time at typically 24 to 72 hours per dispute.

**Users.** Platform support teams who staff these queues. Riders and drivers benefit second, from faster and more consistent outcomes.

**Value proposition.** The rider writes a complaint in their own words. An intake agent classifies it, two advocate agents build each side's case from the trip evidence, and a judge agent re-checks the evidence itself and issues a structured ruling in under 30 seconds. A deterministic safety net then checks whether the evidence behind the ruling is thick enough to act on. If it isn't, the case goes to a human instead of an automatic refund, however confident the model claims to be.

---

## 2. Real-World Scenario Insights

**Where the pain point comes from.** Disputes like these are high in volume and small per ticket, so human triage is slow and hard to keep consistent. Two similar disputes can end differently depending on which agent picks them up. The 24 to 72 hour turnaround comes from the challenge brief.

**Who it affects.**
- **Riders** wait a day or more to learn whether a small charge will be refunded.
- **Drivers** see legitimate cancellation fees challenged, and outcomes vary from case to case.
- **Support teams** touch every case, including ones where the policy outcome is clear.

**The core problem.** The goal is not a faster chatbot. The system has to: **(a)** retrieve the evidence (GPS, chat, app events, traffic reference), **(b)** apply the written policy rules by clause, **(c)** commit to a number, and **(d)** refuse to auto-refund when the evidence is too thin to support the conclusion. Steps (a) to (c) suit a language model. Step (d) is a code rule that does not depend on the model's self-reported confidence.

---

## 3. Comprehensive Solution Design

### 3.1 Business flow

```
Complaint (free text) -> Intake -> Advocates -> Judge -> Safety net -> Auto-ruling (upheld / partial / rejected)
                                                                   \-> Escalation queue (human review)
```

Every ruling carries the spec fields (`dispute_id`, `ruling`, `refund_amount`, `confidence_score`, `reasoning`, `evidence_cited`, `escalation_required`) plus two system fields: a `safety_net` audit block, and a `model_assessment` block that preserves the model's own judgment. A human reviewer can see what the model thought, what the system observed, and why the system overrode it.

### 3.2 Technical design

All agents share one tool layer (8 tools) and one runtime (`BaseAgent.run`). FastAPI streams every step over SSE, so tool calls and agent reasoning are visible as they happen.

1. **Intake agent** reads the rider's free-text complaint, picks the dispute type and reports a classification confidence. It classifies the complaint only. It does not decide the outcome.
2. **Rider Advocate** and **Driver Advocate** run in parallel (`asyncio.gather`). Each is prompted to cite only data returned by tools, and each produces a symmetric case (claim, evidence, cited policy, requested refund).
3. **Judge** does not rely on the advocates' summaries. It re-queries the same 8 tools (`get_trip_data`, `get_gps_telemetry`, `get_chat_logs`, `get_app_events`, `get_rider_profile`, `get_driver_profile`, `get_policy`, `get_traffic_reference`) and walks the policy clauses (CN-1 to CN-4 for no-shows, RD-1 to RD-3 for route deviation).
4. **Safety net** is a deterministic module (`app/safety_net.py`) that runs after the judge. It uses fixed thresholds and ignores the model's confidence score:
   - **Rule A**: the judge's `evidence_cited` list has fewer than 3 distinct items after deduplication.
   - **Rule B**: a behavioral evidence source is empty or near-empty (GPS under 3 points, chat under 2 messages, app events under 2).

   If either rule fires, the ruling becomes `escalated`, the refund is withheld, and the model's original verdict is kept in `model_assessment`. Rule B reads the data tools directly. Rule A counts what the judge cited, so it checks how well the ruling is supported, not whether the model is right.

The interface and the agents' output are available in English and Chinese; only human-readable text changes, never rulings, clause IDs or numbers. The backend is switchable. The demo path calls a real LLM through an OpenAI-compatible endpoint. A scripted deterministic fallback follows the same event flow and needs no API key, so the demo still runs if the LLM quota is exhausted.

### 3.3 How the design works in practice: DISP-003

`TRIP-1003` has only **2 GPS points**, **0 chat messages**, and an app event placing the driver about 420 m from the pickup, well outside the 100 m arrival threshold in clause CN-1. On the real LLM path (Gemini 3.5 Flash Lite), the judge read the evidence and returned `upheld / refund S$25 / confidence 1.0`, a full automatic refund.

That reading is defensible. The app event states the 420 m distance directly, and no contact was logged. The problem is the evidence base: two GPS points and no chat is thin for a ruling that moves money with no human involved. The safety net sees two of the three behavioral sources below their minimums, forces `escalated`, and keeps the judge's `upheld / S$25 / 1.0` in `model_assessment` so the human reviewer starts from the model's reasoning. The UI shows the model's judgment and the override side by side.

> Confidence is the model's self-assessment, and it can be high on a thin evidence base. The check on whether the evidence is sufficient is code, so it behaves the same way every time.

---

## 4. Business Value

Real-LLM results below were measured on the three original synthetic cases (`DISP-001` route deviation, `DISP-002` no-show, `DISP-003` no-show with sparse evidence) on Gemini 3.5 Flash Lite via Google AI Studio, before the fixtures were relabelled to Singapore places and S$ (the relabel changes names and currency labels, not the numbers or logic). `DISP-004` is the official Ryde sample (Tiong Bahru Plaza no-show); we have run it in the deterministic fallback, where the charge stands (`rejected`, refund 0), matching the dataset's expected outcome.

| Dimension | Today (manual) | RydeResolve |
|---|---|---|
| **Time to ruling** | 24 to 72 hours (per the challenge brief) | **17.6 to 27.5 s end to end**, including tool calls and the safety-net check |
| **Audit trail** | Scattered across tools | **22 to 27 tool calls per case**, each streamed as an event |
| **Policy traceability** | Held in the agent's head | Rulings cite policy clauses (CN-1 to CN-4, RD-1 to RD-3) in `evidence_cited` |
| **Thin-evidence cases** | Handled case by case | On DISP-003 the safety net blocked the automatic refund and routed it to a human |
| **Model confidence vs system check** | Not separated | Model confidence is stored in `model_assessment`. The safety net decides independently whether the evidence is enough |

### Fixture results

- **DISP-001 (route deviation)**: judge `partial S$30 / 0.98`. Safety net not triggered (GPS 10, chat 5, events 3). Final `partial S$30`, 27 tool calls. The deterministic fallback reaches the same amount.
- **DISP-002 (no-show)**: judge `rejected S$0 / 1.0` (driver arrived, waited, and contacted the rider). Safety net not triggered (GPS 7, chat 3, events 8). Final `rejected S$0`, 22 tool calls. The fallback agrees.
- **DISP-003 (no-show, sparse evidence)**: judge `upheld S$25 / 1.0`. Safety net **triggered** (GPS 2 of 3, chat 0 of 2). Final `escalated`, refund withheld, original verdict preserved. The deterministic fallback also escalates this case, but through its own scripted rule.

### Limits we want to be upfront about

- All results come from 3 synthetic fixtures, one official Ryde sample case and a few free-text tests, not from production Ryde data. The synthetic amounts are illustrative. We have not measured a real dispute volume or a real borderline-case rate, so we do not claim a cost saving figure.
- LLM output can vary between runs. The deterministic safety net does not remove that variance. It limits the damage when the evidence is thin.
- In the deterministic fallback, the judge and the advocates use the same analysis functions, so its re-check is independent in the data it fetches, not in the logic it applies. On the LLM path the judge's reasoning is the model's own.
- The live demo runs on a free-tier LLM quota. If it runs out, the backend switcher lets a user continue on the scripted backend, which has the same flow but scripted reasoning text.
- Non-English complaints (Singlish, Malay, Tamil, Chinese) are handled by the LLM's own language understanding on the real path. In the scripted fallback, intake uses keyword rules, which we tuned on a handful of example complaints and have not validated at scale.
