"""
The persistence helpers every service uses. Keep this thin -- one read or write
per collection, no business logic here.

Each one delegates to the active store (shared/store.py). Callers never choose
which store is behind it.
"""
from shared.models import BusinessRecord
from shared.store import get_store


def get_business_records(business_id):
    """Every record for a business, as BusinessRecord objects."""
    return [BusinessRecord.from_item(item) for item in get_store().get_business_records(business_id)]


def put_business_records(business_id, records):
    """Upsert records. Accepts BusinessRecord objects or plain dicts."""
    items = [r.to_item() if isinstance(r, BusinessRecord) else r for r in records]
    return get_store().put_business_records(business_id, items)


def replace_business_records(business_id, records):
    items = [r.to_item() if isinstance(r, BusinessRecord) else r for r in records]
    return get_store().replace_business_records(business_id, items)


def get_business_meta(business_id):
    """Provenance for the most recent upload: file name, row counts, range."""
    return get_store().get_business_meta(business_id)


def put_business_meta(business_id, meta):
    return get_store().put_business_meta(business_id, meta)


def save_scenario(business_id, scenario):
    return get_store().save_scenario(business_id, scenario)


def list_scenarios(business_id, limit=5):
    return get_store().list_scenarios(business_id, limit)


def get_session_turns(session_id, business_id, limit=20):
    """Ownership is verified against business_id before any history is loaded."""
    return get_store().get_session_turns(session_id, business_id, limit)


def append_session_turn(session_id, business_id, role, content, tool_calls=None):
    return get_store().append_session_turn(session_id, business_id, role, content, tool_calls)
