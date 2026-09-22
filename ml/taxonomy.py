"""The label space, defined once.

This file is deliberately standalone -- it imports nothing from `backend/`, so
training can run on a machine that has only this directory. The price of that
is a second copy of the label lists, and `tests/test_taxonomy.py` exists to
make sure the copy never drifts from `backend/services/chat/intent.py`.
"""

# Order is the label order. Appending is safe; reordering invalidates every
# checkpoint trained before the change.
INTENTS = (
    "insight",
    "price_change",
    "cost_change",
    "make_vs_buy",
    "list_scenarios",
    "unclear",
)

# The metric head. "none" is a real class, not a mask: most intents have no
# metric, and the model should say so rather than be asked only sometimes.
METRICS = ("revenue", "margin", "units_sold", "cost", "none")

INTENT_TO_ID = {name: i for i, name in enumerate(INTENTS)}
METRIC_TO_ID = {name: i for i, name in enumerate(METRICS)}
ID_TO_INTENT = {i: name for name, i in INTENT_TO_ID.items()}
ID_TO_METRIC = {i: name for name, i in METRIC_TO_ID.items()}

BASE_MODEL = "xlm-roberta-base"
MAX_LENGTH = 64


def metric_label(metric) -> str:
    """None and "none" are the same thing to the model."""
    return metric if metric in METRICS and metric is not None else "none"


def metric_value(label: str):
    """...and the same thing as None on the way back out."""
    return None if label == "none" else label
