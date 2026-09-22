#!/usr/bin/env python3
"""
The PlutusAI application. One process, no cloud accounts.

    python3 backend/app.py                 # http://127.0.0.1:8000
    uvicorn app:app --app-dir backend --reload

This replaces API Gateway and eight Lambda functions. The services it calls
are the same code that ran behind them, minus the proxy-event plumbing: a
service now takes arguments and returns a value, and raising ApiError is how it
reports a problem. Turning that into HTTP happens once, here.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import BackgroundTasks, Depends, FastAPI, File, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from shared import config, repository  # noqa: E402
from shared.auth import (  # noqa: E402
    Principal,
    principal_from_claims,
    principal_from_token,
    reject_client_tenancy,
)
from shared.errors import ApiError, AuthError  # noqa: E402
from shared.log import logger  # noqa: E402
from shared.store import close_store  # noqa: E402

from services import accounts as accounts_service  # noqa: E402
from services import dashboard as dashboard_service  # noqa: E402
from services import ingest as ingest_service  # noqa: E402
from services import refresh as refresh_service  # noqa: E402
from services.chat import service as chat_service  # noqa: E402

@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.DEV_MODE:
        ensure_demo_data()
    yield
    close_store()


app = FastAPI(
    title="PlutusAI",
    description="Business dashboard and what-if simulator.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- errors ------------------------------------------------------------------

@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    """Services raise; this is the only place a status code is chosen."""
    logger.warn(exc.message, status=exc.status_code, path=request.url.path)
    body = {"error": exc.message}
    if exc.details:
        body["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    """An internal message is not something to show a business owner."""
    logger.error("Unhandled error", exc, path=request.url.path)
    return JSONResponse(status_code=500, content={"error": "Something went wrong on our side."})


# --- identity ----------------------------------------------------------------

async def current_principal(request: Request) -> Principal:
    """Who is calling, from the signed token and nothing else.

    The X-Dev-User shortcut exists so the seeded demo works without signing in.
    It is gated on DEV_MODE, which is why DEV_MODE must be off in a deployment:
    with it on, this header is a way to be anyone.
    """
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return principal_from_token(header[7:].strip())

    if config.DEV_MODE:
        subject = request.headers.get("X-Dev-User") or "dev-user"
        return principal_from_claims({"sub": subject, "email": f"{subject}@example.test"})

    raise AuthError()


# --- payloads ----------------------------------------------------------------

class TenantSafeModel(BaseModel):
    """Undeclared fields are kept, not dropped.

    Pydantic's default is to discard what it does not recognise, which would
    make a body carrying business_id invisible to reject_client_tenancy -- the
    rule would silently pass instead of loudly failing, which is the opposite
    of the point. Nothing reads these extras except that check.
    """

    model_config = ConfigDict(extra="allow")


class RegisterRequest(TenantSafeModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    business_name: str | None = Field(default=None, max_length=120)


class LoginRequest(TenantSafeModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ChatRequest(TenantSafeModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="default", max_length=128)


class ScenarioRequest(TenantSafeModel):
    question: str
    summary: str | None = None
    scenario_type: str | None = None
    params: dict | None = None
    baseline: dict | None = None
    projected: dict | None = None
    method: str | None = None
    confidence: str | None = None


# --- routes ------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"ok": True, "store": config.STORE_BACKEND,
            "intent": "model" if config.INTENT_MODEL_URL else "rules"}


@app.post("/api/auth/register")
async def register(payload: RegisterRequest):
    reject_client_tenancy(payload.model_dump())
    return accounts_service.register(payload.email, payload.password, payload.business_name)


@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    reject_client_tenancy(payload.model_dump())
    return accounts_service.login(payload.email, payload.password)


@app.get("/api/auth/me")
async def me(principal: Principal = Depends(current_principal)):
    meta = repository.get_business_meta(principal.business_id)
    return {"email": principal.email, "business_id": principal.business_id,
            "business_name": meta.get("business_name")}


@app.get("/api/dashboard")
async def get_dashboard(principal: Principal = Depends(current_principal)):
    return dashboard_service.generate(principal.business_id)


@app.post("/api/uploads")
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
):
    """The browser posts the CSV straight here.

    No presigned URL, no second request, no 10 MB ceiling -- that whole dance
    existed to get large files past API Gateway.
    """
    result = ingest_service.save_upload(
        principal.business_id, file.filename or "upload.csv", await file.read()
    )
    # Rebuilding the dashboard takes a moment and the owner does not need to
    # wait for it; this is all Module F's state machine was ever doing.
    background.add_task(refresh_service.refresh, principal.business_id)
    return {"records": result["records"], "rejected": result["rejected"], "meta": result["meta"]}


@app.post("/api/chat")
async def chat(payload: ChatRequest, principal: Principal = Depends(current_principal)):
    reject_client_tenancy(payload.model_dump())
    return chat_service.answer(principal.business_id, payload.session_id, payload.message)


@app.get("/api/scenarios")
async def list_scenarios(limit: int = 10, principal: Principal = Depends(current_principal)):
    return chat_service.list_scenarios(principal.business_id, min(max(limit, 1), 50))


@app.post("/api/scenarios")
async def save_scenario(payload: ScenarioRequest,
                        principal: Principal = Depends(current_principal)):
    reject_client_tenancy(payload.model_dump())
    return {"scenario_id": chat_service.save_scenario(principal.business_id,
                                                      payload.model_dump())}


# --- the built frontend -------------------------------------------------------

def mount_frontend() -> None:
    """Serve frontend/dist from this process when it has been built.

    A deployment is then one container and one port, with no CORS involved
    because the UI and the API share an origin. In local development the
    directory does not exist and Vite serves the UI instead, so this is a
    no-op and nothing changes.

    Mounted last: every /api route is already registered by now, so the
    catch-all below cannot shadow one.
    """
    dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "frontend", "dist")
    if not os.path.isdir(dist):
        return

    from fastapi.staticfiles import StaticFiles

    # html=True makes the SPA's index.html the answer for any unknown path,
    # which is what a client-side-routed app needs on a hard refresh.
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    logger.info("Serving the built frontend", path=dist)


# --- development convenience --------------------------------------------------

def ensure_demo_data() -> str | None:
    """A fresh machine has nothing to show, so seed it."""
    principal = principal_from_claims({"sub": "dev-user", "email": "dev-user@example.test"})
    if repository.get_business_records(principal.business_id):
        return principal.business_id

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts"))
    from seed_sample_data import csv_text

    result = ingest_service.ingest_csv_text(principal.business_id, "sample_sales.csv", csv_text())
    meta = repository.get_business_meta(principal.business_id)
    repository.put_business_meta(principal.business_id, {**meta, "business_name": "Amba Bakehouse"})
    logger.info("Seeded sample data", business_id=principal.business_id, records=result["records"])
    return principal.business_id


mount_frontend()


def main():
    import uvicorn

    business_id = ensure_demo_data() if config.DEV_MODE else None
    print(f"\n  PlutusAI on http://{config.HOST}:{config.PORT}")
    print(f"  store:  {config.STORE_BACKEND}")
    print(f"  intent: {'fine-tuned model' if config.INTENT_MODEL_URL else 'deterministic classifier'}")
    if business_id:
        print(f"  demo:   {business_id}")
    print()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
