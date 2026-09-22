"""Load a trained checkpoint and classify a message.

Used by `ml/evaluate.py` and by `ml/serve.py`. It returns the same shape the
backend's classifiers return, so the two are interchangeable at the call site.
"""
import json
import os
import sys
from dataclasses import dataclass

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from model import TwoHeadIntentModel, pick_device  # noqa: E402
from taxonomy import ID_TO_INTENT, ID_TO_METRIC, metric_value  # noqa: E402


@dataclass(frozen=True)
class Prediction:
    name: str
    confidence: float
    metric: str | None = None
    source: str = "model"


class LocalIntentModel:
    def __init__(self, path: str, device=None):
        with open(os.path.join(path, "config.json"), encoding="utf-8") as fh:
            self.config = json.load(fh)
        from transformers import AutoTokenizer

        self.device = device or pick_device()
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = TwoHeadIntentModel(self.config["base_model"])
        self.model.load_state_dict(
            torch.load(os.path.join(path, "model.pt"), map_location="cpu")
        )
        self.model.to(self.device).eval()

    @torch.no_grad()
    def classify(self, message: str) -> Prediction:
        enc = self.tokenizer(message, truncation=True,
                             max_length=self.config["max_length"],
                             padding="max_length", return_tensors="pt")
        logits_i, logits_m = self.model(enc["input_ids"].to(self.device),
                                        enc["attention_mask"].to(self.device))
        probs = logits_i.softmax(-1)[0]
        idx = int(probs.argmax())
        metric = ID_TO_METRIC[int(logits_m.softmax(-1)[0].argmax())]
        name = ID_TO_INTENT[idx]
        # A metric only means anything on an insight question.
        return Prediction(name=name, confidence=float(probs[idx]),
                          metric=metric_value(metric) if name == "insight" else None)
