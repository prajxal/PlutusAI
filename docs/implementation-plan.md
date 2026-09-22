# Business Dashboard + What-If Simulator — Implementation Plan

**Goal:** a business owner uploads their sales data, gets a dashboard built
around whatever is actually in it, and asks plain-language "what if" questions
— price changes, cost changes, make-vs-buy — answered with transparent maths
against their own history.

This is a college major project built to a production-minded standard. This
document is the shared source of truth: anyone should be able to read it and
know what they are building, what their module receives, and what it hands off.

**Status:** Phases 1–5 are built and tested. Phase 6 (the fine-tuned intent
model) and Phase 7 (this document, Docker, deploy) are the current work. See
[Section 5](#5-build-order-and-status).

> **This document was rewritten when the project left AWS.** The original plan
> was built around Cognito, API Gateway, Lambda, DynamoDB, S3, Bedrock,
> EventBridge and Step Functions. None of those are used. What replaced each
> one, and why, is in [Section 2](#2-architecture).

---

## 1. End-to-End User Flow

1. User signs in (email + password, argon2-hashed, HS256 session token).
2. User uploads a CSV of sales data — a normal multipart POST to the API.
3. The system maps the CSV's columns to the internal schema, validates rows,
   and reports the ones it had to reject rather than failing the whole file.
4. The system generates a dashboard: KPIs, charts and anomalies, chosen by a
   stated rule and computed in code.
5. User asks questions in a chat panel beside the dashboard — either **insight
   questions** ("why did my margin drop in March?") or **what-if scenarios**
   ("what if I raise the sourdough 10%?"). Both go through one interface.
6. The chat pipeline classifies the intent, fills the slots it needs from the
   message, calls exactly one tool, and narrates the result. If a required
   number is missing, it asks for it in the next reply.
7. What-ifs run against the business's real history using transparent maths.
   No model supplies a figure.
8. The user sees a before/after chart beside the explanation, and can save the
   scenario.
9. Each business owner's data is private to their account.

---

## 2. Architecture

One Python process and one React app. No cloud accounts, no hosted SDKs.

```
Browser (React SPA, Vite)
   │  fetch + Bearer token
   ▼
FastAPI  backend/app.py            ← the only place an HTTP status is chosen
   │
   ├── services/accounts.py        register / login
   ├── services/ingest.py          CSV → records
   ├── services/dashboard.py       records → kpis / charts / anomalies
   ├── services/chat/              message → reply (+ chart)
   │      └── services/simulation.py    the maths
   └── services/refresh.py         background dashboard rebuild after upload
          │
          ▼
   shared/repository.py → shared/store.py
          ├── JsonStore       a single file, the default
          └── PostgresStore   DATABASE_URL, schema applied at startup
```

**What replaced what, and why:**

| Was | Is | Why |
|---|---|---|
| Cognito | `shared/auth.py` — argon2 + HS256 | One dependency, no console, and tenancy we can reason about in one file |
| API Gateway + 8 Lambdas | One FastAPI app | The handlers lost `(event, context)` and became functions that take arguments and return values. No 29 s ceiling, no cold starts, no proxy-event plumbing |
| DynamoDB | PostgreSQL, or a JSON file | Typed columns for what we filter and sort on; JSONB for the rest. The JSON store means the project runs with no database daemon at all |
| S3 + presigned URLs | `POST /api/uploads` | The two-step presign dance existed only to get large files past API Gateway's 10 MB limit |
| Bedrock (dashboard KPIs) | A stated rule in code | Revenue and margin always, then whatever moved most. Explainable, and impossible to get wrong |
| Bedrock (chat agent loop) | A 5-stage deterministic pipeline | See below |
| Step Functions + EventBridge | A FastAPI `BackgroundTask` | The orchestration existed to cross a network boundary that no longer exists |
| Amplify Hosting | `Dockerfile` — API serves the built SPA | One container, one port, same origin |

**Why the tool-calling loop became a pipeline.** The loop's job was to pick a
tool and read back the result. Both are now decisions that can be tested,
explained and shown to the owner:

```
message → classify intent → fill slots → call one tool → narrate
```

What a learned model may influence is deliberately tiny: **one label out of
six**. Which product, how much, what the numbers are, and what the sentence
says are all code.

---

## 2a. Foundation Rules (fixed)

1. **Tenancy comes from the session, never the request.** `business_id` is
   derived server-side from the verified token. A request that tries to name
   its own is **refused**, not ignored — a bug that starts sending one should
   fail in development rather than pass quietly in production.
   (`shared/auth.py:reject_client_tenancy`, and note that request models allow
   extra fields on purpose so a smuggled `business_id` is visible to it.)
2. **The token does not carry `business_id`.** A claim nobody trusts is a claim
   nobody can accidentally start trusting.
3. **Simulations are transparent.** Every result reports the method used, its
   assumptions and a confidence level, and the reply repeats them.
4. **Numbers come from code, never from a model.**
5. **The classifier is handed the message and no business data at all** — not
   the products, not the figures, not an id. Whatever runs there cannot leak a
   customer's numbers.

---

## 3. Modules — Contracts

### Module A — Ingestion (`services/ingest.py`)
**In:** `business_id`, filename, raw CSV bytes. **Out:** `{records, rejected, meta}`.
Column mapping is heuristic — real CSVs say "Qty Sold" and "Selling Price".
A row that cannot be read is reported with a reason and a line number and the
rest of the file still loads: one bad date should never cost a business their
whole upload. Extra columns (store, channel) are preserved as `extras` and
become part of a record's identity.

### Module B — Dashboard (`services/dashboard.py`)
**In:** `business_id`. **Out:** `{kpis, charts, anomalies, source}`.
Revenue and margin always appear; the remaining slots go to whatever moved
most. Max 4 KPIs, 3 charts.

### Module C — Chat (`services/chat/`)
**In:** `{session_id, message}` (`business_id` from the session).
**Out:** `{reply, chart, assumptions, scenario_saved_id, intent{name, confidence, source}}`,
plus `method`, `method_plain`, `confidence`, `summary.metrics[]` and `detail`
when a simulation ran.
Five files, one each for: what is being asked (`intent.py`), with which values
(`slots.py`), the three things it can do (`tools.py`), how to say it
(`narrate.py`), and the pipeline that joins them (`service.py`).
Session ownership is checked before any history loads.

### Module D — Simulation (`services/simulation.py`)
**In:** `business_id`, `scenario_type`, `params`. **Out:** the transparent
result — `{baseline, projected, series, method, assumptions, confidence}`.
Plain Python. No model calls, no pandas: the maths is sums and one
least-squares fit. Three scenario types: `price_change`, `cost_change`,
`make_vs_buy`.

**Demand response** picks the best method the data supports and says which:
1. `elasticity_from_history` — needs 3+ distinct prices, ≥5% spread, ≥60 days,
   R² ≥ 0.5. A positive slope is rejected as noise.
2. `user_supplied` — if the owner gives one.
3. `default_elasticity` — −0.8, stated as an assumption, always `low` confidence.

### Module F — Refresh (`services/refresh.py`)
Re-runs Module B after new data lands, scheduled as a background task by the
upload route.

### Module G — Frontend (`frontend/src/`)
Sign-in, upload, dashboard, chat. No router and no state library: one
authenticated screen, all shared state in `App.jsx`. The layout is the
argument — numbers in the sheet, reasoning in the conversation.
Confidence drives how a projection is *drawn*: a low-confidence result is a
loose, wide band you can see is not worth acting on before reading a word.

### Module H — Auth and persistence (`shared/`)
`auth.py` (tenancy, argon2, tokens) and `store.py` (one interface, two stores).

### Module I — Intent model (`ml/`) — Phase 6
The one learned component. See [Section 6](#6-the-intent-model-phase-6).

---

## 4. Data Model

Typed columns for anything filtered, joined or sorted on; JSONB for the rest,
so adding a field needs no migration.

```
businesses (business_id PK, name, meta JSONB, created_at)
    ├── users         (user_id PK, email UNIQUE, password_hash, business_id FK)
    ├── records       (business_id FK, record_date DATE, product, dimension,
    │                  payload JSONB, UNIQUE(business_id, record_date, product, dimension))
    ├── scenarios     (scenario_id PK, business_id FK, created_at, payload JSONB)
    └── session_turns (session_id, business_id FK, role, content, tool_calls,
                       created_at, expires_at DEFAULT now() + 30 days)
```

That `UNIQUE` on `records` is load-bearing: two outlets selling the same item
on the same day must not overwrite each other. The JSON store expresses the
same identity as `record#<date>#<product>[#<dimension>]`.

`schema.sql` is idempotent and applied at startup, so there is no migration
tool to keep in step with it.

---

## 5. Build Order and Status

| Phase | What | State |
|---|---|---|
| 1 | De-AWS the runtime — Lambdas → services, one FastAPI app | **done** |
| 2 | PostgreSQL store behind the `Store` interface | **done** |
| 3 | Local auth — register/login/me, argon2, JWT | **done** |
| 4 | Uploads + background dashboard refresh | **done** |
| 5 | Frontend auth and the full UI | **done** |
| 6 | The fine-tuned intent model | in progress |
| 7 | Docs, Dockerfile, deploy | in progress |

---

## 6. The Intent Model (Phase 6)

The seam has been in `services/chat/intent.py` from the start: `IntentClassifier`
is a Protocol, `RegexIntentClassifier` implements it, and `PLUTUS_INTENT_MODEL_URL`
swaps in `ModelIntentClassifier` instead. Every reply reports which one answered
it, in `intent.source`.

**The baseline is a real bar, not a straw man.** The regexes are exact on the
phrasings they know and blind to everything else — high precision, low recall.
Against the hand-written eval set: macro-F1 **0.469** overall, **0.549** on
English, **0.309** on Hinglish.

**The risk that governs the whole phase.** Training on labels produced by
`rules.py` is distillation, and a student cannot beat its teacher — we would
have built an expensive regex emulator. Two things prevent that:

- **The eval set is hand-written and never generated.** 134 examples,
  deliberately including phrasings the regexes get wrong, plus Hinglish and
  Devanagari. No training template appears in it.
- **Training labels come from the template that generated the sentence**, not
  from the regexes. The regexes are kept as a cross-check: they agree with only
  ~33% of generated labels, and the other ~67% is precisely the headroom.

**Reported separately for English and Hinglish**, because one number over both
hides the only interesting result.

```
ml/
├── taxonomy.py          the label space (6 intents, 4 metrics + "none")
├── generate_dataset.py  templated paraphrases, balanced per class
├── data/eval_set.jsonl  HAND-WRITTEN. the honest number comes from here
├── model.py             one encoder, two heads
├── train.py             fine-tune (MPS / CUDA / CPU)
├── infer.py             load a checkpoint and classify
├── evaluate.py          accuracy + macro-F1 vs the baseline
└── serve.py             POST {"message"} → {"intent", "confidence", "metric"}
```

The application must run with no model at all, and must survive the model
going away: any failure — unreachable, timeout, malformed body, a label outside
the taxonomy — falls back to the regexes and marks the reply `rules_fallback`.

---

## 7. Demo Script (target: under 3 minutes)

1. Upload a sample sales CSV → dashboard appears, tailored to the data. *(~20s)*
2. Ask an insight question ("why did my margin drop in March?") → real numbers,
   plain English. *(~15s)*
3. Ask a price-change what-if → chart updates, method and confidence stated. *(~30s)*
4. Ask a make-vs-buy what-if → it asks the one number it is missing, you answer,
   the chart updates with breakeven against real historical volume. *(~40s)*
5. Ask the same question in Hinglish → the model handles what the regexes
   cannot, and `intent.source` shows which answered. *(~20s)*
6. Show saved scenario history. *(~15s)*

---

## 8. Folder Structure

```
plutusai/
├── Dockerfile                  one container: API + built SPA
├── backend/
│   ├── app.py                  every route; the only place a status is chosen
│   ├── services/               ingest, dashboard, simulation, chat/, accounts, refresh
│   └── shared/                 auth, store, postgres_store, repository, models,
│                               config, errors, log, schema.sql
├── frontend/src/               api/, auth/, components/, lib/, styles/
├── ml/                         Phase 6 — see Section 6
├── tests/                      one suite, runnable against either store
├── scripts/                    seed_sample_data.py, deploy.sh
└── docs/
    ├── implementation-plan.md  this document
    └── CODEMAPS/               token-lean architecture maps
```

---

## 9. Definition of Done (MVP)

- [x] CSV upload → structured data stored, rejected rows reported
- [x] Dashboard generates from real data
- [x] Chat routes between insight questions and what-if scenarios
- [x] Three what-if types: price change, cost change, make-vs-buy
- [x] It asks for a missing number in-chat rather than guessing
- [x] Before/after chart renders beside the reply
- [x] Conversation history persists, and is checked for ownership
- [x] Login works; data is private per business, `business_id` from the session only
- [x] Simulation results show method, assumptions and confidence
- [x] The interface *draws* confidence rather than labelling it
- [ ] The intent model beats the baseline on the hand-written eval set
- [ ] Deployed and reachable at a URL
- [ ] Demo rehearsed end-to-end twice

---

## 10. Decisions

**Taken:**

| Decision | Where it landed |
|---|---|
| Chat transport | Single request/response. The 29 s gateway limit was an API Gateway constraint and no longer exists |
| Projection semantics | Historical replay — re-run the period actually traded with the change applied, so projections inherit real seasonality and forecast nothing |
| Elasticity thresholds | 3+ prices, ≥5% spread, ≥60 days, R² ≥ 0.5; `high` needs ≥10% spread. Default −0.8, always `low` |
| Which KPIs appear | Revenue and margin always, then biggest movers. A figure that has not moved tells the owner nothing |
| Dashboard caching | On request, plus a background rebuild after upload |
| Column mapping | Heuristics with per-row rejection. No model involved |
| Storage | One interface, two implementations. JSON file by default, PostgreSQL for anything real |
| No pandas | The maths is sums and one least-squares fit |
| Where a model may act | One label out of six, and never with business data in the request |

**Still open:**

| Decision | Notes |
|---|---|
| Where the intent model is hosted | `ml/serve.py` runs anywhere; a HF Inference Endpoint or Space is the likely home. Config is a URL, so it is a deployment choice, not a code one |
| Where the app is deployed | Any container host. Needs `PLUTUS_DEV_MODE=0` and a pinned `PLUTUS_JWT_SECRET` |
| Account recovery | Email verification, password reset, MFA and sign-in rate limiting are **not built**, and are stated as absent rather than half-implemented |
| Multi-scenario comparison views | Polish |
| Real datasets | Synthetic generator today |
