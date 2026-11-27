"""Tools read the data pack. Exact facts come from here, never from the model.

The data files live in data/. Paths are built from this file's location so they work
the same on your laptop and on Vercel.
"""
import csv
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import tool

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _batches() -> dict:
    """Batch master joined to the SKU master. Codes are cleaned so lookups do not miss."""
    with open(DATA / "sku_master.csv", newline="") as f:
        skus = {r["sku_code"].strip().upper(): r for r in csv.DictReader(f)}
    with open(DATA / "batch_master.csv", newline="") as f:
        out = {}
        for r in csv.DictReader(f):
            code = r["sku_code"].strip().upper()
            out[r["batch_no"].strip().upper()] = {**skus.get(code, {}), **r, "sku_code": code}
        return out


def batch_record(batch_no: str) -> dict:
    """Plain function: easy to test without a model."""
    row = _batches().get(batch_no.strip().upper())
    if row is None:
        return {"found": False, "batch_no": batch_no, "reason": "No such batch in the batch master"}
    return {"found": True, **row}


@tool
def lookup_batch(batch_no: str) -> dict:
    """Look up one batch in the batch master. Returns the SKU, product, manufacturing date,
    expiry date and price to stockist, or found=False if the batch does not exist.
    Use it whenever a question mentions a batch number."""
    return batch_record(batch_no)


TOOLS = [lookup_batch]


# ---------------------------------------------------------------------------------------
# Scheme cap tools. They read the two small tables made by prepare_data.py. Exact numbers
# come from here and from agent/rules.py, never from the model.
# ---------------------------------------------------------------------------------------
from agent import rules  # noqa: E402

DEFAULT_BASIS_QUARTER = "Q1 FY27"  # fallback when the requested quarter is not in scheme_by_quarter.csv yet
RULE_TEXT = (
    "Policy CO-POL-014 section 4.4: free goods issued under all schemes in a quarter, valued at PTS, "
    "must not exceed 3% of that quarter's primary sales. Going above needs CFO approval (section 4.3)."
)


@lru_cache(maxsize=1)
def _quarters() -> dict:
    with open(DATA / "scheme_by_quarter.csv", newline="") as f:
        return {r["quarter"]: (float(r["sales_inr"]), float(r["free_inr"])) for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _tiers() -> dict:
    with open(DATA / "scheme_by_tier.csv", newline="") as f:
        return {(r["quarter"], r["tier"]): float(r["free_inr"]) for r in csv.DictReader(f)}


def scheme_quarter(quarter: str) -> dict:
    """Route A for one quarter: free goods against the 3% cap."""
    q = rules.quarter_from_text(quarter)
    if q is None or q not in _quarters():
        have = ", ".join(sorted(_quarters(), key=rules.quarter_key))
        return {"found": False, "message": f"I have no data for '{quarter}'. Quarters available: {have}."}
    sales, free = _quarters()[q]
    return {
        "found": True,
        "route": "A",
        "rule": RULE_TEXT,
        "method": "Free goods (free packs x PTS) divided by sales (billed packs x PTS), compared with 3%.",
        **rules.quarter_result(q, sales, free),
    }


def scheme_summary() -> dict:
    """Route A for the whole period: every quarter, total excess and excess per year."""
    rows = [(q, s, f) for q, (s, f) in _quarters().items()]
    return {
        "found": True,
        "route": "A",
        "rule": RULE_TEXT,
        "method": "For each quarter: free goods divided by sales, compared with 3%. Excess = free goods minus 3% of sales, "
                  "added up over the quarters above the cap. Per year = total divided by years covered.",
        **rules.period_summary(rows),
    }


def planned_offer(tier_a_free: float | None, tier_b_free: float | None = None, basis_quarter: str | None = None) -> dict:
    """Route B: what a planned offer (free packs per 10 bought) would give, using a real quarter's orders."""
    if tier_a_free is None:
        return {"found": False, "message": "Tell me the planned offer, for example '10 + 1.5' (free packs per 10 bought on Tier A)."}
    q = rules.normalise_quarter(basis_quarter) if basis_quarter else DEFAULT_BASIS_QUARTER
    if q is None or q not in _quarters():
        return {"found": False, "message": f"I have no data for '{basis_quarter}' to use as the basis."}
    sales, free = _quarters()[q]
    free_a, free_b = _tiers().get((q, "A"), 0.0), _tiers().get((q, "B"), 0.0)
    return {
        "found": True,
        "route": "B",
        "rule": RULE_TEXT,
        "method": f"Take the real orders of {q}. Free goods scale with the free packs per 10 (policy Annexure B). Compare with 3% of sales.",
        "assumptions": [
            f"Same orders as {q}: stockists would order the same quantities under the new offer.",
            "Tier B stays as it is unless a Tier B offer is given.",
            "This is an estimate, not a prediction.",
        ],
        **rules.project_offer(q, sales, free_a, free_b, tier_a_free, tier_b_free),
    }


def assess_requests(requests: list[dict], period: str | None = None) -> dict:
    """Route B for approval requests: an offer ratio, a rupee amount, or several of them, for a quarter.

    Each request is a dict with any of: tier_a_free, tier_b_free (free packs per 10 bought),
    amount_cr (INR crore of free goods), extra (True if the amount is on top of the current offer).
    `period` is a quarter ('Q3 FY27') or a month and year ('December 2026').
    """
    target = rules.quarter_from_text(period) if period else None
    if period and target is None:
        return {"found": False, "message": f"I could not read the period '{period}'. Use a quarter like Q3 FY27 or a month and year like December 2026."}
    ratio_req = next((r for r in requests if r.get("tier_a_free") is not None), None)
    ratio = (ratio_req["tier_a_free"], ratio_req.get("tier_b_free")) if ratio_req else None
    amounts = [r["amount_cr"] * rules.CRORE for r in requests if r.get("amount_cr") is not None]
    extra = any(r.get("extra") for r in requests if r.get("amount_cr") is not None)
    if ratio is None and not amounts:
        return {"found": False, "message": "Tell me the request: an offer such as '10 + 1.5' on Tier A, or an amount such as 'INR 1.2 crore of free goods'."}

    in_data = target in _quarters()
    basis = target if in_data else DEFAULT_BASIS_QUARTER
    sales, free = _quarters()[basis]
    free_a, free_b = _tiers().get((basis, "A"), 0.0), _tiers().get((basis, "B"), 0.0)
    summary = scheme_summary()
    assumptions = [
        f"Expected sales are taken from {basis}" + ("." if in_data else f", the latest full quarter, because there is no data yet for {target or 'the next quarter'}."),
        "Stockists would order the same quantities as in that quarter.",
    ]
    if ratio is not None:
        assumptions.append("The offer ratio scales that quarter's free goods; Tier B stays as it is unless a Tier B offer is given.")
    if amounts:
        assumptions.append("Rupee amounts are added on top of the offer ratio if one is given" + (", or on top of the current offer when the request says extra." if extra and ratio is None else "; with no ratio they are the whole of the free goods."))
    assumptions.append("This is an estimate, not a prediction.")
    return {
        "found": True,
        "route": "B",
        "rule": RULE_TEXT,
        "method": "Add up the free goods the request(s) would give for the quarter and compare with 3% of expected sales.",
        "requested_for": target or "not stated",
        "basis_quarter": basis,
        "history": {
            "quarters_over_cap": len(summary["quarters_over_cap"]),
            "total_excess_cr": summary["total_excess_cr"],
            "excess_per_year_cr": summary["excess_per_year_cr"],
        },
        "assumptions": assumptions,
        **rules.project_requests(basis, sales, free_a, free_b, ratio, amounts, extra),
    }
