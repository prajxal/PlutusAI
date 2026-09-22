"""
What the owner is asking for.

This is the one place a learned model will live (Phase 6). Everything else in
the chat pipeline is deterministic, so this module is deliberately narrow: it
turns a sentence into an intent label and nothing else. It is handed the raw
message and no business data whatsoever -- not the products, not the figures,
not an id -- so whatever runs here cannot leak a customer's numbers.

Slot filling stays out of the model on purpose. "Which product" is a match
against a list we already have, and "how much" is a number with a direction;
both are solved exactly by code, and a model could only make them worse.
"""
import re
from dataclasses import dataclass
from typing import Protocol

from shared import config
from shared.log import logger

INTENTS = ("insight", "price_change", "cost_change", "make_vs_buy", "list_scenarios", "unclear")
METRICS = ("revenue", "margin", "units_sold", "cost")

WHAT_IF = re.compile(r"\b(what if|what would|suppose|if i|if we)\b", re.I)
MAKE_VS_BUY = re.compile(
    r"\b(in[- ]house|make (my|our) own|bake (my|our) own|instead of buying|make vs buy)\b", re.I)
COST_WORD = re.compile(r"\b(cost|costs|supplier|cheaper)\b", re.I)
PRICE_WORD = re.compile(
    r"\b(price|prices|charge|raise|increase|hike|discount|cut|drop|lower|reduce)\b", re.I)
SAVED = re.compile(r"\b(saved|previous|earlier) (scenarios?|what[- ]ifs?)\b", re.I)
PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|per ?cent)", re.I)

METRIC_WORDS = [
    ("margin", re.compile(r"\bmargins?\b", re.I)),
    ("revenue", re.compile(r"\b(revenue|sales|turnover|takings)\b", re.I)),
    ("units_sold", re.compile(r"\b(units?|volume|how many|sold)\b", re.I)),
    ("cost", re.compile(r"\bcosts?\b", re.I)),
]


@dataclass(frozen=True)
class Intent:
    name: str
    confidence: float
    metric: str | None = None
    source: str = "rules"

    @property
    def is_scenario(self) -> bool:
        return self.name in ("price_change", "cost_change", "make_vs_buy")

    @property
    def trusted(self) -> bool:
        return self.confidence >= config.INTENT_MIN_CONFIDENCE


class IntentClassifier(Protocol):
    def classify(self, message: str) -> Intent: ...


class RegexIntentClassifier:
    """The deterministic classifier.

    It is exact on the phrasings it knows and blind to everything else, which
    is the ceiling a fine-tuned model has to beat to be worth hosting. It stays
    in the codebase permanently as the fallback for when that model is
    unreachable.
    """

    def classify(self, message: str) -> Intent:
        if MAKE_VS_BUY.search(message):
            return Intent("make_vs_buy", 0.9)
        if SAVED.search(message):
            return Intent("list_scenarios", 0.9)

        if WHAT_IF.search(message) or PERCENT.search(message):
            if COST_WORD.search(message) and not PRICE_WORD.search(message):
                return Intent("cost_change", 0.9)
            if PRICE_WORD.search(message):
                return Intent("price_change", 0.9)

        metric = next((name for name, pattern in METRIC_WORDS if pattern.search(message)), None)
        if metric:
            return Intent("insight", 0.7, metric=metric)
        return Intent("unclear", 0.0)


_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """The model when one is configured and reachable, the regexes otherwise."""
    global _classifier
    if _classifier is None:
        if config.INTENT_MODEL_URL:
            from services.chat.model_intent import ModelIntentClassifier

            _classifier = ModelIntentClassifier(config.INTENT_MODEL_URL)
            logger.info("Using the fine-tuned intent model", url=config.INTENT_MODEL_URL)
        else:
            _classifier = RegexIntentClassifier()
            logger.info("Using the deterministic intent classifier")
    return _classifier


def reset_classifier_for_tests(classifier=None):
    global _classifier
    _classifier = classifier
