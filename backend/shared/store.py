"""
Storage behind one interface.

JsonStore keeps everything in a single file so the project runs with no
database daemon at all; PostgresStore (Phase 2) is the real one. Every service
talks to the interface, so nothing above this file knows which is active.
"""
import json
import os
import threading
import time
import uuid
from typing import Protocol

from shared import config
from shared.log import logger


class Store(Protocol):
    def get_user(self, user_id: str) -> dict | None: ...
    def get_user_by_email(self, email: str) -> dict | None: ...
    def put_user(self, user_id: str, business_id: str, email: str | None = None,
                 password_hash: str | None = None) -> dict: ...
    def get_business_records(self, business_id: str) -> list: ...
    def put_business_records(self, business_id: str, records: list) -> int: ...
    def replace_business_records(self, business_id: str, records: list) -> int: ...
    def get_business_meta(self, business_id: str) -> dict: ...
    def put_business_meta(self, business_id: str, meta: dict) -> None: ...
    def save_scenario(self, business_id: str, scenario: dict) -> str: ...
    def list_scenarios(self, business_id: str, limit: int = 5) -> list: ...
    def get_session_turns(self, session_id: str, business_id: str, limit: int = 20) -> list: ...
    def append_session_turn(self, session_id: str, business_id: str, role: str,
                            content, tool_calls=None) -> None: ...


# --------------------------------------------------------------------- local --

class JsonStore:
    """Single-file store. Not concurrent-safe across processes; a lock keeps it
    consistent within one. Good enough for tests and a single-user laptop, and
    the reason PostgresStore exists for anything beyond that."""

    def __init__(self, directory: str):
        self.path = os.path.join(directory, "store.json")
        self._lock = threading.Lock()
        os.makedirs(directory, exist_ok=True)

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"users": {}, "records": {}, "meta": {}, "scenarios": {}, "sessions": {}}
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, data: dict) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        os.replace(tmp, self.path)

    def _mutate(self, fn):
        with self._lock:
            data = self._read()
            result = fn(data)
            self._write(data)
            return result

    def get_user(self, user_id):
        return self._read()["users"].get(user_id)

    def get_user_by_email(self, email):
        wanted = (email or "").strip().lower()
        return next(
            (u for u in self._read()["users"].values() if (u.get("email") or "").lower() == wanted),
            None,
        )

    def put_user(self, user_id, business_id, email=None, password_hash=None):
        existing = self.get_user(user_id) or {}
        user = {
            "user_id": user_id,
            "business_id": business_id,
            "email": (email or existing.get("email") or "").strip().lower() or None,
            # Never blank out a stored hash by omitting it.
            "password_hash": password_hash or existing.get("password_hash"),
        }
        self._mutate(lambda d: d["users"].__setitem__(user_id, user))
        return user

    def get_business_records(self, business_id):
        return self._read()["records"].get(business_id, [])

    def put_business_records(self, business_id, records):
        def apply(d):
            existing = {_record_key(r): r for r in d["records"].get(business_id, [])}
            for rec in records:
                existing[_record_key(rec)] = rec
            d["records"][business_id] = list(existing.values())
            return len(records)

        return self._mutate(apply)

    def replace_business_records(self, business_id, records):
        def apply(d):
            d["records"][business_id] = list(records)
            return len(records)

        return self._mutate(apply)

    def get_business_meta(self, business_id):
        return self._read()["meta"].get(business_id, {})

    def put_business_meta(self, business_id, meta):
        self._mutate(lambda d: d["meta"].__setitem__(business_id, meta))

    def save_scenario(self, business_id, scenario):
        scenario_id = scenario.get("scenario_id") or f"scenario#{int(time.time() * 1000)}"
        stored = {**scenario, "scenario_id": scenario_id,
                  "created_at": scenario.get("created_at") or _now()}

        def apply(d):
            d["scenarios"].setdefault(business_id, []).append(stored)
            return scenario_id

        return self._mutate(apply)

    def list_scenarios(self, business_id, limit=5):
        rows = self._read()["scenarios"].get(business_id, [])
        return sorted(rows, key=lambda s: s["created_at"], reverse=True)[:limit]

    def get_session_turns(self, session_id, business_id, limit=20):
        session = self._read()["sessions"].get(session_id)
        if not session:
            return []
        # Ownership is checked here, not by the caller -- plan Section 4.
        if session.get("business_id") != business_id:
            from shared.errors import ApiError

            raise ApiError(403, "That conversation belongs to another account.")
        return session["turns"][-limit:]

    def append_session_turn(self, session_id, business_id, role, content, tool_calls=None):
        turn = {"role": role, "content": content, "tool_calls": tool_calls, "at": _now()}

        def apply(d):
            session = d["sessions"].setdefault(
                session_id, {"business_id": business_id, "turns": []}
            )
            if session.get("business_id") != business_id:
                from shared.errors import ApiError

                raise ApiError(403, "That conversation belongs to another account.")
            session["turns"].append(turn)

        self._mutate(apply)


# ------------------------------------------------------------------ plumbing --

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _record_key(rec: dict) -> str:
    return _sk(rec)


def _sk(rec: dict) -> str:
    """record#<date>#<product>[#<dimension>] -- the dimension suffix stops two
    rows for the same date and product overwriting each other."""
    extras = rec.get("extras") or {}
    dimension = "|".join(
        str(extras[k]) for k in sorted(extras) if extras[k] not in (None, "")
    )
    key = f"record#{rec['date']}#{rec['product']}"
    return f"{key}#{dimension}" if dimension else key


_store = None


def get_store() -> Store:
    global _store
    if _store is None:
        if config.STORE_BACKEND == "postgres":
            from shared.postgres_store import PostgresStore

            _store = PostgresStore(config.DATABASE_URL)
            logger.info("Using PostgreSQL store")
        else:
            _store = JsonStore(config.LOCAL_DATA_DIR)
            logger.info("Using single-file JSON store", path=_store.path)
    return _store


def close_store() -> None:
    """Release connections held by the active store, if it holds any."""
    global _store
    if _store is not None and hasattr(_store, "close"):
        _store.close()
    _store = None


def reset_store_for_tests(store=None):
    global _store
    _store = store
