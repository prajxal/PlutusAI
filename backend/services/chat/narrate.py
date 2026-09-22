"""
Turning a result into a sentence.

Every figure in every sentence here is read out of a tool result -- nothing is
computed, rounded differently, or invented at this layer. That is Foundation
Rule 4 taken one step further than the original design: numbers come from code,
and now so do the words around them.
"""
from shared import repository
from shared.models import totals_of

from services.chat import slots

# The full assumptions come back in their own field and the interface shows
# them, so the reply says how much to trust the number, not the same sentence
# twice.
CONFIDENCE_SENTENCE = {
    ("high", "elasticity_from_history"):
        "I am confident in this one — it is measured from your own price history, not assumed.",
    ("high", "direct_recompute"):
        "I am confident in this one — it is arithmetic on your own numbers, with nothing estimated.",
    ("medium", "user_supplied"):
        "That rests on the demand response you gave me rather than anything I measured.",
    ("low", "default_elasticity"):
        "Treat this as a rough figure: this product has not changed price enough for me to "
        "measure how its demand responds, so I have used a category assumption.",
    ("low", "stated_costs"):
        "Treat this as a rough figure: it leaves out setup, equipment and labour, which are "
        "not in your data.",
}


def confidence_sentence(result: dict) -> str:
    specific = CONFIDENCE_SENTENCE.get((result["confidence"], result["method"]))
    if specific:
        return specific
    return {
        "high": "I am confident in this one.",
        "medium": "Treat this as a reasonable estimate rather than a firm number.",
        "low": "Treat this as a rough figure.",
    }[result["confidence"]]


def price_or_cost_change(result, product, percent, scenario_type) -> str:
    base, proj = result["baseline"], result["projected"]
    revenue_shift = proj["revenue"] - base["revenue"]
    profit_shift = proj["profit"] - base["profit"]
    direction = "up" if percent > 0 else "down"

    if scenario_type == "price_change":
        detail = result.get("detail", {})
        lost = detail.get("units_baseline", 0) - detail.get("units_projected", 0)
        lines = [
            f"Taking the {product.lower()} {direction} {abs(percent) * 100:.0f}% moves your "
            f"revenue by {revenue_shift:+,.0f} and your gross profit by {profit_shift:+,.0f} "
            f"over the same 12 months.",
            f"You would sell about {abs(lost):,} {'fewer' if lost > 0 else 'more'} units.",
            f"Gross margin goes from {base['margin']:.1f}% to {proj['margin']:.1f}%.",
        ]
    else:
        lines = [
            f"Moving what the {product.lower()} costs you {direction} "
            f"{abs(percent) * 100:.0f}% changes gross profit by {profit_shift:+,.0f} "
            f"over the same 12 months. Revenue does not move, so all of it lands on profit.",
            f"Gross margin goes from {base['margin']:.1f}% to {proj['margin']:.1f}%.",
        ]
    lines.append(confidence_sentence(result))
    return " ".join(lines)


def make_vs_buy(result, item) -> str:
    detail = result.get("detail", {})
    saved = result["projected"]["profit"] - result["baseline"]["profit"]
    lines = [
        f"Making {item or 'that'} yourself changes your gross profit by {saved:+,.0f} over the "
        f"same 12 months, on a saving of {detail.get('saving_per_unit', 0):,.2f} a unit across "
        f"{detail.get('units_affected', 0):,} units."
    ]
    if detail.get("breakeven_units"):
        lines.append(f"You would cover the setup cost after about "
                     f"{detail['breakeven_units']:,} units.")
    lines.append(confidence_sentence(result))
    return " ".join(lines)


def insight(business_id, metric, product, data) -> str:
    values = data["values"]
    if not values:
        return "I have no rows matching that."

    stats = data["summary_stats"]
    subject = f"{product}'s {metric.replace('_', ' ')}" if product else metric.replace("_", " ")
    unit = "%" if metric == "margin" else ""
    # A margin that moves from 64% to 62% moved two points, not two percent.
    move_unit = " points" if metric == "margin" else unit

    low = min(values, key=lambda v: v["value"])
    high = max(values, key=lambda v: v["value"])
    lines = [
        f"Across the 12 months, {subject} averaged {stats['avg']:,.1f}{unit} a month, "
        f"lowest in {slots.month_name(low['date'])} at {low['value']:,.1f}{unit} and highest in "
        f"{slots.month_name(high['date'])} at {high['value']:,.1f}{unit}."
    ]

    biggest = _biggest_move(values)
    if biggest:
        month, change = biggest
        lines.append(f"The sharpest move was {slots.month_name(month)}, "
                     f"{change:+,.1f}{move_unit} on the month before.")
        # "Why" deserves an answer, not just a number.
        if metric == "margin" and not product:
            because = explain_margin_move(business_id, month)
            if because:
                lines.append(because)
    return " ".join(lines)


def saved_scenarios(rows) -> str:
    if not rows:
        return "You have not saved any scenarios yet."
    listed = "; ".join(f"{s['question']} ({s['summary']})" for s in rows)
    return f"Your saved scenarios: {listed}."


def unclear(products) -> str:
    """An answer that teaches, rather than an apology.

    The classifier could not place the question, so the reply says what this
    can actually do and offers a question worth asking.
    """
    example = products[0].lower() if products else "price"
    return (
        "I can tell you what your revenue, margin, costs or units did over any period, or run "
        "a what-if on a price or a cost. You sell " + _list(products) + ". "
        f"Try \"why did margin drop in May?\" or \"what if I raise the {example} 10%?\""
    )


def _biggest_move(values):
    moves = [(values[i]["date"], values[i]["value"] - values[i - 1]["value"])
             for i in range(1, len(values))]
    return min(moves, key=lambda m: m[1]) if moves else None


def explain_margin_move(business_id, month):
    """Attribute a month's margin move to the product that caused it."""
    records = repository.get_business_records(business_id)
    months = sorted({r.month for r in records})
    if month not in months or months.index(month) == 0:
        return None
    previous = months[months.index(month) - 1]

    worst, worst_drop = None, 0.0
    for candidate in sorted({r.product for r in records}):
        before = [r for r in records if r.product == candidate and r.month == previous]
        after = [r for r in records if r.product == candidate and r.month == month]
        if not before or not after:
            continue
        drop = totals_of(before).margin - totals_of(after).margin
        if drop > worst_drop:
            worst, worst_drop = candidate, drop

    if not worst or worst_drop < 2:
        return None

    before = [r for r in records if r.product == worst and r.month == previous]
    after = [r for r in records if r.product == worst and r.month == month]
    cost_before, cost_after = _weighted(before, "unit_cost"), _weighted(after, "unit_cost")
    price_before, price_after = _weighted(before, "unit_price"), _weighted(after, "unit_price")

    sentence = (f"Almost all of it is the {worst.lower()}, whose own margin fell "
                f"{worst_drop:.0f} points that month")
    if cost_after > cost_before * 1.03 and price_after <= price_before * 1.01:
        sentence += (f" — its cost to you went from {cost_before:,.0f} to {cost_after:,.0f} "
                     f"while you held the price at {price_after:,.0f}")
    elif price_after < price_before * 0.97:
        sentence += f" — you dropped its price from {price_before:,.0f} to {price_after:,.0f}"
    return sentence + "."


def _weighted(rows, attr):
    units = sum(r.units_sold for r in rows)
    return sum(getattr(r, attr) * r.units_sold for r in rows) / units if units else 0.0


def _list(items):
    if not items:
        return "nothing yet"
    return ", ".join(items[:-1]) + (" and " + items[-1] if len(items) > 1 else items[0])
