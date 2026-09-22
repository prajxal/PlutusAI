# PlutusAI — Business Dashboard + What-If Simulator

College major project. A business owner uploads their sales data, gets a
dashboard built around whatever is actually in it, and asks plain-language
"what if" questions — price changes, make-vs-buy — answered with transparent
maths against their own history.

Runs entirely on a laptop. No cloud accounts.

## Run it

```bash
pip install -r backend/requirements.txt
python3 backend/app.py                    # API on :8000, seeds sample data
cd frontend && npm install && npm start    # UI on :5173
python3 -m pytest tests                    # the suite
```

Optional, for a real database:

```bash
brew services start postgresql@18 && createdb plutusai
PLUTUS_STORE=postgres python3 backend/app.py
```

Optional, for the fine-tuned intent classifier (the app runs fine without it):

```bash
pip install -r ml/requirements.txt
python3 ml/serve.py --model ml/artifacts --port 8100
PLUTUS_INTENT_MODEL_URL=http://127.0.0.1:8100/classify python3 backend/app.py
```

Or the whole thing as one container, API and UI on one port:

```bash
docker build -t plutusai .
docker run -p 8000:8000 -e PLUTUS_JWT_SECRET="$(openssl rand -base64 32)" plutusai
```

## Repo layout

- `frontend/` — React app: sign-in, upload, dashboard, chat panel
- `backend/app.py` — the FastAPI application
- `backend/services/` — ingestion, dashboard, simulation, chat, accounts
- `backend/shared/` — storage, tenancy, errors, logging
- `ml/` — the fine-tuned intent classifier: data, training, evaluation, serving
- `tests/` — one suite, runnable against either storage backend
- `scripts/` — sample data generator, build/deploy helper
- `docs/` — implementation plan and architecture codemaps

## The idea it is built around

Every projection carries the method that produced it, the assumptions it rests
on, and a confidence level — and the interface draws that confidence rather
than labelling it. A low-confidence result is rendered as a loose, wide band
you can see is not worth acting on before you read a word of it.

Numbers come from code, never from a model. The only learned component is a
six-way intent classifier that decides what the owner is asking for; it is
handed the message and no business data at all.

That classifier is the whole of Phase 6. Against a hand-written eval set it
takes macro-F1 from 0.469 to 1.000, and on Hinglish — where the deterministic
baseline collapses to "I do not understand" — from 0.309 to 1.000. Read that
perfect score sceptically: it means the eval set is saturated, not that the
model is. [`ml/README.md`](./ml/README.md) explains why, and what a more honest
measurement would need.

If the model is unreachable the regexes answer instead and the reply says so,
so a hosted classifier going down costs answer quality, never the answer.

See [`backend/README.md`](./backend/README.md) for configuration and
architecture, [`ml/README.md`](./ml/README.md) for the model, and
[`docs/CODEMAPS/`](./docs/CODEMAPS/) for token-lean architecture maps.
