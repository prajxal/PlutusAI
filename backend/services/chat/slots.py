"""
The details a question carries: which product, how much, which month.

None of this goes near a model. A product name is matched against the list we
already hold for that business, and a magnitude is a number with a direction --
both are problems code solves exactly.
"""
import re
from dataclasses import dataclass

DOWNWARD = re.compile(r"\b(cut|drop|lower|reduce|discount|down|less)\b", re.I)
PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|per ?cent)", re.I)
BARE_NUMBER = re.compile(r"\b(-?\d+(?:\.\d+)?)\b")
MONEY = re.compile(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)", re.I)
SETUP = re.compile(r"setup[^0-9]{0,20}(\d+(?:\.\d+)?)", re.I)
OWN_ITEM = re.compile(r"\bmy own ([a-z ]{3,25}?)\b(?: instead|\?|$|,)", re.I)

MONTHS = "january february march april may june july august september october november december".split()


@dataclass(frozen=True)
class Slots:
    product: str | None = None
    item: str | None = None
    delta_pct: float | None = None
    in_house_unit_cost: float | None = None
    setup_cost: float | None = None
    month: int | None = None


def extract(message: str, products: list) -> Slots:
    return Slots(
        product=find_product(message, products),
        item=find_product(message, products) or find_item(message),
        delta_pct=find_percent(message),
        in_house_unit_cost=find_money(message),
        setup_cost=find_setup(message),
        month=find_month(message),
    )


def find_product(message: str, products: list):
    """Match what the owner called it to what their file calls it.

    Longest first, so "Sourdough loaf" wins over a product merely called
    "Sourdough"; then a word-level match so "sourdough" alone still lands.
    """
    lowered = message.lower()
    for product in sorted(products, key=len, reverse=True):
        if product.lower() in lowered:
            return product
    for product in sorted(products, key=len, reverse=True):
        for word in product.lower().split():
            if len(word) > 3 and re.search(rf"\b{re.escape(word)}\b", lowered):
                return product
    return None


def find_item(message: str):
    match = OWN_ITEM.search(message)
    return match.group(1).strip() if match else None


def find_percent(message: str):
    """Read 10, "10%" or "ten percent" as 0.10, and honour the direction word.

    A bare number above 90 is not a percentage anyone means, so it is ignored
    rather than turned into a 400% price rise.
    """
    match = PERCENT.search(message)
    if match:
        value = float(match.group(1)) / 100
    else:
        plausible = [n for n in (float(x) for x in BARE_NUMBER.findall(message)) if 0 < abs(n) <= 90]
        if not plausible:
            return None
        value = plausible[0] / 100
    return -abs(value) if DOWNWARD.search(message) else abs(value)


def find_money(message: str):
    match = MONEY.search(message)
    return float(match.group(1)) if match else None


def find_setup(message: str):
    match = SETUP.search(message)
    return float(match.group(1)) if match else None


def find_month(message: str):
    lowered = message.lower()
    abbreviations = set(re.findall(r"\b[a-z]{3}\b", lowered))
    for index, name in enumerate(MONTHS, start=1):
        if name in lowered or name[:3] in abbreviations:
            return index
    return None


def month_name(date: str) -> str:
    year, mon = date.split("-")
    return f"{MONTHS[int(mon) - 1].capitalize()} {year}"
