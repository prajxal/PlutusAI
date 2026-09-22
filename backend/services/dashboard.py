"""
Dashboard generation (Module B).
Input: business_id. Output: { kpis, charts, anomalies, source }

Every figure on this dashboard is computed here, in code (Foundation Rule 4).
Which figures get shown used to be a model's decision; it is now a stated
rule -- revenue and margin always, then whatever moved most. That is both
explainable to the owner and impossible to get wrong, and it keeps the
"tailored to what is actually in their data" promise without asking a model
a question it cannot answer better than a sort.
"""
from shared import repository
from shared.errors import ApiError
from shared.log import logger
from shared.models import months_between, totals_of

MAX_KPIS = 4
MAX_CHARTS = 3

# An owner opens the dashboard to see these two first, whatever else moved.
ALWAYS_SHOW = ["revenue_total", "gross_margin"]


# --------------------------------------------------------------- candidates --

def build_candidates(records) -> dict:
    """Compute every figure the dashboard could show. All values in code."""
    months = months_between(records)
    half = len(months) // 2 or 1
    recent_months, earlier_months = set(months[half:]), set(months[:half])

    recent = [r for r in records if r.month in recent_months]
    earlier = [r for r in records if r.month in earlier_months]

    overall = totals_of(records)
    now, before = totals_of(recent), totals_of(earlier)
    units = sum(r.units_sold for r in records)
    units_now = sum(r.units_sold for r in recent)
    units_before = sum(r.units_sold for r in earlier)
    label = f"on the previous {len(earlier_months)} months"

    kpis = {
        "revenue_total": _kpi("Revenue", overall.revenue, "currency",
                              now.revenue, before.revenue, label),
        "gross_margin": _kpi("Gross margin", overall.margin, "percent",
                             now.margin, before.margin, label, points=True),
        "units_sold": _kpi("Units sold", units, "count", units_now, units_before, label),
        "profit_total": _kpi("Gross profit", overall.profit, "currency",
                             now.profit, before.profit, label),
        "avg_unit_price": _kpi(
            "Average price per unit", (overall.revenue / units) if units else 0, "currency",
            (now.revenue / units_now) if units_now else 0,
            (before.revenue / units_before) if units_before else 0, label),
    }

    by_product = {}
    for r in records:
        bucket = by_product.setdefault(r.product, {"units": 0.0, "revenue": 0.0})
        bucket["units"] += r.units_sold
        bucket["revenue"] += r.revenue
    # Each bar chart is ordered by the measure it actually plots -- a chart of
    # units sold ranked by revenue reads as unsorted.
    by_revenue = sorted(by_product.items(), key=lambda kv: kv[1]["revenue"], reverse=True)
    by_units = sorted(by_product.items(), key=lambda kv: kv[1]["units"], reverse=True)

    charts = {
        "monthly_revenue": {
            "id": "monthly_revenue", "type": "line", "title": "Monthly revenue",
            "unit": "currency", "x": months,
            "series": [{"name": "Revenue", "y": _monthly(records, months, "revenue")}],
        },
        "monthly_profit": {
            "id": "monthly_profit", "type": "line", "title": "Monthly gross profit",
            "unit": "currency", "x": months,
            "series": [{"name": "Gross profit", "y": _monthly(records, months, "profit")}],
        },
        "units_by_product": {
            "id": "units_by_product", "type": "bar", "title": "Units sold by product",
            "unit": "count", "x": [p for p, _ in by_units],
            "series": [{"name": "Units", "y": [round(v["units"]) for _, v in by_units]}],
        },
        "revenue_by_product": {
            "id": "revenue_by_product", "type": "bar", "title": "Revenue by product",
            "unit": "currency", "x": [p for p, _ in by_revenue],
            "series": [{"name": "Revenue", "y": [round(v["revenue"], 2) for _, v in by_revenue]}],
        },
    }
    return {"kpis": kpis, "charts": charts}


def _kpi(label, value, unit, now, before, change_label, points=False):
    """A KPI plus how it moved. `points` marks a percentage, where the honest
    comparison is the difference in points, not the percent of a percent."""
    if points:
        change = now - before
    else:
        change = ((now - before) / before * 100) if before else 0.0
    trend = "flat" if abs(change) < 0.15 else ("up" if change > 0 else "down")
    return {
        "label": label,
        "value": round(value, 2),
        "unit": unit,          # PROPOSED: the contract has a bare number
        "trend": trend,
        "change": round(abs(change), 1),
        "change_label": change_label,
    }


def _monthly(records, months, attr):
    totals = {m: 0.0 for m in months}
    for r in records:
        totals[r.month] += getattr(r, attr)
    return [round(totals[m], 2) for m in months]


# ---------------------------------------------------------------- anomalies --

def detect_anomalies(records) -> list:
    """Things worth a look, found by rule rather than by the model.

    Each detector answers one question an owner would actually ask.
    """
    found = []
    by_product_month = {}
    for r in records:
        bucket = by_product_month.setdefault((r.product, r.month), [])
        bucket.append(r)

    products = sorted({r.product for r in records})
    months = months_between(records)

    for product in products:
        series = [(m, by_product_month.get((product, m), [])) for m in months]
        series = [(m, rows) for m, rows in series if rows]

        # A margin that fell hard from one month to the next.
        for (prev_month, prev_rows), (month, rows) in zip(series, series[1:]):
            before, after = totals_of(prev_rows).margin, totals_of(rows).margin
            if before - after >= 5:
                cost_before = _avg(prev_rows, "unit_cost")
                cost_after = _avg(rows, "unit_cost")
                price_after = _avg(rows, "unit_price")
                detail = ""
                if cost_after > cost_before * 1.05:
                    detail = (f" Your cost went from {cost_before:.0f} to {cost_after:.0f} "
                              f"while the price stayed at {price_after:.0f}.")
                found.append(
                    f"{product} margin fell {before - after:.0f} points in "
                    f"{_month_name(month)}, from {before:.0f}% to {after:.0f}%.{detail}"
                )
                break

        # A month that sold well clear of the product's normal volume.
        volumes = [sum(r.units_sold for r in rows) for _, rows in series]
        if len(volumes) >= 4:
            mean = sum(volumes) / len(volumes)
            for (month, _), volume in zip(series, volumes):
                if mean and volume > mean * 1.2:
                    found.append(
                        f"{product} sold {(volume / mean - 1) * 100:.0f}% above its usual "
                        f"volume in {_month_name(month)}."
                    )
                    break

        # Enough price history to measure demand response -- this is what
        # decides whether a what-if comes back trustworthy, so say it here.
        prices = {round(r.unit_price, 2) for r in records if r.product == product}
        if len(prices) >= 3:
            found.append(
                f"{product} has traded at {len(prices)} different prices this year, which is "
                f"enough for me to measure how its demand responds rather than assume it."
            )

    return found[:4]


def _avg(rows, attr):
    units = sum(r.units_sold for r in rows)
    return sum(getattr(r, attr) * r.units_sold for r in rows) / units if units else 0.0


def _month_name(month: str) -> str:
    names = "January February March April May June July August September October November December".split()
    year, mon = month.split("-")
    return f"{names[int(mon) - 1]} {year}"


# ---------------------------------------------------------------- selection --

def select_kpis(candidates: dict) -> list:
    """Revenue and margin always, then whichever others moved most.

    A KPI that has not moved tells the owner nothing they did not already
    know, so movement is the ranking.
    """
    chosen = [k for k in ALWAYS_SHOW if k in candidates]
    rest = sorted(
        (k for k in candidates if k not in chosen),
        key=lambda k: candidates[k]["change"],
        reverse=True,
    )
    return (chosen + rest)[:MAX_KPIS]


def select_charts(candidates: dict, kpis: dict) -> list:
    """A line over time plus a breakdown by product.

    If profit moved further than revenue, the line shows profit -- that is the
    month-to-month story worth looking at.
    """
    profit_moved = kpis.get("profit_total", {}).get("change", 0)
    revenue_moved = kpis.get("revenue_total", {}).get("change", 0)
    line = "monthly_profit" if profit_moved > revenue_moved else "monthly_revenue"
    return [c for c in (line, "units_by_product") if c in candidates][:MAX_CHARTS]


# ----------------------------------------------------------------- assemble --

def generate(business_id: str) -> dict:
    records = repository.get_business_records(business_id)
    if not records:
        raise ApiError(404, "No data yet. Upload a CSV and the dashboard builds itself around it.")

    candidates = build_candidates(records)
    kpi_ids = select_kpis(candidates["kpis"])
    chart_ids = select_charts(candidates["charts"], candidates["kpis"])

    meta = repository.get_business_meta(business_id)
    dates = sorted(r.date for r in records)

    logger.info("Dashboard generated", business_id=business_id, records=len(records))

    return {
        "kpis": [candidates["kpis"][k] for k in kpi_ids if k in candidates["kpis"]],
        "charts": [candidates["charts"][c] for c in chart_ids if c in candidates["charts"]],
        "anomalies": detect_anomalies(records),
        # PROPOSED: provenance. The first thing an owner checks is whether the
        # dashboard is reading the file they think it is.
        "source": {
            "business_name": meta.get("business_name") or _title(business_id),
            "file": meta.get("file", "your uploaded file"),
            "rows": meta.get("rows", len(records)),
            "rejected_rows": meta.get("rejected_rows", 0),
            "from": meta.get("from", dates[0]),
            "to": meta.get("to", dates[-1]),
        },
    }


def _title(business_id: str) -> str:
    return business_id.replace("biz-", "").replace("-", " ").title() or "Your business"
