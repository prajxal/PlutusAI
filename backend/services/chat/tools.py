"""
The three things the chat service can actually do.

business_id is the first argument of every one of them and is never a field a
caller can set: it is resolved from the verified session and passed in here
(Foundation Rule 1). Nothing in this module is reachable by a model -- the
classifier chooses a name, and this code decides what that name may touch.
"""
from shared import repository
from shared.errors import ApiError
from shared.models import totals_of

METRIC_ATTR = {"revenue": "revenue", "cost": "cost", "units_sold": "units_sold"}


def get_metric(business_id, metric, product=None, date_range=None):
    """Insight-question tool. Reads from BusinessData."""
    records = repository.get_business_records(business_id)
    if not records:
        raise ApiError(404, "There is no data loaded for this business yet.")

    if product:
        product = _match_product(records, product)
        records = [r for r in records if r.product == product]
    if date_range:
        start, end = date_range.get("from"), date_range.get("to")
        records = [r for r in records if (not start or r.date >= start) and (not end or r.date <= end)]
    if not records:
        return {"values": [], "summary_stats": {"min": 0, "max": 0, "avg": 0},
                "note": "Nothing matched that product or date range."}

    # Monthly buckets: a year of daily rows is noise to reason over.
    months = sorted({r.month for r in records})
    values = []
    for month in months:
        rows = [r for r in records if r.month == month]
        if metric == "margin":
            value = totals_of(rows).margin
        elif metric in METRIC_ATTR:
            value = sum(getattr(r, METRIC_ATTR[metric]) for r in rows)
        else:
            raise ApiError(400, f"I do not track {metric!r}. I have revenue, margin, units_sold and cost.")
        values.append({"date": month, "value": round(value, 2)})

    numbers = [v["value"] for v in values]
    return {
        "values": values,
        "summary_stats": {
            "min": round(min(numbers), 2),
            "max": round(max(numbers), 2),
            "avg": round(sum(numbers) / len(numbers), 2),
        },
        "product": product,
    }


def run_simulation(business_id, scenario_type, params):
    """What-if tool. Calls the simulation engine (Module D) directly.

    This used to cross a Lambda boundary with JSON on both sides. It is a
    function call now -- same maths, no serialisation, no 29-second ceiling.
    """
    from services.simulation import run

    return run(business_id, scenario_type, params)


def list_scenarios(business_id, limit=5):
    """The what-ifs this owner kept."""
    rows = repository.list_scenarios(business_id, limit)
    return {
        "scenarios": [
            {
                "scenario_id": s.get("scenario_id"),
                "question": s.get("question"),
                "summary": s.get("summary"),
                "created_at": s.get("created_at"),
            }
            for s in rows
        ]
    }


def products_of(business_id) -> list:
    return sorted({r.product for r in repository.get_business_records(business_id)})


def _match_product(records, name):
    """Match what the owner called it to what the file calls it.

    They say "sourdough"; the CSV says "Sourdough loaf". An exact match wins,
    then a containment match, and an ambiguous one is refused rather than
    guessed at.
    """
    products = sorted({r.product for r in records})
    lowered = name.strip().lower()
    for product in products:
        if product.lower() == lowered:
            return product
    hits = [p for p in products if lowered in p.lower() or p.lower() in lowered]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ApiError(400, f"Did you mean {' or '.join(hits)}?")
    raise ApiError(404, f"I could not find {name!r}. You sell: {', '.join(products)}.")
