"""
Generates a realistic sample sales/inventory CSV for demo/testing, so the
whole team can develop against consistent data without waiting on a real
business dataset.

The data is deliberately not clean. It carries the things the rest of the
system is supposed to find:

  * the sourdough loaf changes price three times, which is what lets the
    simulation engine measure elasticity from history instead of assuming it;
  * the butter croissant's cost jumps in May while its price holds, which is
    the margin drop the dashboard should flag;
  * filter coffee spikes in late June;
  * the headers are a shopkeeper's headers, not our schema, so ingestion's
    column mapping has something to map;
  * a handful of rows are malformed, so the rejected-row path is exercised.

Usage:  python3 scripts/seed_sample_data.py [out.csv]
"""
import csv
import random
import sys
from datetime import date, timedelta

START = date(2025, 9, 1)
END = date(2026, 8, 31)
OUTLETS = ["MG Road", "Indiranagar"]

# Sourdough's price history -- three changes across the year. Demand responds
# with a true elasticity of about -0.9, which the engine has to recover.
SOURDOUGH_PRICES = [
    (date(2025, 9, 1), 165.0),
    (date(2025, 12, 1), 185.0),
    (date(2026, 3, 1), 172.0),
    (date(2026, 6, 15), 195.0),
]
TRUE_ELASTICITY = -0.9

PRODUCTS = {
    "Masala bun":       {"price": 25.0,  "cost": 9.5,   "units": 128},
    "Veg puff":         {"price": 30.0,  "cost": 12.0,  "units": 110},
    "Filter coffee":    {"price": 45.0,  "cost": 14.0,  "units": 86},
    "Butter croissant": {"price": 90.0,  "cost": 34.0,  "units": 51},
    "Sourdough loaf":   {"price": 165.0, "cost": 62.0,  "units": 20},
}

# Festive months trade harder; January is quiet.
SEASON = {9: 1.00, 10: 1.14, 11: 1.08, 12: 1.21, 1: 0.92, 2: 0.96,
          3: 1.02, 4: 1.05, 5: 1.00, 6: 1.07, 7: 1.02, 8: 1.05}


def sourdough_price(day: date) -> float:
    price = SOURDOUGH_PRICES[0][1]
    for starts, value in SOURDOUGH_PRICES:
        if day >= starts:
            price = value
    return price


def rows():
    rng = random.Random(20260922)  # fixed seed: everyone gets the same data
    day = START
    while day <= END:
        for product, base in PRODUCTS.items():
            price, cost = base["price"], base["cost"]
            units = base["units"] * SEASON[day.month]

            if product == "Sourdough loaf":
                price = sourdough_price(day)
                # Constant-elasticity demand against the opening price.
                units *= (price / SOURDOUGH_PRICES[0][1]) ** TRUE_ELASTICITY

            if product == "Butter croissant" and day >= date(2026, 5, 1):
                cost = 41.0  # supplier put butter up; the price never followed

            if product == "Filter coffee" and date(2026, 6, 10) <= day <= date(2026, 6, 30):
                units *= 1.22  # a spike worth noticing

            units *= 1 + rng.uniform(-0.12, 0.12)          # day-to-day noise
            units *= 1.18 if day.weekday() >= 5 else 1.0   # weekends are busier

            for outlet in OUTLETS:
                share = 0.58 if outlet == "MG Road" else 0.42
                sold = round(units * share)
                if sold <= 0:
                    continue
                yield {
                    "Date": day.strftime("%d/%m/%Y"),   # day-first, as people write it
                    "Item": product,
                    "Qty Sold": sold,
                    "Selling Price": f"{price:.2f}",
                    "Cost Price": f"{cost:.2f}",
                    "Outlet": outlet,
                }
        day += timedelta(days=1)


FIELDNAMES = ["Date", "Item", "Qty Sold", "Selling Price", "Cost Price", "Outlet"]


def build_rows():
    """Every row, including the ones ingestion is meant to reject and report."""
    all_rows = list(rows())
    all_rows.insert(40, {"Date": "31/02/2026", "Item": "Veg puff", "Qty Sold": 12,
                         "Selling Price": "30.00", "Cost Price": "12.00", "Outlet": "MG Road"})
    all_rows.insert(900, {"Date": "14/01/2026", "Item": "Masala bun", "Qty Sold": "many",
                          "Selling Price": "25.00", "Cost Price": "9.50", "Outlet": "MG Road"})
    all_rows.insert(1400, {"Date": "", "Item": "Filter coffee", "Qty Sold": 40,
                           "Selling Price": "45.00", "Cost Price": "14.00", "Outlet": "Indiranagar"})
    return all_rows


def csv_text() -> str:
    """The same CSV as a string, for callers that do not want a file."""
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(build_rows())
    return buffer.getvalue()


def main(path="sample_sales.csv"):
    all_rows = build_rows()

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {path} "
          f"({START:%b %Y} to {END:%b %Y}, {len(PRODUCTS)} products, 3 rows deliberately broken)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_sales.csv")
