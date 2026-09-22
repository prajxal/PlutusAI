# PlutusAI backend

One Python process. No cloud accounts, no SDKs for anything hosted.

## Run it

```bash
pip install -r backend/requirements.txt
python3 backend/app.py                  # http://127.0.0.1:8000
```

First run seeds a year of sample bakery data so the dashboard has something to
show. `python3 -m pytest tests` runs the suite.

If `frontend/dist` exists it is served from this process too, so a deployment
is one port with no CORS in play. In development it does not exist and Vite
serves the UI instead.

To use PostgreSQL instead of the single-file store:

```bash
brew services start postgresql@18       # or: pg_ctl -D <datadir> start
createdb plutusai
PLUTUS_STORE=postgres python3 backend/app.py
```

The schema is applied at startup and is written to be safe to re-run, so there
is no migration tool to keep in step with it.

## Layout

| File | Does |
|---|---|
| `app.py` | The FastAPI application. Every route, and the only place a status code is chosen. |
| `services/ingest.py` | CSV → records. Heuristic column mapping, per-row rejection with reasons. |
| `services/dashboard.py` | KPIs, charts and anomalies, all computed in code. |
| `services/simulation.py` | The maths. No model calls, no pandas, fully unit-tested. |
| `services/chat/intent.py` | What the owner is asking for. **The only place a learned model runs.** |
| `services/chat/slots.py` | Which product, how much, which month — deterministic. |
| `services/chat/narrate.py` | Turning a result into a sentence. |
| `services/chat/tools.py` | The three things the chat service can actually do. |
| `services/chat/service.py` | The pipeline that joins those four together. |
| `services/accounts.py` | Registration and sign-in. |
| `shared/auth.py` | Tenancy, passwords and tokens. Foundation Rule 1 lives here. |
| `services/chat/model_intent.py` | The fine-tuned classifier over HTTP, and the fallback to the rules when it is not there. |
| `shared/store.py` | One storage interface; `postgres_store.py` and the JSON store behind it. |

## How a question is answered

```
message → classify intent → fill slots → call one tool → narrate
```

That is the whole pipeline. What a model may influence is deliberately tiny:
**one label out of six.** Which product, how much, what the numbers are, and
what the sentence says are all code. The classifier is handed the raw message
and no business data at all — not the products, not the figures, not an id —
so whatever runs there cannot leak a customer's numbers.

`RegexIntentClassifier` is the default: exact on the phrasings it knows, blind
to everything else. It stays permanently as the fallback, and every reply
reports which classifier answered it, in `intent.source`.

Setting `PLUTUS_INTENT_MODEL_URL` swaps in `ModelIntentClassifier`, which calls
the fine-tuned model over HTTP (`ml/serve.py`, or any host honouring the same
contract). It sends the message and nothing else — no `business_id`, no
products, no figures.

That call is never trusted to succeed. Unreachable, timed out, an HTTP error,
a body that will not parse, or a label outside the taxonomy all fall back to
the regexes and mark the reply `rules_fallback`. A hosted classifier going down
must cost the owner answer *quality*, never the answer itself.

On a hand-written eval set the model takes macro-F1 from 0.469 to 1.000, and
from 0.309 to 1.000 on Hinglish. See [`../ml/README.md`](../ml/README.md),
including why a perfect score there is a statement about the eval set rather
than about the model.

## Tenancy

`business_id` comes from the verified session and nowhere else. A request that
tries to name its own is refused rather than ignored, because a bug that starts
sending one should fail in development instead of passing quietly in
production. The token deliberately does **not** carry `business_id` — a claim
nobody trusts is a claim nobody can accidentally start trusting.

## Configuration

| Variable | Default | |
|---|---|---|
| `PLUTUS_STORE` | `memory` | `memory` (JSON file) or `postgres` |
| `DATABASE_URL` | `postgresql:///plutusai` | Local socket as the current user |
| `PLUTUS_JWT_SECRET` | *(generated)* | **Pin it in a deployment** — unset means every restart signs everyone out |
| `PLUTUS_DEV_MODE` | `1` | Seeds sample data and accepts the `X-Dev-User` header. **Set to `0` in a deployment** |
| `PLUTUS_INTENT_MODEL_URL` | *(unset)* | Points the classifier at the fine-tuned model. Unset, the regexes answer |
| `PLUTUS_INTENT_MODEL_TOKEN` | *(unset)* | Bearer token for that endpoint, if it wants one |
| `PLUTUS_INTENT_MODEL_TIMEOUT` | `3.0` | Seconds before giving up and using the regexes |
| `PLUTUS_UPLOAD_DIR` | `backend/uploads` | Where raw CSVs are kept |
| `PLUTUS_CORS_ORIGINS` | `localhost:5173,5183` | Comma-separated |

## Not built

Stated rather than half-implemented, because a half-built account recovery flow
is worse than an absent one:

- Email verification, password reset, MFA
- Rate limiting on sign-in attempts

## Decisions taken here

- **Projection semantics** — historical replay. The period the business
  actually traded is re-run with the change applied, so projections inherit
  real seasonality and forecast nothing.
- **Elasticity thresholds** — 3+ distinct prices, ≥5% spread, ≥60 days of
  history, R² ≥ 0.5, and a positive slope is rejected as noise. `high`
  confidence needs a ≥10% spread and a good fit. Default elasticity −0.8,
  always `low`.
- **Which KPIs appear** — revenue and margin always, then whatever moved most.
  A figure that has not moved tells the owner nothing they did not know.
- **No pandas** — the maths is sums and one least-squares fit.
