# RydeResolve

**Autonomous dispute resolution where every ruling is evidence-audited.**

A multi-agent system that resolves ride-hailing disputes (route deviation, no-show cancellation fees) end to end: it reads the rider's complaint in their own words, gathers evidence with tools, argues both sides, rules by written policy, and then a **deterministic safety net** refuses to auto-refund when the evidence behind the ruling is too thin, whatever the model's confidence says.

Built for the **Tencent Cloud AI CAN DO IT Hackathon, Singapore 2026** (Ryde / AI Agent Digital Native track), developed with WorkBuddy / CodeBuddy.

Live demo: see the link in the submission (the app also runs fully offline, see Quick start).

---

## How it works

```
 Rider's own words + trip
          |
   [ Intake agent ]  reads the complaint (any language), decides route_deviation / no_show_charge
          |
   +------+-------------------+
   |                          |          run in parallel (asyncio.gather)
 [ Rider advocate ]     [ Driver advocate ]     each builds a case from tool data only
   |                          |
   +------+-------------------+
          |
     [ Judge ]   does NOT trust the advocates: re-queries the tools, applies the policy clauses
          |
   [ Safety net ]   deterministic rules, independent of the model
          |
  Ruling JSON: upheld | partial | rejected | escalated   (+ model_assessment, safety_net audit blocks)
```

**Eight tools** (read JSON fixtures; they return evidence, never judgments): `get_trip_data`, `get_gps_telemetry`, `get_chat_logs`, `get_app_events`, `get_rider_profile`, `get_driver_profile`, `get_policy`, `get_traffic_reference`.

**Policies** (fixtures/policies): no-show charge `CN-1..CN-4` (driver within 100 m and stopped, 5 min free wait, at least one contact attempt, otherwise full refund) and route deviation `RD-1..RD-3` (15% tolerance, refund formula for the excess, traffic exemption).

### The safety net

After the judge rules, `app/safety_net.py` re-fetches the evidence sources and forces `ruling = "escalated"` (refund withheld, human review) if either rule fires:

- **Rule A**: the judge's `evidence_cited` contains fewer than 3 distinct data points.
- **Rule B**: GPS has fewer than 3 points, or chat fewer than 2 messages, or app events fewer than 2.

Neither rule reads the model's confidence score. The model's own verdict is preserved in `model_assessment` so a human reviewer can see what the model thought and why the system overrode it. Rule A depends on what the model chooses to cite; Rule B depends only on the data.

In our run on the sparse-evidence case (DISP-003: 2 GPS points, no chat, driver located about 420 m from the pickup) the real LLM ruled `upheld, refund 25, confidence 1.0`; the safety net escalated it because GPS and chat were near-empty.

## Quick start

Python 3.11+.

```bash
pip install -r requirements.txt
./run.sh                 # http://localhost:8000
```

With no API key it runs in **deterministic mode** (scripted agents, same tools and same policy maths), so the demo always works. To use a real model:

```bash
cp .env.example .env     # then set LLM_MODE=llm and LLM_API_KEY=...
./run.sh
```

Any OpenAI-compatible endpoint works. The default in `.env.example` is Google AI Studio (Gemini 3.5 Flash Lite); Tencent Hunyuan also works by changing `LLM_BASE_URL` / `LLM_MODEL`. **Never commit `.env`**; it is git-ignored.

## Using it

- Open the page, write a complaint in your own words (English, Singlish, Malay, Tamil or Chinese), pick a trip, press **Submit and rule**. You never choose the dispute type; the intake agent does.
- **EN | 中文** toggle (top right) switches the whole interface and the language of the agents' output. The choice is remembered in the browser.
- The dropdown at the top right replays four preset tickets. `DISP-004` is the official Ryde sample (Tiong Bahru Plaza no-show, TRIP-2026-09945).
- The badge shows the backend actually in use (for example `Gemini · gemini-3.5-flash-lite`, or `Deterministic fallback`).

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | mode, provider, model |
| `GET /api/disputes`, `GET /api/trips` | preset tickets, trips a complaint can be filed against |
| `GET /api/file/stream?trip_id=&complaint=&lang=en\|zh&mode=` | free-text complaint, Server-Sent Events stream of every step |
| `POST /api/file` | same, synchronous: `{trip_id, complaint, lang, mode}` -> ruling + all events |
| `GET /api/resolve/{id}/stream`, `POST /api/resolve/{id}` | replay a preset ticket |

`lang` only changes human-readable text; ruling values, clause IDs and numbers are identical in both languages.

## Fixtures and data

`fixtures/` holds trips, profiles, policies and tickets. `TRIP-1001..1003` are **synthetic** Singapore-labelled cases (amounts are illustrative; coordinates are shifted placeholders). `TRIP-2026-09945` / `DISP-004` is the **official Ryde sample dataset**, loaded as provided. Expected offline results: DISP-001 partial (S$30), DISP-002 rejected, DISP-003 escalated, DISP-004 rejected (the cancellation charge stands).

## Repository layout

```
app/main.py            FastAPI + SSE
app/orchestrator.py    intake -> advocates (parallel) -> judge -> safety net
app/agents/            base loop, intake, rider/driver advocates, judge, deterministic analysis
app/safety_net.py      the deterministic evidence-sufficiency check
app/tools/             8 tools + OpenAI-style schemas
app/i18n.py            EN / zh helper
static/                single-page UI (index.html, app.js, style.css)
fixtures/              trips, profiles, policies, tickets
architecture.svg/png   architecture diagram
PROJECT_DESCRIPTION.md submission write-up
```

## Honest limitations

- Two dispute types only; policies are the ones in `fixtures/policies` (modelled on the hackathon brief), not Ryde's production rules.
- Data is fixture-based; there is no live GPS or payment integration, and refunds are not executed, only decided.
- Deterministic mode uses keyword rules for intake (English, Singlish, Malay, Tamil, Chinese keywords). Understanding of arbitrary phrasing and languages relies on the real LLM.
- Free-tier LLM quotas can return 429; the client backs off and retries, and the UI offers the deterministic fallback.
