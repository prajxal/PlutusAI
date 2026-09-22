#!/usr/bin/env python3
"""Score a classifier against the hand-written eval set.

    python3 ml/evaluate.py                        # the regex baseline
    python3 ml/evaluate.py --model ml/artifacts   # a trained checkpoint
    python3 ml/evaluate.py --model ml/artifacts --compare

The eval set is hand-written and never generated from the rules (ml/README.md
explains why that matters). English and Hinglish are reported separately
because one number over both hides the only interesting result: the baseline
is decent at English and close to useless at Hinglish.
"""
import argparse
import json
import os
import sys

from sklearn.metrics import classification_report, f1_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))

from taxonomy import INTENTS, metric_label  # noqa: E402

EVAL_SET = os.path.join(HERE, "data", "eval_set.jsonl")


def load(path=EVAL_SET):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def score(rows, intents_pred, metrics_pred, title):
    """Accuracy and macro-F1 for one slice."""
    gold = [r["intent"] for r in rows]
    acc = sum(g == p for g, p in zip(gold, intents_pred)) / len(rows)
    macro = f1_score(gold, intents_pred, labels=list(INTENTS), average="macro", zero_division=0)

    # Metric accuracy is only meaningful where a metric is actually expected.
    insight = [i for i, r in enumerate(rows) if r["intent"] == "insight"]
    m_acc = (
        sum(metric_label(rows[i]["metric"]) == metrics_pred[i] for i in insight) / len(insight)
        if insight else float("nan")
    )
    print(f"  {title:<10} n={len(rows):<4} intent acc {acc:.3f}   macro-F1 {macro:.3f}   "
          f"metric acc (insight only) {m_acc:.3f}")
    return {"n": len(rows), "accuracy": acc, "macro_f1": macro, "metric_accuracy": m_acc}


def evaluate(classifier, rows, name, per_class=False):
    print(f"\n{name}")
    preds = [classifier.classify(r["message"]) for r in rows]
    intents_pred = [p.name for p in preds]
    metrics_pred = [metric_label(getattr(p, "metric", None)) for p in preds]

    result = {"overall": score(rows, intents_pred, metrics_pred, "overall")}
    for variant in ("english", "hinglish"):
        idx = [i for i, r in enumerate(rows) if r["variant"] == variant]
        if idx:
            result[variant] = score(
                [rows[i] for i in idx],
                [intents_pred[i] for i in idx],
                [metrics_pred[i] for i in idx],
                variant,
            )

    if per_class:
        print()
        print(classification_report([r["intent"] for r in rows], intents_pred,
                                    labels=list(INTENTS), zero_division=0))
    result["_predictions"] = list(zip([r["message"] for r in rows],
                                      [r["intent"] for r in rows], intents_pred))
    return result


def baseline_classifier():
    from services.chat.intent import RegexIntentClassifier

    return RegexIntentClassifier()


def model_classifier(path):
    from infer import LocalIntentModel

    return LocalIntentModel(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="path to a trained checkpoint directory")
    ap.add_argument("--eval-set", default=EVAL_SET)
    ap.add_argument("--compare", action="store_true", help="also score the baseline")
    ap.add_argument("--per-class", action="store_true")
    ap.add_argument("--errors", action="store_true", help="print what was got wrong")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    rows = load(args.eval_set)
    print(f"Eval set: {len(rows)} hand-written examples "
          f"({sum(r['variant'] == 'english' for r in rows)} English, "
          f"{sum(r['variant'] == 'hinglish' for r in rows)} Hinglish)")

    results = {}
    if args.model is None or args.compare:
        results["baseline"] = evaluate(baseline_classifier(), rows,
                                       "RegexIntentClassifier (baseline)", args.per_class)
    if args.model:
        results["model"] = evaluate(model_classifier(args.model), rows,
                                    f"Fine-tuned model ({args.model})", args.per_class)

    if "baseline" in results and "model" in results:
        print("\nVerdict")
        for slice_name in ("overall", "english", "hinglish"):
            b = results["baseline"][slice_name]["macro_f1"]
            m = results["model"][slice_name]["macro_f1"]
            arrow = "beats" if m > b else "does NOT beat"
            print(f"  {slice_name:<10} macro-F1 {b:.3f} -> {m:.3f}   model {arrow} the baseline")

    if args.errors:
        key = "model" if "model" in results else "baseline"
        print(f"\nWhat {key} got wrong")
        for msg, gold, pred in results[key]["_predictions"]:
            if gold != pred:
                print(f"  {gold:<15} -> {pred:<15} {msg}")

    if args.json_out:
        clean = {k: {s: v for s, v in r.items() if not s.startswith("_")}
                 for k, r in results.items()}
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2)
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
