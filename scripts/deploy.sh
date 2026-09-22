#!/usr/bin/env bash
# Build the frontend and run the backend. No cloud provider involved.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Backend dependencies"
pip install -q -r backend/requirements.txt

echo "==> Tests"
python3 -m pytest tests -q

echo "==> Frontend build"
(cd frontend && npm ci --silent && npm run build)

cat <<'NOTE'

==> Built. To serve it:

    # 1. A database (optional -- the JSON store needs nothing)
    createdb plutusai

    # 2. Settings a deployment must pin
    export PLUTUS_DEV_MODE=0                  # disables the X-Dev-User header
    export PLUTUS_JWT_SECRET="$(openssl rand -base64 32)"
    export PLUTUS_STORE=postgres
    export DATABASE_URL=postgresql:///plutusai
    export PLUTUS_CORS_ORIGINS=https://your-frontend-host

    # 3. Run it
    uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000

frontend/dist/ is static -- serve it from anything, and set VITE_API_URL at
build time to point at the API.

Leaving PLUTUS_DEV_MODE=1 in a deployment lets anyone be any user via a
header. It is the one setting that must not be forgotten.
NOTE
