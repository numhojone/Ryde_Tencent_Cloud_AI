# RydeResolve

**Autonomous dispute resolution where every ruling is policy-checked and evidence-audited.**

A multi-agent system that resolves ride-hailing disputes end to end under the **Ryde Dispute Resolution Policy v2.1**: it reads the rider's complaint in their own words, gathers evidence with tools, argues both sides, rules by numbered policy clause, applies the policy's ruling thresholds in code, and then a **deterministic safety net** refuses to act automatically when the evidence behind a ruling is too thin, whatever the model's confidence says. Safety incidents are never ruled by the AI (policy section 5).

Built for the **Tencent Cloud AI CAN DO IT Hackathon, Singapore 2026** (Ryde / AI Agent Digital Native track), developed with WorkBuddy / CodeBuddy and Claude.

---

## Story in, structured ticket out

The rider types what happened in their own words. The system:

1. **Matches the story to one of the rider's recent trips** (`app/trip_match.py`), in code, before any agent runs. Each trip is scored on place names in the story vs its pickup / drop-off (fuzzy, case-insensitive, with local aliases such as 樟宜机场), amounts vs its quote / fare / fee fields, distance, duration and speed vs its records, dates and times, and whether the suggested category is possible for that trip (a cancelled trip cannot be a route deviation). A trip is chosen only when its score is high enough **and** clearly ahead of the next one; otherwise the rider is shown the top 3 and picks one. Nothing is ruled without a trip.
2. **Turns the story into a ticket in the same format as the sample tickets** (`dispute_id, trip_id, filed_by, rider_id, driver_id, dispute_type, description, filed_at, status, requested_resolution, requested_amount`), with `description` kept verbatim, plus `extracted_facts` (quoted / charged amount, claimed difference, fee type, pickup / drop-off, time mentions, driver and rider actions, safety indicators, language), `missing_info`, and a `claim_check` that compares the story's numbers with the trip's records.
3. Rules exactly as before, from the platform's records.

**The honest limit:** the story only selects the category and the trip. The ruling comes from the platform's records for that trip (GPS, chat, fare logs, app events), never from the story. `claim_check` is shown to the reader and is not passed to the agents that rule. Extracted facts are only what the story states; anything it does not say is `null`. In LLM mode the model's facts are checked against the story (numbers must appear in it) and replaced by the rule extractor if malformed. In deterministic mode the extractor is regex / keyword based: it knows the place names in the trip fixtures and common phrasings in English, Singlish, Malay, Tamil and Chinese, and will miss wording outside those.

## Three-pane demo, with rider login

`/` starts with a demo login ("Ryde Support"): pick a demo rider (name and rider ID) or **Support agent**. There is no password; this is a demo login, not real authentication. The server sets a signed session cookie (HMAC with `SECRET_KEY` from `.env`, HttpOnly, SameSite=Lax) and reads the rider ID only from it, never from the browser or the story. Every data endpoint answers 401 without a session; the support-console endpoints answer 403 to riders. The original single chat is still at `/classic` (behind the same login).

| Pane | What it is |
|---|---|
| **Rider** (left) | The customer's app. Stage 1: the rider says what happened and confirms which of **their own** trips it was. Stage 2: the case runs. Stage 3: one plain-language outcome card (decision, amount, one-line reason, policy section), or "passed to a Ryde support agent" with a reference and no amount promised, plus any questions from support. For the support agent this pane is a read-only view of the rider's conversation. |
| **Agent room** (middle) | The existing group chat. Idle ("Waiting for a case") until the rider confirms a trip; then trip, intake, both advocates, judge, policy thresholds and safety net run live. |
| **Support console** (right) | For the support agent only: a queue of cases handed to a person (any rider), then the summary card, evidence chips, "Ask about this case" and the decision bar. A rider sees "No cases need review" here. |

**Stage 1, finding the trip** (`app/rider_match.py`, deterministic in both modes): the intake rules pick the category (no signal at all: one clarifying question, no guess); only the signed-in rider's trips are considered; trip data decides which ones the category is possible for (no-show: cancelled with a no-show fee; fare: final fare above the quote; route: completed with a longer actual distance; damage: a cleaning or damage fee; safety: any trip); the story ranks them (places, amounts, dates, weekdays, today / yesterday, time of day, driver name). Then: no trip fits, so the rider sees their recent trips; one clear match, so "Is this the one?" with Yes / No, pick another; several close ones, so a picker with date, route, fare, status and why each might match. The case, and the agent room, start only after the rider confirms. The chosen trip is checked on the server against the session (another rider's trip: 403).

**Scoping:** every tool that returns trip data (`get_trip_data`, GPS, chat, app events, fare breakdown, damage evidence, traffic) and the rider / driver profiles only return the case's own rider's data; another rider's trip gives the same "not found" as a trip that does not exist. A rider sees only their own cases, disputes and trips; the support agent sees any case that was handed to a person.

**Test data:** each demo rider has 3 to 6 trips. The extra ones are synthetic, in `fixtures/trips_synthetic.json` (generated by `scripts/build_trips_synthetic.py`), with display names and suggested stories in `fixtures/demo_accounts.json`. Official files (DISP-001 to 003, their trips and rider profiles) are unchanged.

Demo, end to end (offline, no key needed):

1. `LLM_MODE=deterministic ./run.sh`, open http://localhost:8000, sign in as **Daniel Lim (R-7823)**. Pick **Offline demo** in the demo strip.
2. Click **No-show fee (two trips fit)**, then **Send**. Two of Daniel's cancelled trips fit, so a picker appears. Choose **Redhill MRT → Great World** (24 Sep). The agent room starts; the driver messaged but never called (2.3), so the AI refunds S$5.00 and the rider sees the outcome card. The support console stays empty.
3. **Sign out**, sign in as **Sarah Tan (R-4521)**. Click **Detour to Changi T3**, **Send**, then **Yes, this one**. The deviation is 4.3 km, over the 2 km limit (6.1), so the rider is told a support agent has the case.
4. Open a **private window** at the same address and sign in as **Support agent**. The case is in "Cases for review"; open it. The left pane shows Sarah's conversation read-only, the middle the agent room, the right the summary (AI recommendation partial S$3.44 and why it was escalated).
5. Ask `Did the rider have any luggage?`, **Check wording**, **Confirm and ask**. Nothing in the record says, so the question goes to Sarah. In Sarah's window, reply `Yes, two suitcases.`; the console answers the original question citing that message.
6. **Approve AI recommendation**, add a note, **Submit decision**. Sarah's window shows the outcome card; both show "Resolved".

How the two new agents work (`app/agents/rephrase.py`, `app/agents/case_qa.py`, both on the existing `BaseAgent`):

- **Rephrase agent**: fixes spelling and grammar and sets a professional tone without changing the meaning; messages to the rider get a short polite wrapper and are addressed to "you". Offline it is deterministic (a small typo dictionary, capitalisation, punctuation, a fixed template). In Live AI mode the model is called only when the text is not already clean or needs translating into Chinese; otherwise no request is spent. Everything a person sends to the rider goes through it.
- **Case-QA agent**: a deterministic retrieval step always runs first over the recorded case only (ticket, extracted facts, every rider message, the tool outputs, both advocates' arguments). If nothing relevant is retrieved, no model is called: the answer is "not mentioned by the rider" and the question goes to the rider. Otherwise the answer is built from the retrieved snippets only, by the model in Live AI mode (its citations must match snippet sources, else the template answer is used) or by a template offline. Every answer cites its sources, e.g. "Rider message, 21:03", "Chat log, 13:24 (rider)", "GPS log".

Rider-facing messages are in Chinese when the rider writes in Chinese (or the UI is set to 中文), otherwise English. Offline the rephraser cannot translate, so a Chinese rider gets the Chinese template around the agent's question as typed. Cases live in server memory (`app/case_store.py`) and are lost on restart.

## How it works

```
 Rider's own words (+ optional trip)
          |
   [ Trip match ]  story -> one of the rider's recent trips, or "which trip?" (no ruling)
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
          |
   AI may rule alone? --yes--> rider gets the outcome card (resolved_by_ai)
          | no
   [ Support console ]  summary card; case-QA agent (retrieval first, cites sources; asks the rider when the record
                        has no answer); rephrase agent on everything sent to the rider; a person decides
          |
   rider gets the outcome card (resolved_by_human)
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
cp .env.example .env     # set LLM_MODE=llm and LLM_API_KEY=... (and a random SECRET_KEY for the login cookie)
./run.sh
```

Any OpenAI-compatible endpoint works (default: Google AI Studio, Gemini; Tencent Hunyuan via `LLM_BASE_URL` / `LLM_MODEL`). **Never commit `.env`**; it is git-ignored. In LLM mode the model reasons freely, and the section 6 thresholds are still enforced in code from the tool data; the judge's output is cross-checked against the deterministic policy computation (`policy_check`).

## Using it

This section describes the classic single-chat UI at `/classic` (sign in first at `/`). As a rider it only offers your own trips and preset tickets; as the support agent, all of them.

- Write a complaint in your own words (English, Singlish, Malay, Tamil or Chinese) and press **Submit and rule**. The trip selector defaults to **Auto-detect from my story**; you can still pick a trip by hand. You never choose the dispute type. If the story does not point to one trip, the intake agent asks which one and offers the candidates as buttons.
- **EN | 中文** toggle switches the interface and the agents' output language; rulings, clause numbers and amounts are identical in both.
- The dropdown replays six preset tickets: DISP-001 route deviation, DISP-002 no-show, DISP-003 fare dispute (all from the official Ryde datasets), plus DISP-004 property damage, DISP-005 safety incident and DISP-006 sparse evidence (synthetic).

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | mode, provider, model |
| `GET /api/disputes`, `GET /api/trips` | preset tickets, trips a complaint can be filed against |
| `GET /api/file/stream?complaint=&trip_id=&lang=en\|zh&mode=` | free-text complaint, SSE stream of every step. `trip_id` optional: empty or `auto` matches it from the story; an explicit one skips matching |
| `POST /api/file` | same, synchronous; returns `status: trip_unresolved` with candidates and no ruling when no trip matches |
| `GET /api/resolve/{id}/stream`, `POST /api/resolve/{id}` | replay a preset ticket |
| `GET /api/auth/accounts`, `POST /api/auth/login` `{rider_id}` or `{role: "support"}`, `POST /api/auth/logout`, `GET /api/auth/me` | demo login (no password); sets / clears the signed session cookie |
| `POST /api/rider/find-trip` `{story, lang?}` | stage 1 (rider only): `state` clarify / none / confirm / pick, with trip cards from the signed-in rider's trips only |
| `POST /api/cases` `{story, trip_id, mode?, lang?}` | rider only: start a case on a confirmed trip of the signed-in rider (403 for anyone else's trip) |
| `GET /api/cases`, `GET /api/cases/{id}` | a rider's own cases; for support, every case handed to a person. Someone else's case is 404 |
| `GET /api/cases/{id}/events` | one SSE stream per case; every event carries `pane`: `rider`, `room`, `human` or `case` (status). The tag is `pane` because orchestrator events already use `role` for the agent |
| `POST /api/cases/{id}/rider-message` `{text, trip_id?}` | the rider's reply (or which trip it was) |
| `POST /api/cases/{id}/human/rephrase` `{text, purpose: qa\|rider\|note}` | support only: "You wrote" / "Will be sent as" |
| `POST /api/cases/{id}/human/ask` `{question, original?}` | case-QA answer, or the question goes to the rider |
| `POST /api/cases/{id}/human/decision` `{action: approve\|adjust\|reject\|request_info, amount?, note?}` | the person's decision (adjust needs an amount and a note) |

All endpoints except `/api/health` and the login ones need a session (401 otherwise); `human/*` need the support role (403 for riders). A rider's event stream and case snapshot never include the console's data.

Free-text SSE events (existing ones unchanged): `trip_matched {trip_id, route, confidence, reasons, candidates}`, `trip_unresolved {message, candidates}` (followed by `done`, no ruling), `ticket_filed {ticket}`.
Case statuses: `intake`, `in_review`, `resolved_by_ai`, `with_agent`, `waiting_for_rider`, `resolved_by_human`.

## Data

`fixtures/` holds trips, profiles, `policies/policy_v2_1.json`, `precedents.json` and tickets. Names were removed from profiles. Ground-truth outcomes for tests live in `fixtures/expected/` and are never returned by any tool. Official Ryde datasets are used as provided (field names kept); the property-damage, safety and sparse-evidence cases are synthetic. Expected offline results: DISP-001 partial S$3.44 (human approval required), DISP-002 rejected, DISP-003 upheld S$4.50, DISP-004 upheld S$35, DISP-005 escalated, DISP-006 escalated.

## Repository layout

```
app/main.py            FastAPI + SSE; / is the three-pane demo, /classic the original chat
app/case_store.py      in-memory cases for the three-pane demo, event fan-out by pane, human decisions
app/case_views.py      rider outcome card, support-console summary (built from the recorded case)
app/auth.py            demo login: signed session cookie, rider / support roles
app/rider_match.py     stage 1: which of the signed-in rider's trips a story is about
app/orchestrator.py    trip match -> intake -> advocates (parallel) -> judge -> thresholds -> safety net; safety incident path
app/trip_match.py      story -> trip scoring, claim_check (story vs records, informational)
app/extract.py         rule-based story -> extracted_facts, missing_info
app/agents/            base loop, intake, advocates, judge, cases.py, analysis.py (deterministic policy facts),
                       rephrase.py and case_qa.py (support console)
app/thresholds.py      policy section 6 in code
app/safety_net.py      evidence-sufficiency check per dispute type
app/tools/             11 tools + OpenAI-style schemas
static/                login.html/js/css; three.html/js/css (three-pane demo, embeds app.js for the agent room); index.html (classic)
scripts/smoke_three_pane.py  browser smoke test (Playwright): login, stage 1, escalation, support queue
scripts/build_trips_synthetic.py  writes fixtures/trips_synthetic.json and fixtures/demo_accounts.json
fixtures/              trips, profiles, policy, precedents, tickets, expected (tests only)
tests/                 pytest suite (offline)
architecture.svg/png   diagram
PROJECT_DESCRIPTION.md submission write-up
```

## Honest limitations

- The real-LLM path has not been re-run since the Policy v2.1 rebuild (it was verified on the earlier synthetic version). Offline results above are verified; treat live-model behaviour on the new dispute types as untested until you run it with a key.
- Fixture data only: no live GPS, payment or refund execution. Rulings are decided, not executed.
- Deterministic mode uses keyword rules for intake and fact extraction; arbitrary phrasing relies on the real LLM. Trip matching only knows the six fixture trips (all treated as "the rider's recent trips") and their place names plus a small alias list.
- The LLM path of the new ticket extraction has not been run against a live model; its validation and fallback are covered by offline tests only.
- "At the pickup location" has no distance in the policy; we use 100 m as an operational definition. The confidence weights are our own.
- Free-tier LLM quotas can return 429; the UI offers the deterministic fallback.
- The login is a demo: pick an account, no password. The session cookie is signed but not `Secure` (the demo runs on plain http); without a `SECRET_KEY` in `.env` a random key is used and sessions end when the server restarts. Stage 1 matching is rule-based in both modes (the model is not used to classify or extract there). "Today" / "yesterday" are read against the real date, so they do not match the September 2026 fixture trips.
- Three-pane demo: the Live AI paths of the rephrase and case-QA agents have not been run against a live model (to save the free quota); their fallbacks, citation check and "no retrieval, no model call" rule are covered by offline tests. Offline answers are the retrieved snippets in a template, not prose. Retrieval is keyword and topic based, so a question worded unlike the record can miss and be sent to the rider instead. Cases are in memory, single process.
