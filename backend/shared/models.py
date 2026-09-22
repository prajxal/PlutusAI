"""
Shared type/schema definitions matching docs/implementation-plan.md contracts.
Keep these in sync with the JSON schemas in the plan doc -- this file is the
single source of truth other modules should import from, not re-declare.

NOTE: business_id is derived from the verified session server-side; it is never
taken from the client, and the intent classifier never sees it at all.
"""
from dataclasses import dataclass, field, asdict
from datetime import date as _date, datetime

RECORD_FIELDS = ("date", "product", "units_sold", "unit_price", "unit_cost")
CONFIDENCE_LEVELS = ("high", "medium", "low")
METRICS = ("revenue", "margin", "units_sold", "cost", "profit")


@dataclass
class BusinessRecord:
    """One product's trading on one day (optionally split by a further
    dimension such as store or channel -- see plan Section 4)."""

    date: str  # YYYY-MM-DD
    product: str
    units_sold: float
    unit_price: float
    unit_cost: float
    extras: dict = field(default_factory=dict)

    @property
    def revenue(self) -> float:
        return self.units_sold * self.unit_price

    @property
    def cost(self) -> float:
        return self.units_sold * self.unit_cost

    @property
    def profit(self) -> float:
        return self.revenue - self.cost

    @property
    def month(self) -> str:
        return self.date[:7]

    @property
    def dimension(self) -> str:
        """The extra key that keeps two rows for the same date+product from
        overwriting each other in DynamoDB (plan Section 4)."""
        parts = [str(self.extras[k]) for k in sorted(self.extras) if self.extras[k] not in (None, "")]
        return "|".join(parts)

    def to_item(self) -> dict:
        return {**asdict(self)}

    @classmethod
    def from_item(cls, item: dict) -> "BusinessRecord":
        return cls(
            date=item["date"],
            product=item["product"],
            units_sold=float(item["units_sold"]),
            unit_price=float(item["unit_price"]),
            unit_cost=float(item["unit_cost"]),
            extras=item.get("extras") or {},
        )


@dataclass
class Totals:
    revenue: float = 0.0
    margin: float = 0.0
    profit: float = 0.0

    def to_dict(self) -> dict:
        return {
            "revenue": round(self.revenue, 2),
            "margin": round(self.margin, 2),
            "profit": round(self.profit, 2),
        }


def totals_of(records) -> Totals:
    """Revenue, profit and gross margin over any set of records.

    margin is a percentage, so a zero-revenue set reports 0 rather than
    dividing by zero.
    """
    revenue = sum(r.revenue for r in records)
    cost = sum(r.cost for r in records)
    profit = revenue - cost
    margin = (profit / revenue * 100) if revenue else 0.0
    return Totals(revenue=revenue, margin=margin, profit=profit)


def months_between(records) -> list:
    return sorted({r.month for r in records})


def parse_date(value) -> str:
    """Accept the date formats a real spreadsheet produces; return ISO.

    Day-first is tried before month-first because the target users are in
    India, where 03/04/2026 means 3 April.
    """
    if isinstance(value, (_date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        raise ValueError("empty date")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {text!r}")


def parse_number(value, field_name: str) -> float:
    """Tolerate the currency symbols, commas and spaces people actually type."""
    if value is None:
        raise ValueError(f"missing {field_name}")
    text = str(value).strip().replace(",", "").replace("₹", "").replace("$", "").replace(" ", "")
    if text in ("", "-", "NA", "N/A", "null", "None"):
        raise ValueError(f"missing {field_name}")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{field_name} {value!r} is not a number")


# SimulationResult (Module D output) -- kept as a plain dict builder so the
# JSON shape in the plan doc and the shape on the wire cannot drift apart.
def simulation_result(baseline: Totals, projected: Totals, series: dict, method: str,
                      assumptions: list, confidence: str) -> dict:
    assert confidence in CONFIDENCE_LEVELS, f"bad confidence {confidence}"
    return {
        "baseline": baseline.to_dict(),
        "projected": projected.to_dict(),
        "series": series,
        "method": method,
        "assumptions": assumptions,
        "confidence": confidence,
    }
