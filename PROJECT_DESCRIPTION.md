# RydeResolve

> **Title**: RydeResolve
>
> **Subtitle**: Policy-grounded multi-agent dispute resolution with an evidence safety net
>
> **Blurb (8 words)**: *Autonomous dispute resolution where every ruling is audited.*

> **Live demo**: https://a530bc9f1a32e974f.sg2.agentos-app.run (update by republishing the new folder)

---

## 1. Project Overview

**Target scenario.** Riders and drivers on a ride-hailing platform like Ryde file disputes after a trip. RydeResolve handles the four rulable categories in the Ryde Dispute Resolution Policy v2.1 (**route deviation, no-show charge, fare dispute, property damage**) and routes the fifth, **safety incidents**, to humans as the policy requires. Today these go to human agents who pull GPS, chat, app events and policy pages from separate tools; the challenge brief puts resolution at typically 24 to 72 hours.

**Users.** Platform support teams first; riders and drivers benefit from faster and more consistent outcomes.

**Value proposition.** The rider writes a complaint in their own words. An intake agent picks the dispute type, two advocate agents build each side's case from the trip evidence, and a judge re-checks the evidence itself and rules by numbered policy clause. The policy's own thresholds (monetary tiers, 80% / 95% confidence, 2 km route limit, repair claims) are then applied in code, and a deterministic safety net blocks automatic action when the evidence is thin.

## 2. Real-World Scenario Insights

Disputes are high volume and small per ticket, so manual triage is slow and inconsistent. The hard part is not a faster chatbot: the system must (a) retrieve evidence, (b) apply the written policy by clause, (c) commit to a number, and (d) know when **not** to act automatically. (a) to (c) suit a language model; (d) is the Ryde policy's own design (section 6 thresholds, section 5 safety rule) and we enforce it in code, independent of the model's self-reported confidence.

## 3. Solution Design

```
Complaint -> Intake -> Advocates (parallel) -> Judge -> Policy thresholds (6) -> Safety net -> Ruling | Human review
                 \-> safety indicators (5.2) -> Safety case file -> Human review (no AI ruling)
```

- **Intake agent**: five types; any safety indicator in the text forces the safety path regardless of the type the filer chose (5.2). Works in English, Singlish, Malay, Tamil and Chinese.
- **Advocates** (rider, driver) run in parallel and cite only tool data.
- **Judge** re-queries 11 read-only tools, applies clauses by number (1.2 to 1.4, 2.1 to 2.4, 3.2 to 3.4, 4.2 to 4.4), searches precedents (section 7) and calibrates confidence from the four factors in policy 6.3.
- **Policy thresholds** (`app/thresholds.py`): fare under S$10 AI final; S$10 to S$50 needs 80%; over S$50 human; route deviation over 2 km needs human approval; repair claims human; a party fraud flag raises the bar to 95%.
- **Safety net**: Rule A (fewer than 3 distinct evidence points) and a per-dispute-type Rule B (required sources too thin). It forces `escalated` and preserves the model's verdict in `model_assessment`.
- **Safety incidents**: the AI gathers evidence, summarises the rider's account and suggests interim measures (5.3). It does not rule, assign fault or recommend a resolution (5.2).
- Interface and agent output in English and Chinese; rulings, clause numbers and amounts never change with language. An LLM backend (OpenAI-compatible) and a deterministic backend share the same event flow.

### Worked examples (offline, deterministic backend)

| Case | Source | Result |
|---|---|---|
| DISP-001 route deviation, 4.3 km | official sample | partial S$3.44 (4.3 km x S$0.80): traffic justified the reroute (1.4) but the driver did not inform the rider (1.2). Over 2 km, so human approval required |
| DISP-002 no-show | official sample | rejected: arrived early, waited, 4 messages and a call; S$5 fee stands (2.2) |
| DISP-003 fare dispute | official sample | upheld S$4.50: surge 1.0x to 1.5x, rider not notified (3.3) |
| DISP-004 property damage | synthetic | upheld S$35: photo taken over 24 h after the trip and not linked to it (4.2, 4.4) |
| DISP-005 safety incident | synthetic | escalated: case file prepared, no AI ruling (5.2) |
| DISP-006 thin evidence | synthetic | model-side answer overridden by the safety net: 2 GPS points, no chat; escalated |

## 4. Business Value

| Dimension | Today (manual) | RydeResolve |
|---|---|---|
| Time to ruling | 24 to 72 hours (challenge brief) | seconds in our runs; we have not benchmarked at scale |
| Audit trail | scattered across tools | every tool call and agent step streamed as an event |
| Policy traceability | in the agent's head | rulings cite clause numbers and a policy path |
| Risky cases | judged case by case | code-enforced thresholds; thin evidence and safety cases go to humans |
| Model confidence vs system check | not separated | model verdict preserved, safety net decides independently |

### Limits we state upfront

- Official sample datasets and a few synthetic cases only; no production data, no measured dispute volume, so we claim no cost-saving figure.
- The real-LLM path has not been re-run since the Policy v2.1 rebuild; all numbers above are from the deterministic backend. LLM output can vary between runs, and the section 6 thresholds are enforced in code for exactly that reason.
- In the deterministic backend the advocates and judge share analysis functions, so the judge's re-check is independent in the data it fetches, not the logic. On the LLM path the judge's reasoning is the model's own and is cross-checked against the policy computation.
- The official route sample recommends a partial refund although 6.1 sends deviations over 2 km to a human; we return the recommendation flagged as needing human approval.
- Confidence weighting (40/30/15/15) and the 100 m pickup radius are our own definitions.
- Fixture-based: no live GPS, payments or refund execution.
