# RydeResolve

**Autonomous dispute resolution where every ruling is policy-checked and evidence-audited.**

A multi-agent system that resolves ride-hailing disputes end to end under the **Ryde Dispute Resolution Policy v2.1**: it reads the rider's complaint in their own words, gathers evidence with tools, argues both sides, rules by numbered policy clause, applies the policy's ruling thresholds in code, and then a **deterministic safety net** refuses to act automatically when the evidence behind a ruling is too thin, whatever the model's confidence says. Safety incidents are never ruled by the AI (policy section 5).

Built for the **Tencent Cloud AI CAN DO IT Hackathon, Singapore 2026** (Ryde / AI Agent Digital Native track), developed with WorkBuddy / CodeBuddy and Claude.

---

## How it works

```
 Rider's own words + trip
          |
   [ Intake agent ]  route_deviation | no_show_charge | fare_dispute | property_damage | safety_incident
          |                                                         |
          |                                         safety indicators (any dispute type, 5.2)
   +------+------------------+                                      v
   |                         |   parallel          [ Safety case file ]  AI gathers evidence, suggests interim
 [ Rider advocate ]   [ Driver advocate ]                                measures (5.3), does NOT rule
   |                         |
   +------+------------------+
          |
     [ Judge ]   re-queries the tools, applies clauses by number, searches precedents,
          |      calibrates confidence from 4 factors (policy 6.3)
   [ Policy thresholds (section 6) ]   monetary tiers, 80% / 95% confidence, route <= 2 km, repair -> human
          |
   [ Safety net ]   deterministic evidence-sufficiency check per dispute type
          |
  Ruling JSON: upheld | partial | rejected | escalated  (+ policy_path, model_assessment, safety_net blocks)
```

**Eleven read-only tools** (they return evidence, never judgments): `get_trip_data`, `get_gps_telemetry`, `get_chat_logs`, `get_app_events`, `get_rider_profile`, `get_driver_profile`, `get_policy`, `get_traffic_reference`, `get_fare_breakdown`, `get_damage_evidence`, `search_precedents`.

### Policy v2.1 coverage

| Dispute | Clauses implemented | Ruling logic |
|---|---|---|
| Route deviation | 1.2 to 1.4 | tolerance 1 km; refund = deviation km x distance rate; traffic-justified deviation exempt; driver must inform the rider |
| No-show charge | 2.1 to 2.4 | 5 min free wait; driver must message **and** call; S$5 fee; driver no-show voids it; S$5 goodwill credit if no contact attempt |
| Fare dispute | 3.2 to 3.4 | surge increase without notification is refunded; surge-only difference refunded in full |
| Property damage | 4.2 to 4.4 | photos within 24 h, in-app camera, linked to trip; cleaning capped at S$50; unsupported claim reversed |
| Safety incident | 5.1 to 5.3 | always human review; AI prepares a case file only |

Section 6 thresholds are applied in `app/thresholds.py`: fare under S$10 AI final, S$10 to S$50 needs 80% confidence, over S$50 human; route deviation over 2 km needs human approval; repair claims always human; any party with a fraud flag raises the confidence bar to 95%. Confidence is calibrated in code from evidence completeness, policy clarity, precedent alignment and party credibility (weights 40/30/15/15, our own heuristic, not specified by the policy).

**A policy question we flagged rather than hid.** The official route-deviation sample (DISP-001, 4.3 km deviation) has a recommended ruling of *partial S$3.44*, while policy 6.1 says deviations over 2 km go to a human. We return the AI recommendation **and** mark it as requiring human approval (`escalation_required = true`, `policy_path.human_approval_only = true`). Set `STRICT_ESCALATION=true` to make such cases `escalated` instead.

### The safety net

After the judge rules, `app/safety_net.py` re-fetches the evidence sources that dispute type depends on and forces `escalated` if:

- **Rule A**: the judge cites fewer than 3 distinct evidence points.
- **Rule B**: a required source is thin (no-show: GPS < 3, chat < 2, events < 2; route: GPS < 3, chat < 2; fare: no surge log or no chat; property: no damage photo record or no chat).

Neither rule reads the model's confidence. The model's own verdict is kept in `model_assessment`.

## Quick start

Python 3.11+.

```bash
pip install -r requirements.txt
./run.sh                 # http://localhost:8000
python -m pytest -q      # offline tests (pip install pytest)
```

With no API key it runs in **deterministic mode** (scripted agents, same tools, same policy maths). To use a real model:

```bash
cp .env.example .env     # set LLM_MODE=llm and LLM_API_KEY=...
./run.sh
```

Any OpenAI-compatible endpoint works (default: Google AI Studio, Gemini; Tencent Hunyuan via `LLM_BASE_URL` / `LLM_MODEL`). **Never commit `.env`**; it is git-ignored. In LLM mode the model reasons freely, and the section 6 thresholds are still enforced in code from the tool data; the judge's output is cross-checked against the deterministic policy computation (`policy_check`).

## Using it

- Write a complaint in your own words (English, Singlish, Malay, Tamil or Chinese), pick a trip, press **Submit and rule**. You never choose the dispute type.
- **EN | 中文** toggle switches the interface and the agents' output language; rulings, clause numbers and amounts are identical in both.
- The dropdown replays six preset tickets: DISP-001 route deviation, DISP-002 no-show, DISP-003 fare dispute (all from the official Ryde datasets), plus DISP-004 property damage, DISP-005 safety incident and DISP-006 sparse evidence (synthetic).

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | mode, provider, model |
| `GET /api/disputes`, `GET /api/trips` | preset tickets, trips a complaint can be filed against |
| `GET /api/file/stream?trip_id=&complaint=&lang=en\|zh&mode=` | free-text complaint, SSE stream of every step |
| `POST /api/file` | same, synchronous |
| `GET /api/resolve/{id}/stream`, `POST /api/resolve/{id}` | replay a preset ticket |

## Data

`fixtures/` holds trips, profiles, `policies/policy_v2_1.json`, `precedents.json` and tickets. Names were removed from profiles. Ground-truth outcomes for tests live in `fixtures/expected/` and are never returned by any tool. Official Ryde datasets are used as provided (field names kept); the property-damage, safety and sparse-evidence cases are synthetic. Expected offline results: DISP-001 partial S$3.44 (human approval required), DISP-002 rejected, DISP-003 upheld S$4.50, DISP-004 upheld S$35, DISP-005 escalated, DISP-006 escalated.

## Repository layout

```
app/main.py            FastAPI + SSE
app/orchestrator.py    intake -> advocates (parallel) -> judge -> thresholds -> safety net; safety incident path
app/agents/            base loop, intake, advocates, judge, cases.py, analysis.py (deterministic policy facts)
app/thresholds.py      policy section 6 in code
app/safety_net.py      evidence-sufficiency check per dispute type
app/tools/             11 tools + OpenAI-style schemas
static/                single-page UI
fixtures/              trips, profiles, policy, precedents, tickets, expected (tests only)
tests/                 pytest suite (offline)
architecture.svg/png   diagram
PROJECT_DESCRIPTION.md submission write-up
```

## Honest limitations

- The real-LLM path has not been re-run since the Policy v2.1 rebuild (it was verified on the earlier synthetic version). Offline results above are verified; treat live-model behaviour on the new dispute types as untested until you run it with a key.
- Fixture data only: no live GPS, payment or refund execution. Rulings are decided, not executed.
- Deterministic mode uses keyword rules for intake; arbitrary phrasing relies on the real LLM.
- "At the pickup location" has no distance in the policy; we use 100 m as an operational definition. The confidence weights are our own.
- Free-tier LLM quotas can return 429; the UI offers the deterministic fallback.
