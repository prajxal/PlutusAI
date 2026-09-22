"""One encoder, two heads.

Intent and metric are the same question asked twice ("what is being asked for"
and "about which figure"), so they share an encoder and disagree only in the
last linear layer. Two separate models would cost twice the memory and twice
the latency to learn the same sentence representation.
"""
import torch
import torch.nn as nn
from transformers import AutoConfig, AutoModel

from taxonomy import INTENTS, METRICS


class TwoHeadIntentModel(nn.Module):
    def __init__(self, base_model: str, dropout: float = 0.1):
        super().__init__()
        self.base_model = base_model
        self.encoder = AutoModel.from_pretrained(base_model)
        hidden = AutoConfig.from_pretrained(base_model).hidden_size
        self.dropout = nn.Dropout(dropout)
        self.intent_head = nn.Linear(hidden, len(INTENTS))
        self.metric_head = nn.Linear(hidden, len(METRICS))

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # Mean-pool over real tokens. XLM-R has no trained pooler, so <s> alone
        # is a worse sentence vector than the average of what is actually there.
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (out.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        pooled = self.dropout(pooled)
        return self.intent_head(pooled), self.metric_head(pooled)


def pick_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")
