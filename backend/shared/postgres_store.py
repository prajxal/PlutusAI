"""
PostgreSQL implementation of the Store interface.

Chosen for one reason above the rest: JSONB. Identity and anything we filter,
sort or join on is a real column with a real type; everything else is a
document. Adding a field to a record or a scenario therefore needs no ALTER
TABLE and no migration.

The schema lives in schema.sql and is applied at startup. It is written to be
safe to run repeatedly, so there is no migration tool to keep in step with it.
"""
import json
import os
import time
import uuid

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from shared.errors import ApiError
from shared.log import logger

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


class PostgresStore:
    def __init__(self, dsn: str, apply_schema: bool = True):
        # A pool because FastAPI runs sync endpoints on a thread pool and a
        # psycopg connection is not safe to share between threads.
        self.pool = ConnectionPool(dsn, min_size=1, max_size=10, kwargs={"row_factory": dict_row},
                                   open=True)
        if apply_schema:
            self.apply_schema()

    def apply_schema(self) -> None:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            ddl = fh.read()
        with self.pool.connection() as conn:
            conn.execute(ddl)
        logger.info("Schema applied")

    def close(self) -> None:
        self.pool.close()

    # --- users ---------------------------------------------------------------

    def get_user(self, user_id: str):
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT user_id, email, password_hash, business_id FROM users WHERE user_id = %s",
                (user_id,),
            ).fetchone()

    def get_user_by_email(self, email: str):
        with self.pool.connection() as conn:
            return conn.execute(
                "SELECT user_id, email, password_hash, business_id FROM users WHERE email = %s",
                (email.strip().lower(),),
            ).fetchone()

    def put_user(self, user_id: str, business_id: str, email=None, password_hash=None):
        with self.pool.connection() as conn:
            # The business row has to exist before a user can reference it.
            conn.execute(
                "INSERT INTO businesses (business_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (business_id,),
            )
            conn.execute(
                """INSERT INTO users (user_id, email, password_hash, business_id)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE
                     SET email = COALESCE(EXCLUDED.email, users.email),
                         password_hash = COALESCE(EXCLUDED.password_hash, users.password_hash),
                         business_id = EXCLUDED.business_id""",
                (user_id, (email or "").strip().lower() or None, password_hash, business_id),
            )
        return {"user_id": user_id, "email": email, "business_id": business_id}

    # --- records -------------------------------------------------------------

    def get_business_records(self, business_id: str) -> list:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT record_date, product, payload FROM records
                   WHERE business_id = %s ORDER BY record_date, product""",
                (business_id,),
            ).fetchall()
        return [
            {
                "date": row["record_date"].isoformat(),
                "product": row["product"],
                **row["payload"],
            }
            for row in rows
        ]

    def put_business_records(self, business_id: str, records: list) -> int:
        self._ensure_business(business_id)
        rows = [
            (
                business_id,
                rec["date"],
                rec["product"],
                _dimension(rec),
                Jsonb({
                    "units_sold": rec["units_sold"],
                    "unit_price": rec["unit_price"],
                    "unit_cost": rec["unit_cost"],
                    "extras": rec.get("extras") or {},
                }),
            )
            for rec in records
        ]
        with self.pool.connection() as conn, conn.cursor() as cur:
            # One round trip for the whole file instead of one per row.
            cur.executemany(
                """INSERT INTO records (business_id, record_date, product, dimension, payload)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (business_id, record_date, product, dimension)
                   DO UPDATE SET payload = EXCLUDED.payload""",
                rows,
            )
        return len(rows)

    def replace_business_records(self, business_id: str, records: list) -> int:
        self._ensure_business(business_id)
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM records WHERE business_id = %s", (business_id,))
        return self.put_business_records(business_id, records)

    # --- business meta -------------------------------------------------------

    def get_business_meta(self, business_id: str) -> dict:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT meta FROM businesses WHERE business_id = %s", (business_id,)
            ).fetchone()
        return (row or {}).get("meta") or {}

    def put_business_meta(self, business_id: str, meta: dict) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO businesses (business_id, name, meta) VALUES (%s, %s, %s)
                   ON CONFLICT (business_id) DO UPDATE
                     SET meta = EXCLUDED.meta,
                         name = COALESCE(EXCLUDED.name, businesses.name)""",
                (business_id, meta.get("business_name"), Jsonb(meta)),
            )

    # --- scenarios -----------------------------------------------------------

    def save_scenario(self, business_id: str, scenario: dict) -> str:
        self._ensure_business(business_id)
        scenario_id = scenario.get("scenario_id") or f"scenario#{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}"
        stored = {**scenario, "scenario_id": scenario_id,
                  "created_at": scenario.get("created_at") or _now()}
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO scenarios (scenario_id, business_id, payload) VALUES (%s, %s, %s)
                   ON CONFLICT (scenario_id) DO UPDATE SET payload = EXCLUDED.payload""",
                (scenario_id, business_id, Jsonb(stored)),
            )
        return scenario_id

    def list_scenarios(self, business_id: str, limit: int = 5) -> list:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT payload FROM scenarios WHERE business_id = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (business_id, limit),
            ).fetchall()
        return [row["payload"] for row in rows]

    # --- conversations -------------------------------------------------------

    def get_session_turns(self, session_id: str, business_id: str, limit: int = 20) -> list:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """SELECT business_id, role, content, tool_calls, created_at
                   FROM session_turns WHERE session_id = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (session_id, limit),
            ).fetchall()
        # Ownership is checked here, not by the caller.
        for row in rows:
            if row["business_id"] != business_id:
                raise ApiError(403, "That conversation belongs to another account.")
        return [
            {"role": r["role"], "content": r["content"], "tool_calls": r["tool_calls"],
             "at": r["created_at"].isoformat()}
            for r in reversed(rows)
        ]

    def append_session_turn(self, session_id, business_id, role, content, tool_calls=None):
        self._ensure_business(business_id)
        with self.pool.connection() as conn:
            owner = conn.execute(
                "SELECT business_id FROM session_turns WHERE session_id = %s LIMIT 1",
                (session_id,),
            ).fetchone()
            if owner and owner["business_id"] != business_id:
                raise ApiError(403, "That conversation belongs to another account.")
            conn.execute(
                """INSERT INTO session_turns (session_id, business_id, role, content, tool_calls)
                   VALUES (%s, %s, %s, %s, %s)""",
                (session_id, business_id, role, content,
                 Jsonb(tool_calls) if tool_calls is not None else None),
            )

    # --- plumbing ------------------------------------------------------------

    def _ensure_business(self, business_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO businesses (business_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (business_id,),
            )


def _dimension(rec: dict) -> str:
    """The extra key that keeps two rows for the same date and product apart."""
    extras = rec.get("extras") or {}
    return "|".join(str(extras[k]) for k in sorted(extras) if extras[k] not in (None, ""))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
