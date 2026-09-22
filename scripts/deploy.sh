#!/usr/bin/env bash
# Build and check the whole thing. No cloud provider involved.
#
#   ./scripts/deploy.sh            build + test, then print how to serve it
#   ./scripts/deploy.sh --docker   also build the container image
set -euo pipefail

cd "$(dirname "$0")/.."

DOCKER=0
[[ "${1:-}" == "--docker" ]] && DOCKER=1

echo "==> Backend dependencies"
pip install -q -r backend/requirements.txt

echo "==> Tests"
python3 -m pytest tests -q

echo "==> Frontend build"
(cd frontend && npm ci --silent && npm run build)

if [[ $DOCKER -eq 1 ]]; then
  echo "==> Container image"
  docker build -t plutusai .
fi

cat <<'NOTE'

==> Built.

The API serves frontend/dist itself, so this is one process on one port and
there is no CORS involved in a deployment.

  Container (everything in one image):

    docker build -t plutusai .
    docker run -p 8000:8000 \
      -e PLUTUS_JWT_SECRET="$(openssl rand -base64 32)" \
      -e PLUTUS_STORE=postgres \
      -e DATABASE_URL=postgresql://user:pass@host/plutusai \
      plutusai

  Or directly:

    createdb plutusai                          # optional; the JSON store needs nothing

    export PLUTUS_DEV_MODE=0                   # disables the X-Dev-User header
    export PLUTUS_JWT_SECRET="$(openssl rand -base64 32)"
    export PLUTUS_STORE=postgres
    export DATABASE_URL=postgresql:///plutusai

    uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000

  The intent model is a separate service and is entirely optional -- with no
  model configured the deterministic classifier answers, and the app is fully
  functional:

    python3 ml/serve.py --model ml/artifacts --port 8100
    export PLUTUS_INTENT_MODEL_URL=http://127.0.0.1:8100/classify

Two settings must not be forgotten:

  PLUTUS_DEV_MODE=0   leaving it at 1 lets anyone be any user via a header.
  PLUTUS_JWT_SECRET   unset, it is regenerated per process and every restart
                      signs every user out.

The Dockerfile sets PLUTUS_DEV_MODE=0 already. It deliberately does not set a
JWT secret: an absent secret fails visibly, a default one fails quietly.
NOTE
