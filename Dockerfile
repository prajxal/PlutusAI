# PlutusAI -- the application in one image.
#
#   docker build -t plutusai .
#   docker run -p 8000:8000 -e PLUTUS_DEV_MODE=0 -e PLUTUS_JWT_SECRET=... plutusai
#
# The frontend is built in the first stage and served as static files by the
# same process that serves the API, so a deployment is one container and one
# port. The intent model is deliberately NOT in here: it is a separate service
# behind PLUTUS_INTENT_MODEL_URL (ml/serve.py, or a hosted endpoint), and the
# application runs perfectly well with no model at all.

# --- frontend ----------------------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
# Same-origin by default: the API serves these files, so no host to point at.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- application -------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

# Dependencies first, so a code change does not reinstall psycopg every build.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY --from=frontend /build/dist ./frontend/dist

# Nothing here needs root.
RUN useradd --create-home --uid 10001 plutus \
    && mkdir -p /app/backend/uploads /app/backend/.localdata \
    && chown -R plutus:plutus /app
USER plutus

# Defaults a deployment must not inherit silently: DEV_MODE off means the
# X-Dev-User header stops being a way to be anyone. JWT_SECRET is intentionally
# absent -- unset, every restart signs all users out, which is a visible
# failure rather than a quiet one.
ENV PLUTUS_DEV_MODE=0 \
    PLUTUS_HOST=0.0.0.0 \
    PLUTUS_PORT=8000 \
    PLUTUS_STORE=memory \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
