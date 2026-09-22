# The intent model (Phase 6)

The one learned component in PlutusAI. It decides **what the owner is asking
for** — one label out of six — and nothing else. Which product, how much, what
the numbers are and what the reply says are all code.

It is handed the raw message and **no business data whatsoever**: not the
products, not the figures, not an id. Whatever runs here cannot leak a
customer's numbers because it is never given any.

## Results

Against `data/eval_set.jsonl` — 134 hand-written examples, 84 English, 50
Hinglish (including Devanagari):

| | baseline macro-F1 | model macro-F1 |
|---|---|---|
| overall | 0.469 | **1.000** |
| English | 0.549 | **1.000** |
| Hinglish | 0.309 | **1.000** |

Metric head (insight questions only): 0.719 → **0.812**.

The baseline is `RegexIntentClassifier`: precision 0.81, recall 0.46 — exact on
the phrasings it knows, blind to everything else, and it collapses to `unclear`
on almost all Hinglish. That collapse is the gap this phase exists to close.

### Read that 1.000 sceptically

**A perfect macro-F1 means the eval set is saturated, not that the model is
perfect.** The training templates and the eval set were written by the same
author in the same sitting. No template string appears in the eval set, and the
labels were chosen by what is *correct* rather than by what the regexes say —
but the two still share a vocabulary and a set of assumptions about how an
owner phrases things. A genuinely independent eval set, written by a teammate
or drawn from real messages, would score lower and would be the number worth
putting in a report.

Two things stop this from being circular in the way the plan's risk table
warned about:

- **The eval set is never generated.** It is hand-written, and deliberately
  includes phrasings the regexes get wrong.
- **Training labels come from the template that produced the sentence**, not
  from the regexes. Distillation from `rules.py` would inherit its ceiling
  exactly; the generator reports that the regexes agree with only ~33% of
  generated labels, and the remaining ~67% is the headroom.

The metric head at 0.812 is the useful signal that the eval set is not
trivially easy. Its remaining errors are mostly questions with no specific
metric ("where am I losing money", "dhandha kaisa chal raha hai") where the
model picks a plausible one — debatable labels rather than clear mistakes.

## Layout

| File | Does |
|---|---|
| `taxonomy.py` | The label space. Standalone, so training needs nothing from `backend/`. `tests/test_taxonomy.py` stops it drifting |
| `generate_dataset.py` | Templated paraphrases, balanced per class, English + Hinglish |
| `data/eval_set.jsonl` | **Hand-written.** The honest number comes from here |
| `model.py` | One encoder, two heads (intent 6-way, metric 5-way incl. `none`) |
| `train.py` | Fine-tune on MPS / CUDA / CPU |
| `infer.py` | Load a checkpoint, classify a message |
| `evaluate.py` | Accuracy + macro-F1, model vs baseline, English vs Hinglish |
| `serve.py` | The HTTP endpoint the application talks to |

## Running it

```bash
pip install -r ml/requirements.txt

python3 ml/generate_dataset.py --n 4200      # -> data/train.jsonl, data/val.jsonl
python3 ml/train.py --epochs 4               # -> artifacts/   (~7 min on an M-series GPU)
python3 ml/evaluate.py --model ml/artifacts --compare --per-class
```

Then serve it and point the application at it:

```bash
python3 ml/serve.py --model ml/artifacts --port 8100
PLUTUS_INTENT_MODEL_URL=http://127.0.0.1:8100/classify python3 backend/app.py
```

`/api/health` reports `"intent": "model"` once it is wired up, and every chat
reply carries `intent.source` saying which classifier answered it.

## Design notes

**Two heads, one encoder.** "What is being asked" and "about which figure" are
the same question asked twice, so they share a sentence representation and
differ only in the last linear layer. The metric loss is weighted 0.5 — it is
the minor question, and weighting it equally lets it pull the encoder away from
the label the pipeline actually branches on.

**Mean pooling, not `<s>`.** XLM-R ships no trained pooler, so the average of
real tokens is a better sentence vector than the first one.

**Balanced sampling.** Sampling templates uniformly produced 1352 `cost_change`
rows against 46 `list_scenarios`, because slot-heavy intents have far more
unique fills. Macro-F1 weights every class equally, so that imbalance would go
straight into the number being optimised. Each (variant, intent) bucket now
gets the same quota, and inverse-frequency class weights cover what is left —
`unclear` still runs thin, because there are only so many ways to type "hello".

**`none` is a real metric class, not a mask.** Most intents have no metric and
the model should say so, rather than being asked only sometimes.

## The fallback is not optional

`backend/services/chat/model_intent.py` falls back to the regexes on *any*
problem: unreachable, timeout, HTTP error, unparseable body, or a label outside
the taxonomy. The reply is then marked `rules_fallback`, so a degraded answer
is visible rather than silent.

A hosted classifier going down must cost the owner answer *quality*, never the
answer itself. `tests/test_model_intent.py` covers each failure mode, and one
test asserts the request body is exactly `{"message": ...}` and carries no
business data.

## Known wrinkles

- `transformers` 5.x prints a Mistral-regex warning when loading the saved
  tokenizer. It is spurious for XLM-R — tokenisation is correct, as the scores
  show — but it is noisy.
- `artifacts/model.pt` is ~1.1 GB (fp32). It is gitignored. Quantising or
  saving fp16 would cut it substantially and is untried.
- The checkpoint is selected on generated-val accuracy, which saturates at
  1.000 by epoch 3. Selecting on the hand-written eval set instead would be
  better practice, but would spend the only honest measurement on model
  selection.
