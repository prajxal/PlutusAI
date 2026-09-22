"""
Simulation engine (Module D).
Input: business_id, scenario_type, params
Output: {
  baseline: {revenue, margin, profit}, projected: {...},
  series: {metric, x, baseline_y, projected_y},
  method, assumptions: [str], confidence: "high"|"medium"|"low"
}

IMPORTANT: plain Python math only -- no model calls in this file, ever.
Deterministic and unit-testable; every formula is one sentence:

  revenue          = units x price
  profit           = units x (price - cost)
  margin           = profit / revenue, as a percentage
  demand response  = units x (1 + delta)^elasticity      (constant elasticity)
  breakeven units  = setup cost / saving per unit

Projection semantics (plan Section 10, decided here): historical replay. The
period the business actually traded is re-run with the change applied, so the
projection inherits their real seasonality and makes no forecast about the
future. Every assumption returned says so.

pandas is deliberately not used: the maths is sums and one least-squares fit,
so the standard library covers it and the Lambda needs no SDK-for-pandas layer
(one of the packaging questions in Section 10 disappears).
"""
import math

from shared import repository
from shared.errors import ApiError, MissingParams
from shared.log import logger
from shared.models import Totals, months_between, simulation_result, totals_of

# --- thresholds (plan Section 10 left these open; these are the chosen values) --
MIN_PRICE_POINTS = 3        # distinct prices needed before estimating from history
MIN_PRICE_SPREAD = 0.05     # at least 5% between cheapest and dearest
MIN_DAYS_HISTORY = 60       # a product needs this much trading history
STRONG_SPREAD = 0.10        # spread above this, with a good fit, earns "high"
MIN_FIT_QUALITY = 0.50      # R^2 below this is not a trustworthy elasticity
DEFAULT_ELASTICITY = -0.8   # everyday food is fairly inelastic; a stated assumption

SCENARIO_TYPES = ("price_change", "cost_change", "make_vs_buy")


# ------------------------------------------------------------------ entrypoint --

def run(business_id: str, scenario_type: str, params: dict) -> dict:
    """The only way a simulation is started. business_id is passed in by the
    caller, which has already resolved it from the verified session."""
    if scenario_type not in SCENARIO_TYPES:
        raise ApiError(400, f"I can model {', '.join(SCENARIO_TYPES)} -- not {scenario_type!r}.")

    records = repository.get_business_records(business_id)
    if not records:
        raise ApiError(404, "There is no data to run this against yet. Upload a CSV first.")

    if scenario_type == "price_change":
        result = simulate_price_change(
            records,
            _require(params, "product"),
            _as_fraction(_require(params, "delta_pct")),
            elasticity=_optional_float(params.get("elasticity")),
        )
    elif scenario_type == "cost_change":
        result = simulate_cost_change(
            records, _require(params, "product"), _as_fraction(_require(params, "delta_pct"))
        )
    else:
        result = simulate_make_vs_buy(
            records,
            params.get("item"),
            _optional_float(params.get("in_house_unit_cost")),
            _optional_float(params.get("setup_cost")),
            _optional_float(params.get("current_outsourced_unit_cost")),
        )

    logger.info(
        "Simulation complete",
        business_id=business_id,
        scenario_type=scenario_type,
        method=result["method"],
        confidence=result["confidence"],
    )
    return result


# ------------------------------------------------------------ demand response --

def select_demand_method(records, product, user_elasticity=None):
    """Return (method_name, elasticity, assumptions, confidence).

    Tries the strongest available evidence first and reports which one it used,
    so the agent can repeat it to the owner (Foundation Rule 3). Adding a new
    strategy means adding a branch here and nothing else.
    """
    if user_elasticity is not None:
        return (
            "user_supplied",
            float(user_elasticity),
            [f"Demand response of {user_elasticity} as you specified, not measured from your data."],
            "medium",
        )

    rows = [r for r in records if r.product == product]
    estimate = estimate_elasticity(rows)

    if estimate is None:
        return (
            "default_elasticity",
            DEFAULT_ELASTICITY,
            [
                f"A category assumption that demand falls about "
                f"{abs(DEFAULT_ELASTICITY) * 10:.0f}% for every 10% price rise. "
                f"{product} has not changed price enough for me to measure this from your own data."
            ],
            "low",
        )

    elasticity, points, spread, fit = estimate
    confidence = "high" if (spread >= STRONG_SPREAD and points >= MIN_PRICE_POINTS
                            and fit >= MIN_FIT_QUALITY) else "medium"
    return (
        "elasticity_from_history",
        elasticity,
        # The method itself is reported separately; this is the evidence behind it.
        [
            f"{product} traded at {points} different prices this year, {spread * 100:.0f}% apart, "
            f"and sales moved about {abs(elasticity) * 10:.1f}% for every 10% the price did."
        ],
        confidence,
    )


def estimate_elasticity(rows):
    """Least-squares slope of ln(daily units) on ln(price).

    That slope is the price elasticity of demand by definition. Returns
    (elasticity, price_points, spread, r_squared), or None when the product's
    history is too thin or the fit says something implausible.
    """
    if len({r.date for r in rows}) < MIN_DAYS_HISTORY:
        return None

    # Average daily units at each price, so a price held for longer does not
    # simply look like more demand.
    by_price = {}
    for r in rows:
        bucket = by_price.setdefault(round(r.unit_price, 2), {"units": 0.0, "days": set()})
        bucket["units"] += r.units_sold
        bucket["days"].add(r.date)

    points = [
        (price, b["units"] / len(b["days"]))
        for price, b in by_price.items()
        if price > 0 and b["units"] > 0
    ]
    if len(points) < MIN_PRICE_POINTS:
        return None

    prices = [p for p, _ in points]
    spread = (max(prices) - min(prices)) / min(prices)
    if spread < MIN_PRICE_SPREAD:
        return None

    xs = [math.log(p) for p, _ in points]
    ys = [math.log(u) for _, u in points]
    slope, fit = _least_squares(xs, ys)

    # A positive slope says people bought more when it cost more. That is
    # noise, not a demand curve -- fall back to the stated assumption instead.
    if slope is None or slope >= 0 or fit < MIN_FIT_QUALITY:
        return None
    return slope, len(points), spread, fit


def _least_squares(xs, ys):
    """Slope and R^2 of the best-fit line. Returns (None, 0) if x never varies."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1 - ss_res / ss_tot if ss_tot else 1.0
    return slope, r_squared


# -------------------------------------------------------------------- scenarios --

def simulate_price_change(records, product, delta_pct, elasticity=None):
    """Re-run history with one product's price moved by delta_pct."""
    _assert_product(records, product)
    method, elasticity, assumptions, confidence = select_demand_method(records, product, elasticity)

    price_multiplier = 1 + delta_pct
    if price_multiplier <= 0:
        raise ApiError(400, "A price cannot fall by 100% or more.")
    units_multiplier = price_multiplier ** elasticity

    def project(record):
        if record.product != product:
            return record.units_sold, record.unit_price, record.unit_cost
        return (
            record.units_sold * units_multiplier,
            record.unit_price * price_multiplier,
            record.unit_cost,
        )

    baseline, projected, series = _replay(records, project)
    old_units = sum(r.units_sold for r in records if r.product == product)

    assumptions = assumptions + [
        f"{product}'s cost to you stays the same.",
        "Your other products are unaffected.",
        "The last "
        f"{len(months_between(records))} months are replayed with the new price, "
        "so seasonality is unchanged. This is not a forecast of the months ahead.",
    ]
    result = simulation_result(baseline, projected, series, method, assumptions, confidence)
    result["detail"] = {
        "product": product,
        "delta_pct": round(delta_pct * 100, 2),
        "elasticity": round(elasticity, 3),
        "units_baseline": round(old_units),
        "units_projected": round(old_units * units_multiplier),
    }
    return result


def simulate_cost_change(records, product, delta_pct):
    """Re-run history with what one product costs you moved by delta_pct."""
    _assert_product(records, product)
    cost_multiplier = 1 + delta_pct

    def project(record):
        if record.product != product:
            return record.units_sold, record.unit_price, record.unit_cost
        return record.units_sold, record.unit_price, record.unit_cost * cost_multiplier

    baseline, projected, series = _replay(records, project)
    return simulation_result(
        baseline,
        projected,
        series,
        # No behavioural guess is involved -- this is arithmetic on your own
        # numbers, which is why it comes back at high confidence.
        "direct_recompute",
        [
            "Your selling price and the volumes you sell stay as they were.",
            f"Only {product}'s cost changes, by {delta_pct * 100:+.1f}%.",
            "Revenue is unchanged, so the whole effect lands on profit.",
        ],
        "high",
    )


def simulate_make_vs_buy(records, item, in_house_unit_cost, setup_cost, current_outsourced_unit_cost):
    """Compare buying something in against making it yourself.

    Asks for what it genuinely cannot know (what in-house production would
    cost) and reads what it can from the business's own records.
    """
    if in_house_unit_cost is None:
        raise MissingParams(
            ["in_house_unit_cost"],
            "I need to know what one unit would cost you to make in-house before I can compare.",
        )

    products = {r.product for r in records}
    inferred = False
    if current_outsourced_unit_cost is None:
        if item in products:
            rows = [r for r in records if r.product == item]
            units = sum(r.units_sold for r in rows)
            current_outsourced_unit_cost = (sum(r.cost for r in rows) / units) if units else None
            inferred = True
        if current_outsourced_unit_cost is None:
            raise MissingParams(
                ["current_outsourced_unit_cost"],
                f"I could not find {item!r} in your data, so I need what you pay for it today.",
            )

    affected = [r for r in records if r.product == item] if item in products else list(records)
    saving_per_unit = current_outsourced_unit_cost - in_house_unit_cost
    setup = setup_cost or 0.0

    # BusinessRecord defines __eq__, so instances are unhashable -- identity is
    # what distinguishes the affected rows here.
    affected_ids = {id(r) for r in affected}

    def project(record):
        if id(record) in affected_ids:
            return record.units_sold, record.unit_price, record.unit_cost - saving_per_unit
        return record.units_sold, record.unit_price, record.unit_cost

    baseline, projected, series = _replay(records, project)

    # The setup cost is real money spent once, so it comes off the first month
    # rather than being spread where it would be easy to miss.
    if setup and series["projected_y"]:
        series["projected_y"][0] = round(series["projected_y"][0] - setup, 2)
        projected = Totals(
            revenue=projected.revenue,
            profit=projected.profit - setup,
            margin=((projected.profit - setup) / projected.revenue * 100) if projected.revenue else 0.0,
        )

    units = sum(r.units_sold for r in affected)
    assumptions = [
        f"Making it yourself costs {in_house_unit_cost:.2f} a unit, the figure you gave me.",
        (f"You currently pay {current_outsourced_unit_cost:.2f} a unit, averaged from your own records."
         if inferred else
         f"You currently pay {current_outsourced_unit_cost:.2f} a unit, the figure you gave me."),
        "The volumes you sell do not change -- only what each unit costs you.",
    ]
    confidence = "medium"
    if setup:
        assumptions.append(f"A one-off setup cost of {setup:.0f}, taken in the first month.")
    else:
        assumptions.append("No setup, equipment or labour cost is included, because I do not know it.")
        confidence = "low"

    result = simulation_result(baseline, projected, series, "stated_costs", assumptions, confidence)
    result["detail"] = {
        "item": item,
        "saving_per_unit": round(saving_per_unit, 2),
        "units_affected": round(units),
        "breakeven_units": round(setup / saving_per_unit) if setup and saving_per_unit > 0 else None,
    }
    return result


# --------------------------------------------------------------------- replay --

def _replay(records, project):
    """Re-run every record through `project` and total it up, by month.

    Returns (baseline totals, projected totals, series). The series reports
    whichever of revenue or profit the change actually moved most, so the chart
    shows the measure worth looking at.
    """
    baseline = totals_of(records)

    months = months_between(records)
    base_by_month = {m: {"revenue": 0.0, "profit": 0.0} for m in months}
    proj_by_month = {m: {"revenue": 0.0, "profit": 0.0} for m in months}
    proj_revenue = proj_cost = 0.0

    for record in records:
        units, price, cost = project(record)
        revenue, spend = units * price, units * cost
        proj_revenue += revenue
        proj_cost += spend
        base_by_month[record.month]["revenue"] += record.revenue
        base_by_month[record.month]["profit"] += record.profit
        proj_by_month[record.month]["revenue"] += revenue
        proj_by_month[record.month]["profit"] += revenue - spend

    proj_profit = proj_revenue - proj_cost
    projected = Totals(
        revenue=proj_revenue,
        profit=proj_profit,
        margin=(proj_profit / proj_revenue * 100) if proj_revenue else 0.0,
    )

    metric = _metric_that_moved(baseline, projected)
    series = {
        "metric": metric,
        "x": months,
        "baseline_y": [round(base_by_month[m][metric], 2) for m in months],
        "projected_y": [round(proj_by_month[m][metric], 2) for m in months],
    }
    return baseline, projected, series


def _metric_that_moved(baseline: Totals, projected: Totals) -> str:
    def shift(before, after):
        return abs(after - before) / abs(before) if before else 0.0

    return "profit" if shift(baseline.profit, projected.profit) >= shift(
        baseline.revenue, projected.revenue
    ) else "revenue"


# ------------------------------------------------------------------- plumbing --

def _assert_product(records, product):
    products = sorted({r.product for r in records})
    if product not in products:
        raise ApiError(
            404,
            f"I could not find {product!r} in your data. You sell: {', '.join(products[:8])}.",
        )


def _require(params, key):
    if params.get(key) in (None, ""):
        raise MissingParams([key], f"I need {key.replace('_', ' ')} to run this.")
    return params[key]


def _as_fraction(value) -> float:
    """Accept 10, "10%" or 0.1 and return 0.1.

    Anything at or beyond +/-1 is read as a percentage, because nobody means a
    100x price rise when they type 10.
    """
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    number = float(value)
    return number / 100 if abs(number) >= 1 else number


def _optional_float(value):
    if value in (None, ""):
        return None
    return float(value)
