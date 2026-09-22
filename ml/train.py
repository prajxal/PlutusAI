#!/usr/bin/env python3
"""Fine-tune the two-head intent model.

    python3 ml/train.py                      # trains on ml/data/train.jsonl
    python3 ml/train.py --epochs 5 --lr 2e-5

Runs on Apple Silicon (MPS), CUDA or CPU -- whichever is there. The plan
assumed a Colab T4; this dataset is small enough that a laptop GPU is minutes,
so there is no reason to leave the machine.

A plain loop rather than transformers.Trainer: two heads and a weighted loss
are three lines here and a subclass plus a collator there, and this way the
training step is readable by someone who has never used the library.
"""
import argparse
import json
import os
import sys
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from model import TwoHeadIntentModel, pick_device  # noqa: E402
from taxonomy import (BASE_MODEL, INTENT_TO_ID, INTENTS, MAX_LENGTH,  # noqa: E402
                      METRIC_TO_ID, METRICS, metric_label)


class IntentDataset(Dataset):
    def __init__(self, path, tokenizer):
        with open(path, encoding="utf-8") as fh:
            self.rows = [json.loads(line) for line in fh if line.strip()]
        self.tok = tokenizer

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        enc = self.tok(row["message"], truncation=True, max_length=MAX_LENGTH,
                       padding="max_length", return_tensors="pt")
        return {
            "input_ids": enc["input_ids"][0],
            "attention_mask": enc["attention_mask"][0],
            "intent": torch.tensor(INTENT_TO_ID[row["intent"]]),
            "metric": torch.tensor(METRIC_TO_ID[metric_label(row["metric"])]),
        }


def class_weights(rows, label_of, mapping):
    """Inverse-frequency weights.

    `unclear` has a fraction of the examples the slot-heavy intents do, because
    there are only so many ways to type "hello". Left alone the model would
    learn to never predict it, and macro-F1 counts that class as much as any
    other.
    """
    counts = torch.zeros(len(mapping))
    for row in rows:
        counts[mapping[label_of(row)]] += 1
    weights = counts.sum() / (len(mapping) * counts.clamp(min=1))
    return weights


@torch.no_grad()
def evaluate_split(model, loader, device):
    model.eval()
    intent_ok = metric_ok = total = 0
    for batch in loader:
        logits_i, logits_m = model(batch["input_ids"].to(device),
                                   batch["attention_mask"].to(device))
        intent_ok += (logits_i.argmax(-1).cpu() == batch["intent"]).sum().item()
        metric_ok += (logits_m.argmax(-1).cpu() == batch["metric"]).sum().item()
        total += len(batch["intent"])
    model.train()
    return intent_ok / total, metric_ok / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=os.path.join(HERE, "data", "train.jsonl"))
    ap.add_argument("--val", default=os.path.join(HERE, "data", "val.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "artifacts"))
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    device = pick_device()
    print(f"device: {device}   base model: {args.base_model}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    train_ds = IntentDataset(args.train, tokenizer)
    val_ds = IntentDataset(args.val, tokenizer)
    print(f"train {len(train_ds)}   val {len(val_ds)}")

    train_dl = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=args.batch_size)

    model = TwoHeadIntentModel(args.base_model).to(device)
    w_intent = class_weights(train_ds.rows, lambda r: r["intent"], INTENT_TO_ID).to(device)
    w_metric = class_weights(train_ds.rows, lambda r: metric_label(r["metric"]),
                             METRIC_TO_ID).to(device)
    loss_intent = nn.CrossEntropyLoss(weight=w_intent)
    loss_metric = nn.CrossEntropyLoss(weight=w_metric)

    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = len(train_dl) * args.epochs
    schedule = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=args.lr,
                                                   total_steps=steps, pct_start=0.1)

    best = -1.0
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        running = 0.0
        for step, batch in enumerate(train_dl, 1):
            optimiser.zero_grad()
            logits_i, logits_m = model(batch["input_ids"].to(device),
                                       batch["attention_mask"].to(device))
            # The metric head is the minor question; weighting it equally would
            # let "which figure" pull the shared encoder away from "what is
            # being asked", which is the label the pipeline actually branches on.
            loss = (loss_intent(logits_i, batch["intent"].to(device))
                    + 0.5 * loss_metric(logits_m, batch["metric"].to(device)))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            schedule.step()
            running += loss.item()
            if step % 20 == 0:
                print(f"  epoch {epoch} step {step}/{len(train_dl)} loss {running / step:.4f}")

        acc_i, acc_m = evaluate_split(model, val_dl, device)
        print(f"epoch {epoch}: val intent acc {acc_i:.4f}   val metric acc {acc_m:.4f}   "
              f"({time.time() - started:.0f}s)")

        if acc_i > best:
            best = acc_i
            save(model, tokenizer, args)
            print(f"  saved (best so far) -> {args.out}")

    print(f"\ndone in {time.time() - started:.0f}s. best val intent accuracy {best:.4f}")
    print(f"now score it against the hand-written eval set:\n"
          f"    python3 ml/evaluate.py --model {args.out} --compare --per-class")


def save(model, tokenizer, args):
    os.makedirs(args.out, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(args.out, "model.pt"))
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"base_model": args.base_model, "intents": list(INTENTS),
                   "metrics": list(METRICS), "max_length": MAX_LENGTH}, fh, indent=2)


if __name__ == "__main__":
    main()
