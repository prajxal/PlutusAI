"""
The chat pipeline (Module C).

    message -> classify intent -> fill slots -> call one tool -> narrate

That is the whole thing. It replaces a Bedrock tool-calling loop, and the
replacement is not a downgrade in the part that matters: the loop's job was to
choose a tool and read back the result, and both are now decisions that can be
tested, explained and shown to the owner.

What the model may influence is deliberately tiny -- one label out of six.
Which product, how much, what the numbers are and what the sentence says are
all code.
"""
from shared import config, repository
from shared.errors import ApiError, MissingParams
from shared.log import logger

from services.chat import narrate, slots, tools
from services.chat.intent import get_classifier

METHOD_PLAIN = {
    "elasticity_from_history": (
        "Measured from your own price history. This product has changed price enough times "
        "for me to see how demand actually responded."
    ),
    "default_elasticity": (
        "A category assumption, not your data. This product has not changed price enough "
        "for me to measure how its demand responds."
    ),
    "user_supplied": "The demand response you gave me, applied to your own volumes.",
    "direct_recompute": (
        "Arithmetic on your own numbers. Nothing about behaviour is being predicted here, "
        "so there is nothing to estimate."
    ),
    "stated_costs": (
        "Your own volumes, with the costs you gave me. What it would cost you to produce "
        "in-house is not in your data, so that figure is yours, not mine."
    ),
}


def answer(business_id: str, session_id: str, message: str) -> dict:
    """One conversational turn."""
    message = (message or "").strip()
    if not message:
        raise ApiError(400, "Type a question and I will answer it.")

    # Loaded before the new turn is written so ownership is checked first.
    repository.get_session_turns(session_id, business_id, config.SESSION_TURN_WINDOW)
    repository.append_session_turn(session_id, business_id, "user", message)

    intent = get_classifier().classify(message)
    products = tools.products_of(business_id)
    filled = slots.extract(message, products)

    reply, simulation = _dispatch(business_id, intent, filled, products, message)

    repository.append_session_turn(session_id, business_id, "assistant", reply)
    logger.info("Chat turn complete", business_id=business_id, session_id=session_id,
                intent=intent.name, confidence=intent.confidence, source=intent.source,
                simulated=simulation is not None)

    return _shape(reply, simulation, message, intent)


def _dispatch(business_id, intent, filled, products, message):
    """Route to exactly one tool. Returns (reply, simulation result or None)."""
    # A classifier that is not sure should ask, not guess. Acting on a
    # half-confident label is how an owner ends up repricing the wrong product.
    if not intent.trusted:
        return narrate.unclear(products), None

    if intent.name in ("price_change", "cost_change"):
        return _change(business_id, intent.name, filled, products)
    if intent.name == "make_vs_buy":
        return _make_vs_buy(business_id, filled)
    if intent.name == "list_scenarios":
        return narrate.saved_scenarios(tools.list_scenarios(business_id, 5)["scenarios"]), None
    if intent.name == "insight":
        metric = intent.metric or "revenue"
        data = tools.get_metric(business_id, metric, product=filled.product)
        return narrate.insight(business_id, metric, data.get("product"), data), None
    return narrate.unclear(products), None


def _change(business_id, scenario_type, filled, products):
    if not filled.product:
        return f"Which product did you mean? You sell {narrate._list(products)}.", None
    if filled.delta_pct is None:
        verb = "change" if scenario_type == "price_change" else "change the cost of"
        return (f"By how much should I {verb} the {filled.product.lower()}? Tell me a "
                f"percentage, for example 10% up or 5% down."), None

    result = tools.run_simulation(
        business_id, scenario_type,
        {"product": filled.product, "delta_pct": filled.delta_pct},
    )
    return narrate.price_or_cost_change(
        result, filled.product, filled.delta_pct, scenario_type
    ), result


def _make_vs_buy(business_id, filled):
    try:
        result = tools.run_simulation(business_id, "make_vs_buy", {
            "item": filled.item,
            "in_house_unit_cost": filled.in_house_unit_cost,
            "setup_cost": filled.setup_cost,
        })
    except MissingParams as exc:
        # Not a failure: asking for the missing number is the right answer.
        return f"{exc.message} Give me a figure per unit and I will run it.", None
    return narrate.make_vs_buy(result, filled.item), result


def _shape(reply, simulation, question, intent):
    """The response contract. `chart`, `assumptions` and `scenario_saved_id`
    are the documented Module C fields; the rest exist because Foundation Rule
    3 requires the method and confidence to be visible, and the contract had
    nowhere to put them."""
    response = {
        "reply": reply,
        "chart": None,
        "assumptions": [],
        "scenario_saved_id": None,
        "intent": {"name": intent.name, "confidence": round(intent.confidence, 3),
                   "source": intent.source},
    }
    if not simulation:
        return response

    response.update({
        "chart": {"type": "line", **simulation["series"]},
        "assumptions": simulation["assumptions"],
        "method": simulation["method"],
        "method_plain": METHOD_PLAIN.get(simulation["method"], simulation["method"]),
        "confidence": simulation["confidence"],
        "summary": {"metrics": _summary_metrics(simulation)},
        "question": question,
        "detail": simulation.get("detail"),
    })
    return response


def _summary_metrics(simulation):
    base, proj = simulation["baseline"], simulation["projected"]
    metrics = [
        {"label": "Revenue", "unit": "currency", "baseline": base["revenue"], "projected": proj["revenue"]},
        {"label": "Gross margin", "unit": "percent", "baseline": base["margin"], "projected": proj["margin"]},
        {"label": "Gross profit", "unit": "currency", "baseline": base["profit"], "projected": proj["profit"]},
    ]
    detail = simulation.get("detail") or {}
    if detail.get("units_baseline") is not None:
        metrics.append({
            "label": f"{detail.get('product', 'Units')} sold",
            "unit": "count",
            "baseline": detail["units_baseline"],
            "projected": detail["units_projected"],
        })
    return metrics


def save_scenario(business_id: str, payload: dict) -> str:
    """Keep a what-if the owner wants to come back to."""
    if not payload.get("question"):
        raise ApiError(400, "There is nothing to save yet.")
    return repository.save_scenario(business_id, {
        "question": payload["question"],
        "summary": payload.get("summary") or "",
        "scenario_type": payload.get("scenario_type"),
        "params": payload.get("params"),
        "baseline": payload.get("baseline"),
        "projected": payload.get("projected"),
        "method": payload.get("method"),
        "confidence": payload.get("confidence"),
    })


def list_scenarios(business_id: str, limit: int = 10) -> dict:
    return tools.list_scenarios(business_id, limit)
