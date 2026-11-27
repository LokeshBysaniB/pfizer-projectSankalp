"""The pilot workflow, as a LangGraph graph.

    understand (model) -> route A (code) -> explain (model) -> a person decides
                       -> route B (code) -> explain (model)
                       -> route C (code) -> explain (model)
                       -> route D (code) -> explain (model)
                       -> decline (code)

A and B: scheme cap (what happened, what a planned offer would do).
C and D: claims window (check one new claim, or summarise the recovery list).

The model only reads the question and words the answer. Every number comes from
agent/tools.py and agent/rules.py.
"""
import json
import time
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agent import claims, tools
from agent.llm import get_llm

UNDERSTAND = (
    "You read one question about Pfizer Limited's trade channel and return ONLY a JSON object, nothing else:\n"
    '{"route": "A" or "B" or "C" or "D" or "other", "period": string or null, '
    '"requests": [{"tier_a_free": number or null, "tier_b_free": number or null, "amount_cr": number or null, "extra": true or false}], '
    '"claim": {"batch_no": string or null, "claim_date": string or null, "claim_type": string or null}}\n'
    "route A = scheme cap, what actually happened: free goods against the 3% cap, past quarters, how much over the cap. requests is [].\n"
    "route B = scheme cap, a request or plan to approve: what if we run 10 + 2, would this scheme break the cap, can I approve these requests.\n"
    "route C = check ONE new expiry claim against the 90-day claim window: is this claim valid, can I accept it, is it inside the window.\n"
    "route D = the claims window across all past claims: how many credited claims were outside the window, how much money, the recovery list.\n"
    "other = anything else.\n"
    "period = the quarter or month the question is about, exactly as written ('Q3 FY25', 'December 2026'), or null.\n"
    "One object in requests per request or offer in the question.\n"
    "tier_a_free = free packs per 10 bought ('10 + 1.5' gives 1.5), or null. tier_b_free = the same for Tier B, only if given.\n"
    "amount_cr = a rupee amount of free goods in INR crore ('INR 1.2 crore' gives 1.2, '50 lakh' gives 0.5), or null.\n"
    "extra = true only if the wording says the amount is extra, additional or on top of the current offer.\n"
    "claim (route C only): batch_no exactly as written, claim_date as DD-MM-YYYY, claim_type as written ('near expiry', 'expired', 'breakage', 'short supply'). Use null for anything not given. For other routes claim is null."
)

EXPLAIN_FULL = (
    "You explain a scheme cap result to a finance or sales colleague in plain words, no jargon. "
    "Use ONLY the numbers in the result JSON; never calculate or invent a number. Quote the *_cr values as INR crore. "
    "Say what the rule is, what the result is, and how it was worked out. For route B, say whether the request fits within the cap, "
    "by how much it is over or under, the largest Tier A offer that stays within it if given, the history, and the assumptions, "
    "and say it is an estimate. Keep it under 150 words."
)

EXPLAIN_TABLE = (
    "You explain a scheme cap result to a finance or sales colleague in plain words, no jargon. "
    "A detailed table shows the quarter-by-quarter figures; do not repeat every number from the JSON. "
    "State the 3% rule, the headline story (how many quarters were over, total excess), and what the person should look at in the table. "
    "Never calculate or invent a number. Keep it under 100 words."
)

EXPLAIN_CLAIMS_INTAKE = (
    "You advise a claims colleague on the next step for ONE claim check. Plain sentences only — no headings, "
    "no 'Decision:', 'Claim Date:' labels, and no bullet lists. "
    "The UI already shows the outcome, batch, dates, allowed window, and the reason from the tool; do not repeat those facts. "
    "Write 1–3 short sentences: what they should do (accept, reject, refile, escalate, or ask claims team to confirm). "
    "For TOO_EARLY you may name valid_from once as the earliest date to refile. "
    "For TOO_LATE on an expired claim you may name valid_until once as the last day the window was open — "
    "never cite valid_from for a late expired claim. Never invent a date. Keep it under 60 words."
)

EXPLAIN_CLAIMS_RECOVERY = (
    "You explain a recovery-list result to a claims or finance colleague in plain words, no jargon. "
    "A table lists the totals; do not repeat every count and INR lakh figure from the JSON. "
    "Explain how firm (more than 90 days after expiry) differs from confirm with the claims team, cannot-verify batches, "
    "and pending claims to hold, and that confirm needs the claims team before any recovery. "
    "Never calculate or invent a number. Keep it under 100 words."
)


def wants_facts_table(result: dict) -> bool:
    """Whether the UI should show the expandable numbers table."""
    if not result.get("found"):
        return False
    if result.get("route") == "D":
        return True
    if result.get("route") == "A" and result.get("quarters"):
        return True
    return False


def explain_prompt(result: dict) -> str:
    if result.get("topic") == "claims":
        return EXPLAIN_CLAIMS_RECOVERY if result.get("route") == "D" else EXPLAIN_CLAIMS_INTAKE
    if wants_facts_table(result):
        return EXPLAIN_TABLE
    return EXPLAIN_FULL

PERSON_DECIDES = "This is a recommendation only. Sales, the Controller and the CFO decide."
DECLINE = ("I can answer questions about the 3% scheme cap (how past quarters did, or what a planned offer would do) "
           "and about the 90-day expiry claim window (check one claim, or see the recovery list). Try one of those.")


class State(TypedDict, total=False):
    question: str
    route: str
    period: str | None
    requests: list
    claim: dict
    result: dict
    answer: str
    model_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _usage_totals(message) -> dict[str, int]:
    """Token counts from an AIMessage when the provider returns them."""
    out = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    um = getattr(message, "usage_metadata", None)
    if isinstance(um, dict):
        prompt = int(um.get("input_tokens") or um.get("prompt_tokens") or 0)
        completion = int(um.get("output_tokens") or um.get("completion_tokens") or 0)
        total = int(um.get("total_tokens") or prompt + completion)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}
    meta = getattr(message, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or prompt + completion)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}
    return out


def _merge_usage(state: dict, message) -> dict[str, int]:
    u = _usage_totals(message)
    return {
        "prompt_tokens": int(state.get("prompt_tokens") or 0) + u["prompt_tokens"],
        "completion_tokens": int(state.get("completion_tokens") or 0) + u["completion_tokens"],
        "total_tokens": int(state.get("total_tokens") or 0) + u["total_tokens"],
    }


def _json_from(text: str) -> dict:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _clean_request(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    req = {
        "tier_a_free": _number(item.get("tier_a_free")),
        "tier_b_free": _number(item.get("tier_b_free")),
        "amount_cr": _number(item.get("amount_cr")),
        "extra": item.get("extra") is True,
    }
    return req if (req["tier_a_free"] is not None or req["amount_cr"] is not None) else None


def _clean_claim(item) -> dict:
    item = item if isinstance(item, dict) else {}
    return {k: (item.get(k).strip() or None) if isinstance(item.get(k), str) else None
            for k in ("batch_no", "claim_date", "claim_type")}


def understand(state: State) -> dict:
    reply = get_llm().invoke([SystemMessage(UNDERSTAND), HumanMessage(state["question"])])
    data = _json_from(reply.content)
    route = data.get("route") if data.get("route") in ("A", "B", "C", "D") else "other"
    raw = data.get("requests") if isinstance(data.get("requests"), list) else []
    return {
        "route": route,
        "period": data.get("period") if isinstance(data.get("period"), str) else None,
        "requests": [r for r in map(_clean_request, raw) if r],
        "claim": _clean_claim(data.get("claim")),
        "model_calls": 1,
        **_merge_usage(state, reply),
    }


def route_a(state: State) -> dict:
    period = state.get("period")
    return {"result": tools.scheme_quarter(period) if period else tools.scheme_summary()}


def route_b(state: State) -> dict:
    return {"result": tools.assess_requests(state.get("requests", []), state.get("period"))}


def route_c(state: State) -> dict:
    c = state.get("claim") or {}
    return {"result": claims.check_claim(c.get("batch_no"), c.get("claim_date"), c.get("claim_type"))}


def route_d(state: State) -> dict:
    return {"result": claims.window_summary()}


def decline(state: State) -> dict:
    return {"answer": DECLINE}


def explain(state: State) -> dict:
    result = state["result"]
    if not result.get("found"):
        return {"answer": result["message"]}
    prompt = f"Question: {state['question']}\n\nResult:\n{json.dumps(result, indent=2)}"
    reply = get_llm().invoke([SystemMessage(explain_prompt(result)), HumanMessage(prompt)])
    closing = claims.PERSON_DECIDES_CLAIMS if result.get("topic") == "claims" else PERSON_DECIDES
    return {
        "answer": f"{reply.content.strip()}\n\n{closing}",
        "model_calls": state.get("model_calls", 0) + 1,
        **_merge_usage(state, reply),
    }


def pick_route(state: State) -> str:
    return {"A": "route_a", "B": "route_b", "C": "route_c", "D": "route_d"}.get(state["route"], "decline")


builder = StateGraph(State)
builder.add_node("understand", understand)
builder.add_node("route_a", route_a)
builder.add_node("route_b", route_b)
builder.add_node("route_c", route_c)
builder.add_node("route_d", route_d)
builder.add_node("decline", decline)
builder.add_node("explain", explain)
builder.add_edge(START, "understand")
builder.add_conditional_edges("understand", pick_route, ["route_a", "route_b", "route_c", "route_d", "decline"])
builder.add_edge("route_a", "explain")
builder.add_edge("route_b", "explain")
builder.add_edge("route_c", "explain")
builder.add_edge("route_d", "explain")
builder.add_edge("explain", END)
builder.add_edge("decline", END)
graph = builder.compile()


def run_question(question: str) -> dict:
    started = time.perf_counter()
    final = graph.invoke({"question": question})
    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    result = final.get("result")
    return {
        "answer": final["answer"],
        "result": result,
        "show_table": wants_facts_table(result) if result else False,
        "evidence": [json.dumps(result, indent=2)] if result else [],
        "model_calls": final.get("model_calls", 0),
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": final.get("prompt_tokens", 0),
        "completion_tokens": final.get("completion_tokens", 0),
        "total_tokens": final.get("total_tokens", 0),
    }
