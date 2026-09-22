"""The fine-tuned classifier, reached over HTTP.

`intent.py` has imported this module since the chat pipeline was written; until
now the file did not exist, so setting PLUTUS_INTENT_MODEL_URL raised
ImportError on the first chat message. This is that seam filled in.

Two rules govern everything here:

1. **The model is never trusted to be up.** Any failure -- connection refused,
   timeout, a 500, a body that does not parse, a label not in the taxonomy --
   falls back to the deterministic classifier and answers the owner anyway. A
   hosted endpoint going down must degrade the quality of the answer, never
   the availability of the product.
2. **The model is sent the message and nothing else.** No business_id, no
   product names, no figures. Whatever runs at the other end cannot leak a
   customer's numbers because it is never given any.
"""
import json
import urllib.error
import urllib.request

from shared import config
from shared.log import logger

from services.chat.intent import INTENTS, METRICS, Intent, RegexIntentClassifier


class ModelIntentClassifier:
    """Calls the endpoint; falls back to the regexes on any problem at all."""

    def __init__(self, url: str, token: str | None = None, timeout: float | None = None):
        self.url = url
        self.token = token if token is not None else config.INTENT_MODEL_TOKEN
        self.timeout = timeout if timeout is not None else config.INTENT_MODEL_TIMEOUT
        self.fallback = RegexIntentClassifier()

    def classify(self, message: str) -> Intent:
        try:
            payload = self._call(message)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warn("Intent model unreachable, using the rules", error=str(exc))
            return self._fall_back(message)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warn("Intent model returned something unreadable", error=str(exc))
            return self._fall_back(message)

        intent = self._read(payload)
        if intent is None:
            logger.warn("Intent model returned a label outside the taxonomy",
                        payload=str(payload)[:200])
            return self._fall_back(message)
        return intent

    # --- the wire ------------------------------------------------------------

    def _call(self, message: str) -> dict:
        body = json.dumps({"message": message}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _read(self, payload) -> Intent | None:
        """Validate before believing. A label we do not recognise is a bug at
        the other end, and guessing which of ours it meant would be worse than
        falling back."""
        if not isinstance(payload, dict):
            return None
        name = payload.get("intent")
        if name not in INTENTS:
            return None

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None
        confidence = min(max(confidence, 0.0), 1.0)

        metric = payload.get("metric")
        if metric is not None and metric not in METRICS:
            metric = None
        # A metric is only meaningful on an insight question.
        if name != "insight":
            metric = None

        return Intent(name=name, confidence=confidence, metric=metric, source="model")

    def _fall_back(self, message: str) -> Intent:
        """The rules answer, and say so -- `intent.source` reaches the owner's
        reply, so a degraded answer is visible rather than silent."""
        intent = self.fallback.classify(message)
        return Intent(name=intent.name, confidence=intent.confidence,
                      metric=intent.metric, source="rules_fallback")
