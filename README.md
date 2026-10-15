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

`/` starts with a demo login ("Ryde Support"). It offers **one role only: Rider**, and lists exactly the six riders in `fixtures/profiles/riders/` as "Name (R-xxxx)", with the name each profile carries. There is no password; this is a demo login, not real authentication. The server sets a signed session cookie (HMAC with `SECRET_KEY` from `.env`, HttpOnly, SameSite=Lax) and reads the rider ID only from it, never from the browser or the story. Nobody signs in as a driver or a support agent: the support console and the driver view are demo panes inside the signed-in rider's own screen, and everything they show is that rider's own cases. The original single chat is still at `/classic` (behind the same login).

| Pane | What it is |
|---|---|
| **Rider** (left) | The customer's app. Stage 1: the rider says what happened and confirms which of **their own** rides it was. Stage 2: the case runs. Stage 3: one plain-language outcome card (decision, amount, one-line reason, policy section), or "passed to a Ryde support agent" with the case reference and no amount promised, plus any questions from support. A **Rider \| Driver** toggle in the header switches to the driver view of the same cases. |
| **Agent room** (middle) | The existing group chat. Idle ("Waiting for a case") until the rider confirms a ride; then intake, both advocates, judge, policy thresholds and safety net run live. |
| **Support console** (right) | The rider's own cases that need a person: the summary card, evidence chips, "Ask about this case" (recipient Rider, Driver or Auto) and the decision bar. |

**Stage 1, finding the ride** (`app/rider_match.py`, deterministic in both modes). The rider's rides are loaded first, from the session's rider ID, and nothing else is looked at. A story that names another rider, another rider's trip ID or a driver who never drove this rider gets "I can only look at trips on your account." with no hint whether it exists; "show me my rides" lists only their own. Otherwise: the intake rules pick the category (no signal: one clarifying question); the rider's rides are filtered by their ticket type (falling back to the trip evidence); the story ranks them (places, dates, weekdays, today / yesterday, time of day, amounts, driver name). One clear match gets "Is this the one?"; several close ones get a picker (date and time, route, fare, status, why it might match); none of that kind gets the rider's full list. Choosing a ride reuses that ride's ticket (dispute ID, trip, driver); the rider's story becomes the ticket's description. If the story sounds like another kind of dispute than the ride's ticket, the rider is asked before anything starts (policy 5.2 still makes any story with safety indicators a safety incident). A ride has one case: choosing it again reopens that case. `property_damage` is shown as "Property damage / cleaning fee". A rider's rides are the trips `fixtures/trip_parties.json` gives them: their 10 dataset trips plus their sample trip, if one of the six samples is theirs.

**Scoping:** every tool that returns trip data (`get_trip_data`, GPS, chat, app events, fare breakdown, damage evidence, traffic) and the rider / driver profiles only return the signed-in rider's data; another rider's trip gives the same "not found" as a trip that does not exist. Every endpoint that takes a case or trip ID answers 404 for one that is not the rider's own, including the console and driver-view endpoints. In Live AI mode only the rider's own records can reach a prompt.

**Driver view (no driver login, no driver chooser):** shows, for each of the rider's cases, that case's own driver as the server resolves it from the trip ("Driver: Nur Aisyah (D-4410)"), a trip card (date, pickup to drop-off), support's questions and the reply box; the toggle badges count unanswered questions on each side. The driver view shows no rider story, amount or profile, only the rider's first name.

In the console, "Ask about this case" has a recipient: **Auto** (default), Rider or Driver; the driver is always the case's own driver, never chosen by name. Auto is decided in code (who the question is about, and topic words: waiting, calling, arriving, the route and why, traffic, the vehicle, drop-off for the driver; whereabouts, photos, what they saw, felt or were told for the rider); when it is unsure it picks the rider and says so, and in Live AI mode one short model call may decide instead. The person sees "You wrote", "Will be sent as", who it would go to, and the exact wording the rider or driver would receive, and can edit all of it. The case record is searched first (including driver replies); only if it has no answer is the question sent, and the case shows "Waiting for driver reply", "Waiting for rider reply" or both. A reply lands in the record, refreshes the summary and answers the original question with a citation such as "Driver reply, 21:40". The agent room only gets a neutral line ("Support asked the driver for clarification", "Driver replied"). Driver replies and rider stories are untrusted data: they never change a ruling or a recommendation, and when a model reads them they are wrapped as quoted evidence that must not be followed.

Demo, end to end (offline, no key needed):

1. `LLM_MODE=deterministic ./run.sh`, open http://localhost:8000, sign in as **Priya Nair (R-9001)** and pick **Offline demo**.
2. Click **Route deviation (3 rides fit)**, then **Send**. The picker shows Priya's three route rides (20 Sep, 23 Sep, 12 Oct). Choose **23 Sep, Clementi Mall to Serangoon NEX**.
3. The agent room runs; the 5.0 km deviation is over the 2 km limit (6.1), so Priya is told a support agent has DISP-152. The console shows the summary: AI recommendation upheld S$4.00.
4. In the console, ask `why did the drvier go thru Bukit Timah insted of the KPE?`, **Check wording**: Auto picks **Driver**, and you see the driver's wording. **Confirm and ask**.
5. The **Driver** side of the toggle shows a badge. Click it: "Driver: Nur Aisyah (D-4410)", the 23 Sep trip card, and the question. Reply, e.g. `There was an accident on the KPE so I went through Bukit Timah.`
6. The console answers the original question citing "Driver reply, HH:MM". Click **Rider** to switch back, then approve, adjust or reject in the console.

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

This section describes the classic single-chat UI at `/classic` (sign in first at `/`). It only offers the signed-in rider's own rides and tickets.

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
| `GET /api/auth/accounts`, `POST /api/auth/login` `{rider_id}`, `POST /api/auth/logout`, `GET /api/auth/me` | demo login, riders only (no password); sets / clears the signed session cookie; `me` carries the quick-fill stories built from the rider's own rides |
| `POST /api/rider/find-trip` `{story, lang?}` | stage 1: `state` foreign / list / clarify / none / confirm / pick, with trip cards from the signed-in rider's rides only |
| `POST /api/cases` `{story, trip_id, confirm_type?, mode?, lang?}` | start (or reopen) the case on one of the rider's rides; 404 for anyone else's; 409 with `mismatch` when the story's type differs from the ride's ticket |
| `GET /api/cases`, `GET /api/cases/{id}` | the signed-in rider's own cases; someone else's case is 404 |
| `GET /api/cases/{id}/events` | one SSE stream per case; every event carries `pane`: `rider`, `room`, `human` or `case` (status). The tag is `pane` because orchestrator events already use `role` for the agent |
| `POST /api/cases/{id}/rider-message` `{text, trip_id?}` | the rider's reply (or which trip it was) |
| `POST /api/cases/{id}/human/rephrase` `{text, purpose: qa\|rider\|driver\|note}` | "You wrote" / "Will be sent as" |
| `POST /api/cases/{id}/human/ask` `{question, original?, recipient: auto\|rider\|driver, party_text?}` | case-QA answer from the record, or the question goes to the rider or the driver |
| `POST /api/cases/{id}/human/route` `{question}` | who Auto would send the question to, and why |
| `GET /api/driver-view`, `POST /api/driver-view/reply` `{case_id, text, question_id?}` | the driver view of the signed-in rider's own cases (404 for any other case) |
| `POST /api/cases/{id}/human/decision` `{action: approve\|adjust\|reject\|request_info, amount?, note?}` | the person's decision (adjust needs an amount and a note) |

All endpoints except `/api/health` and the login ones need a rider session (401 otherwise). The console (`human/*`) and driver-view endpoints work on the signed-in rider's own cases only (404 otherwise).

Free-text SSE events (existing ones unchanged): `trip_matched {trip_id, route, confidence, reasons, candidates}`, `trip_unresolved {message, candidates}` (followed by `done`, no ruling), `ticket_filed {ticket}`.
Case statuses: `intake`, `in_review`, `resolved_by_ai`, `with_agent`, `waiting_for_rider`, `waiting_for_driver`, `waiting_for_both`, `resolved_by_human`.

## Data

`fixtures/` holds trips, profiles, `policies/policy_v2_1.json`, `precedents.json` and tickets. Ground-truth outcomes for tests live in `fixtures/expected/` and are never returned by any tool or shown in the UI; tool paths outside the readable folders are refused.

### Test data

- **3 official samples** from the official Ryde datasets, used as provided: DISP-001 route deviation, DISP-002 no-show, DISP-003 fare dispute.
- **3 earlier synthetic samples** written for this project: DISP-004 cleaning claim, DISP-005 safety incident, DISP-006 thin evidence. Expected offline results for the six samples: DISP-001 partial S$3.44 (human approval required), DISP-002 rejected, DISP-003 upheld S$4.50, DISP-004 upheld S$35, DISP-005 escalated, DISP-006 escalated.
- **60 tickets, DISP-101 to DISP-160.** Their dispute IDs, trip IDs, riders, drivers (IDs and names), dispute types and rider-driver pairs come from the team's 60-ticket dataset (its cleaning-fee category is our `property_damage`, shown as "Property damage / cleaning fee"). **All trip details and evidence are synthetic**: dates, places, GPS, chats, fares, photos, repair quotes, traffic incidents, the riders' stories and the profile statistics, generated by `scripts/build_dataset60.py` (fixed seeds; it writes to `build/dataset60/`, which is not committed). The files sit with the samples in `fixtures/disputes/`, `fixtures/trips/` and `fixtures/expected/`; `fixtures/trip_parties.json` maps all 66 trips to their rider and driver, and the 12 profiles in `fixtures/profiles/` carry the names the UI shows. Every rider has 10 of these tickets, at least 2 per type (15 per type), and 30 of the 60 must reach a person by a deterministic rule. `fixtures/stories/stories.json` holds 180 free-text stories (3 per ticket) and 9 that name another rider's trip, for testing the story-to-ticket flow; it is test data only.
- **The expected outcomes in `fixtures/expected/` are our reading of Ryde Policy v2.1**, computed from the policy and each scenario's parameters by the build script, not by calling the app, and not answers from the organisers. Ground truth is never readable by a tool and never reaches an event, the UI or a model prompt (`tests/test_leakage60.py`).

## Repository layout

```
app/main.py            FastAPI + SSE; / is the three-pane demo, /classic the original chat
app/case_store.py      in-memory cases for the three-pane demo, event fan-out by pane, human decisions
app/case_views.py      rider outcome card, support-console summary (built from the recorded case)
app/auth.py            demo login: signed session cookie, rider / support roles
app/rider_match.py     stage 1: which of the signed-in rider's trips a story is about
app/agents/question_router.py  Auto recipient for support questions (rider or driver)
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
scripts/build_dataset60.py  regenerates the 60 dataset tickets, trips, profiles, expected outcomes and stories (into build/dataset60/)
fixtures/stories/      free-text test stories for the 60 tickets (test data only)
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
- The login is a demo: pick one of the six dataset riders, no password. The session cookie is signed but not `Secure` (the demo runs on plain http); without a `SECRET_KEY` in `.env` a random key is used and sessions end when the server restarts. Stage 1 matching is rule-based in both modes (the model is not used to classify or extract there). "Today" / "yesterday" are read against the real date, so they do not match the September 2026 fixture trips.
- The support console and the driver view are demo panes inside the rider's own screen: in this demo the signed-in rider can see and drive their own case's console and driver view. A real deployment would put them behind separate staff and driver accounts. Offline, a question to a Chinese-speaking party keeps the agent's wording inside the Chinese template (no translation). Auto routing is keyword-based; the person always sees and can change the recipient before anything is sent. Questions and replies live in memory with the case.
- Three-pane demo: the Live AI paths of the rephrase and case-QA agents have not been run against a live model (to save the free quota); their fallbacks, citation check and "no retrieval, no model call" rule are covered by offline tests. Offline answers are the retrieved snippets in a template, not prose. Retrieval is keyword and topic based, so a question worded unlike the record can miss and be sent to the rider instead. Cases are in memory, single process.
