"""
Runtime configuration, read from the environment in one place.

Nothing here depends on a cloud provider. Defaults are the values that let the
project run on a laptop with `python3 -m backend.app` and no accounts anywhere.
"""
import os


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


# --- storage -----------------------------------------------------------------
# "memory" keeps everything in a JSON file under backend/.localdata; "postgres"
# uses DATABASE_URL. Both sit behind the Store interface in shared/store.py.
STORE_BACKEND = os.environ.get("PLUTUS_STORE", "memory")
LOCAL_DATA_DIR = os.environ.get(
    "PLUTUS_LOCAL_DATA", os.path.join(os.path.dirname(os.path.dirname(__file__)), ".localdata")
)
# Defaults to the local socket as the current user, which is what a Homebrew
# or apt install gives you after `createdb plutusai` -- no role, no password,
# no container. A deployment sets DATABASE_URL explicitly.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql:///plutusai")

# Uploaded CSVs are kept as evidence of what the dashboard was built from.
UPLOAD_DIR = os.environ.get(
    "PLUTUS_UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
)
MAX_UPLOAD_BYTES = int(os.environ.get("PLUTUS_MAX_UPLOAD_BYTES", str(64 * 1024 * 1024)))

# --- http --------------------------------------------------------------------
HOST = os.environ.get("PLUTUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("PLUTUS_PORT", "8000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "PLUTUS_CORS_ORIGINS", "http://localhost:5173,http://localhost:5183"
    ).split(",")
    if origin.strip()
]

# --- auth (Phase 3) ----------------------------------------------------------
# Generated per process when unset so a laptop needs no setup; a deployment
# must pin it or every restart signs everyone out.
JWT_SECRET = os.environ.get("PLUTUS_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_TTL_MINUTES = int(os.environ.get("PLUTUS_JWT_TTL_MINUTES", "720"))

# --- intent model (Phase 6) --------------------------------------------------
# When unset, the deterministic classifier is used. Setting it points the
# classifier at the fine-tuned encoder we host.
INTENT_MODEL_URL = os.environ.get("PLUTUS_INTENT_MODEL_URL", "")
INTENT_MODEL_TOKEN = os.environ.get("PLUTUS_INTENT_MODEL_TOKEN", "")
INTENT_MODEL_TIMEOUT = float(os.environ.get("PLUTUS_INTENT_MODEL_TIMEOUT", "3.0"))
# Below this the classifier's answer is not trusted and we ask rather than guess.
INTENT_MIN_CONFIDENCE = float(os.environ.get("PLUTUS_INTENT_MIN_CONFIDENCE", "0.55"))

# --- conversation ------------------------------------------------------------
SESSION_TURN_WINDOW = int(os.environ.get("PLUTUS_SESSION_TURNS", "12"))

# --- environment -------------------------------------------------------------
# Dev mode seeds sample data and allows the demo account. Never in a deployment.
DEV_MODE = _flag("PLUTUS_DEV_MODE", "1")

DEFAULT_CURRENCY = os.environ.get("PLUTUS_CURRENCY", "INR")
