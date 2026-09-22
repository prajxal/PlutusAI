#!/usr/bin/env python3
"""Build the training set.

    python3 ml/generate_dataset.py --n 4000

**On labels.** The plan said to label generated paraphrases with `rules.py` as
an oracle. Taken literally that is pure distillation, and a student trained
only on its teacher's labels cannot beat the teacher -- we would have spent a
week building an expensive regex emulator, which is the headline risk in the
plan's own risk table.

So the label here is the template's own intent: we generated the sentence, so
we already know what it means, for free and without error. `rules.py` is kept
as a *cross-check* rather than the source of truth. Where it disagrees with
the template, the row is flagged `oracle_agrees: false` -- those rows are the
phrasings the baseline cannot see, and they are precisely the ones that give
the model somewhere to go. The generator reports how many there are, and the
Hinglish share of that number is the reason this phase is worth doing at all.

The eval set is untouched by any of this: it is hand-written, and no template
below appears in it.
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))

PRODUCTS_EN = ["sourdough", "the croissants", "the masala bun", "the brownies", "the loaf",
               "the cookies", "the cake", "the puffs", "the samosas", "the biscuits"]
PRODUCTS_HI = ["sourdough", "croissant", "masala bun", "brownie", "double roti",
               "biscuit", "cake", "samosa", "puff", "rusk"]
INPUTS_EN = ["butter", "flour", "sugar", "milk", "packaging", "the boxes", "cocoa",
             "yeast", "the trays", "labour"]
INPUTS_HI = ["maida", "butter", "cheeni", "dudh", "packaging", "dabba", "cocoa",
             "kaccha maal", "labour", "gas"]
MAKEABLE_EN = ["the packaging", "the boxes", "the jam", "the icing", "the bread",
               "the labels", "the trays", "the filling"]
MAKEABLE_HI = ["packaging", "dabba", "jam", "icing", "bread", "label", "tray", "masala"]
MONTHS_EN = ["January", "March", "May", "August", "October", "December", "last month",
             "last quarter", "this year", "April"]
MONTHS_HI = ["January", "March", "May", "August", "October", "December", "pichle mahine",
             "is mahine", "is saal", "April"]
PCT = ["5%", "10%", "12%", "15%", "20%", "8 percent", "25 percent", "7%", "30%", "6 percent"]
AMT = ["10", "20", "50", "5", "15", "100", "250", "280", "300", "40"]

# Each entry: (intent, metric, [templates]). Slots: {p} product, {i} input,
# {m} makeable, {mo} month, {pc} percent, {a} amount.
TEMPLATES = {
    "english": [
        ("price_change", None, [
            "what if I raise {p} price by {pc}?",
            "what if we increase prices {pc}",
            "suppose I discount {p} {pc}",
            "if we cut prices by {pc} what happens",
            "what would a {pc} price hike do",
            "if I put the rate up by {pc}",
            "what if {p} sold for {a} instead of {a}",
            "thinking of charging {a} more for {p}",
            "should I make {p} dearer by {pc}",
            "what if I raise all prices by {pc}",
            "planning a {pc} markup on {p}",
            "if {p} went to {a} from {a}",
            "is a {a} rupee increase on {p} worth it",
            "what happens if I drop {p} price {pc}",
            "suppose we mark {p} up {pc}",
            "considering a price rise of {pc}",
            "what if the selling price of {p} changed by {pc}",
            "lower {p} by {pc} and show me",
            "if I sold {p} at {a}",
            "price increase of {pc} on {p}, worth it?",
        ]),
        ("cost_change", None, [
            "suppose {i} cost goes up {pc}",
            "what if my {i} costs rise {pc}",
            "what if the supplier charges {pc} more for {i}",
            "what if {i} gets {pc} dearer",
            "{i} is going up {pc} next month",
            "what if {i} becomes cheaper by {pc}",
            "suppose {i} rates climb {pc}",
            "what if my costs drop {pc}",
            "if we pay {pc} more for {i}",
            "what happens when {i} goes up {pc}",
            "my supplier wants {pc} more for {i}",
            "what if {i} became {pc} more expensive",
            "suppose I found a cheaper source and saved {pc} on {i}",
            "if input prices fell by {pc}",
            "{i} purchase price up {pc}, then what",
            "what if procurement of {i} costs {pc} extra",
            "a {pc} rise in {i} expenses",
            "if {i} bills went down {pc}",
        ]),
        ("make_vs_buy", None, [
            "what if I make my own {m}?",
            "should I produce {m} instead of buying it",
            "what if we brought {m} in-house",
            "should we produce {m} ourselves",
            "is it worth stopping the outsourcing of {m}",
            "would manufacturing {m} internally save money",
            "thinking of setting up my own line for {m}",
            "make vs buy for {m}",
            "cheaper to do {m} in my own kitchen?",
            "we currently buy {m}, should we build it",
            "what would it take to stop buying {m} from outside",
            "is self production of {m} viable",
            "in-house {m} or keep buying",
            "if I made {m} myself instead",
            "stop outsourcing {m}?",
        ]),
        ("list_scenarios", None, [
            "show me my saved scenarios",
            "what were my earlier what-ifs",
            "show me my scenario history",
            "what did I simulate in {mo}",
            "pull up the previous scenarios",
            "list everything I have run so far",
            "open my past what-ifs",
            "my saved what-ifs please",
            "can I see the simulations I kept",
            "bring back that scenario from {mo}",
            "what have I asked you before",
            "show the scenarios I saved",
            "my what-if history",
            "review my old simulations",
            "which scenarios did I save for {p}",
            "the what-if I ran on {p}",
            "list my saved runs from {mo}",
            "what scenarios do I have for {p}",
            "reopen the {p} simulation",
            "everything I modelled in {mo}",
            "go back to my last scenario",
            "compare my saved scenarios",
            "did I already run one for {p}",
            "show saved projections",
            "my previous simulations please",
            "what-ifs I kept from {mo}",
        ]),
        ("insight", "revenue", [
            "what was my revenue in {mo}",
            "show me my sales trend",
            "which product makes me the most money",
            "how much did I sell in {mo}",
            "what is my turnover {mo}",
            "revenue for {p} in {mo}",
            "total sales {mo}",
            "how are takings looking",
            "what did {p} bring in",
            "top selling product by value",
        ]),
        ("insight", "margin", [
            "why did margin drop in {mo}?",
            "what is my gross margin",
            "how profitable is {p}",
            "margin trend for {p}",
            "which product has the best margin",
            "why is my margin falling",
            "show margin by product",
            "is {p} profitable",
        ]),
        ("insight", "units_sold", [
            "how many units did I sell in {mo}",
            "total units sold in {mo}",
            "how many {p} went out last week",
            "volume for {p} in {mo}",
            "how many did I move in {mo}",
            "unit sales by product",
        ]),
        ("insight", "cost", [
            "what are my costs looking like",
            "what did {p} cost me",
            "break down my spending by product",
            "how much am I spending on {i}",
            "cost trend for {p}",
            "what is my biggest expense",
        ]),
        ("insight", None, [
            "why was {mo} so bad",
            "is the bakery doing better than {mo}",
            "where am I losing money",
            "how did {mo} compare to {mo}",
            "which month was my best",
            "give me the numbers for {p}",
            "how is {p} doing",
            "summarise {mo} for me",
        ]),
        ("unclear", None, [
            "hello there", "thanks!", "who are you", "can you help",
            "what is the weather like", "ok", "tell me a joke", "good morning",
            "what can this thing do", "hi", "are you there", "never mind",
            "sorry", "yes", "no thanks", "cool", "one second", "hmm",
            "hey", "good evening", "thank you so much", "that is all",
            "wait", "what", "huh", "nothing", "forget it", "bye",
            "see you", "please hold on", "is anyone there", "testing",
            "how does this work", "what should I ask", "help me out",
            "I do not know", "maybe later", "sure", "fine", "great",
            "who made you", "are you a robot", "say something",
        ]),
    ],
    "hinglish": [
        ("price_change", None, [
            "agar main {p} ka price {pc} badha doon to?",
            "kya ho agar rate {pc} zyada kar doon",
            "{p} ka daam {pc} kam kar doon to kya hoga",
            "price {a} rupees badhane se kya farak padega",
            "agar main {pc} discount du to",
            "sabka rate {pc} upar kar dein to",
            "{p} mehenga karun {pc} se",
            "sasta bech doon to kya hoga {pc} kam pe",
            "{p} ka rate {a} kar doon to",
            "{pc} ka izafa karun {p} pe",
            "daam badhaun ya na badhaun {pc}",
            "{p} {a} me bechu to profit kitna",
            "agar {pc} sasta kar doon",
            "rate list {pc} upar karni hai, asar batao",
        ]),
        ("cost_change", None, [
            "agar {i} {pc} mehenga ho jaye to",
            "{i} ka cost {pc} badh gaya to kya hoga",
            "supplier {pc} zyada charge kare to",
            "agar {i} ka kharcha {pc} badh jaye",
            "{i} sasta ho gaya {pc} to kya asar",
            "kaccha maal {pc} mehenga hua to",
            "lagat {pc} kam ho jaye to profit kitna",
            "{i} ke daam {pc} chadh gaye to",
            "agar {i} par {pc} zyada dena pade",
            "purchase cost {pc} badha to margin pe kya",
            "{i} ka bill {pc} kam ho jaye to",
        ]),
        ("make_vs_buy", None, [
            "agar main khud {m} banau to?",
            "{m} khud banaun ya kharidun",
            "in-house {m} banane me faida hai kya",
            "apne hi kitchen me {m} banana sasta padega kya",
            "bahar se mangane ki jagah khud banaye to",
            "{m} khud bana lein to kitna bachega",
            "outsourcing band karke khud karein",
            "{m} ki manufacturing khud shuru karun",
            "kharidna band karke {m} banana theek rahega",
            "khud production karun {m} ka",
        ]),
        ("list_scenarios", None, [
            "mere purane scenarios dikhao",
            "pehle jo what-if kiye the wo dikha do",
            "saved scenarios dikhao",
            "meri scenario history kholo",
            "kal jo simulate kiya tha wo nikalo",
            "jo maine save kiya tha wo dikhao",
            "purane simulation dikha do",
            "pehle wale scenario kholo",
            "meri saved what-if list",
            "{p} ka scenario save kiya tha kya",
            "{mo} me jo run kiya tha wo dikhao",
            "sab scenarios ki list do",
            "{p} wala what-if kholo",
            "pichle projections dikhao",
            "jo calculate kiya tha pehle wo batao",
            "meri saved list kholo",
            "dobara wahi scenario dikhao",
            "{mo} ke saved what-if",
            "purani reports nikalo",
        ]),
        ("insight", "revenue", [
            "{mo} ka revenue kitna tha",
            "sabse zyada paisa kis product se aaya",
            "kitni bikri hui {mo} me",
            "{p} se kitna kamaya",
            "total sale batao {mo} ki",
            "kamai kaisi rahi {mo}",
        ]),
        ("insight", "margin", [
            "{mo} me margin kyun gira",
            "mera munafa kaisa chal raha hai",
            "{p} ka margin batao",
            "kis product me sabse zyada munafa hai",
            "margin kam kyun ho raha hai",
        ]),
        ("insight", "units_sold", [
            "kitne units beche the {mo} me",
            "{mo} me kitne {p} bike",
            "{p} ki kitni quantity gayi",
            "is mahine kitne units bike",
        ]),
        ("insight", "cost", [
            "kharcha kitna hua {mo}",
            "lagat kitni aa rahi hai {p} pe",
            "{i} pe kitna kharch ho raha hai",
            "sabse bada kharcha kya hai",
        ]),
        ("insight", None, [
            "dhandha kaisa chal raha hai",
            "kis mahine sabse acha tha",
            "{p} kaisa perform kar raha hai",
            "{mo} kaisa raha",
            "business ki halat batao",
        ]),
        ("unclear", None, [
            "namaste", "theek hai", "kya kar sakte ho", "shukriya", "haan bhai",
            "acha", "ok ji", "kuch nahi", "ruko", "batao", "hello ji", "arre",
            "namaskar", "kaise ho", "dhanyavaad", "bas", "chalo", "nahi",
            "haan", "ek minute", "samajh nahi aaya", "kya bola", "phir se",
            "kuch aur", "band karo", "rehne do", "ji", "sun rahe ho",
            "tum kaun ho", "yeh kya hai", "madad karo", "kuch batao",
        ]),
    ],
}


def fill(template, rng, variant):
    products = PRODUCTS_EN if variant == "english" else PRODUCTS_HI
    inputs = INPUTS_EN if variant == "english" else INPUTS_HI
    makeable = MAKEABLE_EN if variant == "english" else MAKEABLE_HI
    months = MONTHS_EN if variant == "english" else MONTHS_HI
    out = template
    # Repeated slots must draw different values -- "from 250 to 250" is noise.
    while "{a}" in out:
        out = out.replace("{a}", rng.choice(AMT), 1)
    while "{mo}" in out:
        out = out.replace("{mo}", rng.choice(months), 1)
    return (out.replace("{p}", rng.choice(products))
               .replace("{i}", rng.choice(inputs))
               .replace("{m}", rng.choice(makeable))
               .replace("{pc}", rng.choice(PCT)))


def casings(text, rng):
    """Owners type the way they type: no capital, all capital, a stray full stop."""
    roll = rng.random()
    if roll < 0.15:
        return text.upper()
    if roll < 0.55:
        return text.lower()
    if roll < 0.65:
        return text.rstrip("?.! ") + "."
    if roll < 0.72:
        return text.rstrip("?.! ")
    return text


def generate(n, seed=13):
    """Sample to a per-class quota, not uniformly over templates.

    Sampling templates uniformly produced 1352 cost_change rows against 46
    list_scenarios: the slot-heavy intents have far more unique fills, and
    dedupe then starves the intents that do not. Macro-F1 weights every class
    equally, so that imbalance goes straight into the number we are trying to
    move. Each (variant, intent) bucket therefore gets the same quota, and a
    bucket whose unique supply runs dry is simply reported short rather than
    padded with duplicates.
    """
    rng = random.Random(seed)
    buckets = [(v, g) for v, groups in TEMPLATES.items() for g in groups]

    # insight is split across five metric groups; treat it as one bucket per
    # variant so it is not five times the size of every other intent.
    by_class = {}
    for variant, group in buckets:
        by_class.setdefault((variant, group[0]), []).append(group)

    quota = max(1, n // len(by_class))
    rows, short = [], {}
    for (variant, intent), groups in sorted(by_class.items()):
        seen, made, attempts = set(), [], 0
        while len(made) < quota and attempts < quota * 80:
            attempts += 1
            _, metric, templates = rng.choice(groups)
            message = casings(fill(rng.choice(templates), rng, variant), rng)
            key = message.lower()
            if key in seen:
                continue
            seen.add(key)
            made.append({"message": message, "intent": intent, "metric": metric,
                         "variant": variant})
        if len(made) < quota:
            short[(variant, intent)] = len(made)
        rows.extend(made)

    if short:
        print("  (bucket short of quota -- not enough unique phrasings:)")
        for (variant, intent), got in sorted(short.items()):
            print(f"    {variant:<9} {intent:<15} {got}/{quota}")
    rng.shuffle(rows)
    return rows


def cross_check(rows):
    """Compare every generated label against the baseline, and say how often
    they differ. That difference is the headroom this phase is chasing."""
    from services.chat.intent import RegexIntentClassifier

    clf = RegexIntentClassifier()
    disagree = Counter()
    for row in rows:
        predicted = clf.classify(row["message"]).name
        row["oracle_label"] = predicted
        row["oracle_agrees"] = predicted == row["intent"]
        if not row["oracle_agrees"]:
            disagree[(row["variant"], row["intent"])] += 1
    return disagree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--val-split", type=float, default=0.1)
    ap.add_argument("--out-dir", default=os.path.join(HERE, "data"))
    args = ap.parse_args()

    rows = generate(args.n, args.seed)
    disagree = cross_check(rows)

    cut = int(len(rows) * (1 - args.val_split))
    splits = {"train": rows[:cut], "val": rows[cut:]}
    for name, split in splits.items():
        path = os.path.join(args.out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in split:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  {path}  {len(split)} rows")

    agree = sum(r["oracle_agrees"] for r in rows)
    print(f"\n{len(rows)} examples "
          f"({sum(r['variant'] == 'english' for r in rows)} English, "
          f"{sum(r['variant'] == 'hinglish' for r in rows)} Hinglish)")
    print(f"by intent: {dict(Counter(r['intent'] for r in rows))}")
    print(f"\nbaseline agrees with {agree}/{len(rows)} ({agree / len(rows):.1%}) of generated labels")
    print(f"the other {len(rows) - agree} rows are what the model has to learn "
          f"that the regexes cannot see:")
    for (variant, intent), count in sorted(disagree.items(), key=lambda kv: -kv[1]):
        print(f"    {variant:<9} {intent:<15} {count}")


if __name__ == "__main__":
    main()
