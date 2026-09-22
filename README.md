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

## Repo layout

- `frontend/` — React app: sign-in, upload, dashboard, chat panel
- `backend/app.py` — the FastAPI application
- `backend/services/` — ingestion, dashboard, simulation, chat, accounts
- `backend/shared/` — storage, tenancy, errors, logging
- `tests/` — one suite, runnable against either storage backend
- `scripts/` — sample data generator
- `docs/` — implementation plan

## The idea it is built around

Every projection carries the method that produced it, the assumptions it rests
on, and a confidence level — and the interface draws that confidence rather
than labelling it. A low-confidence result is rendered as a loose, wide band
you can see is not worth acting on before you read a word of it.

Numbers come from code, never from a model. The only learned component is a
six-way intent classifier that decides what the owner is asking for; it is
handed the message and no business data at all.

See [`backend/README.md`](./backend/README.md) for configuration and
architecture.
