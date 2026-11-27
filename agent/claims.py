"""Claims window tools. Exact facts come from here and from agent/rules.py, never from the model.

check_claim:     intake mode. One new claim in, pass / reject / escalate out, with the dates and the days.
window_summary:  recovery list mode. The same rule run over the register by prepare_claims.py.
"""
import csv
from functools import lru_cache

from agent import rules
from agent.tools import DATA, batch_record

RULE_TEXT = (
    "Claims policy section 5.2: a near-expiry claim is valid only in the 90 days before the batch's expiry date; "
    "an expired claim only within 90 days after it. Expiry is taken from the batch master, not from the claim form."
)
PERSON_DECIDES_CLAIMS = "This is a recommendation only. The claims team and the credit note owners decide."


@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    with open(DATA / "claims_window_check.csv", newline="") as f:
        return list(csv.DictReader(f))


def _value(row: dict) -> float:
    return float(row["value_inr"]) if row["value_inr"] else 0.0


def lakh(value: float) -> float:
    return round(value / 100_000, 1)


def check_claim(batch_no: str | None, claim_date: str | None, claim_type: str | None) -> dict:
    """Intake mode: check one new claim against the 90-day window."""
    if not batch_no:
        return {"found": False, "message": "Tell me the batch number of the claim, for example K2310408."}
    ctype = rules.normalise_claim_type(claim_type)
    if ctype is None:
        return {"found": False, "message": "Tell me the claim type: near expiry, expired, breakage or short supply."}
    cdate = rules.parse_date(claim_date)
    if cdate is None:
        return {"found": False, "message": "Tell me the date the claim was raised, for example 12-02-2026."}
    base = {"found": True, "route": "C", "topic": "claims", "rule": RULE_TEXT,
            "method": "Look up the expiry date in the batch master, count the days between the claim date and expiry, "
                      "and compare with the 90-day window for the claim type.",
            "batch_no": batch_no.strip().upper(), "claim_type": ctype, "claim_date": cdate.isoformat()}
    batch = batch_record(batch_no)
    if not batch["found"]:
        return {**base, "outcome": "escalate", "code": "NO_BATCH", "expiry_date": None,
                "reason": "This batch is not in the batch master. Batches from before October 2023 are archived, so the expiry "
                          "date cannot be checked. Escalate to a person; do not reject."}
    expiry = rules.parse_date(batch["expiry_date"])
    return {**base, "expiry_date": expiry.isoformat(), "expiry_source": "batch_master",
            **rules.window_check(ctype, cdate, expiry)}


def window_summary() -> dict:
    """Recovery list mode: how many credited claims broke the window, and what is still pending."""
    rows = _rows()
    credited = [r for r in rows if r["status"] == "Credited"]

    def group(name: str, status_rows: list[dict]) -> dict:
        sel = [r for r in status_rows if r["group"] == name]
        total = sum(_value(r) for r in sel)
        return {"claims": len(sel), "value_lakh": lakh(total), "value_lakh_per_year": lakh(total / rules.YEARS_COVERED)}

    firm, confirm = group("firm", credited), group("confirm", credited)
    verifiable = [r for r in credited if r["group"] in ("firm", "confirm")]
    pending_hold = [r for r in rows if r["status"] == "Pending" and r["group"] in ("firm", "confirm", "cannot_verify")]
    by_code = {}
    for r in verifiable:
        by_code.setdefault(r["code"], []).append(r)
    return {
        "found": True, "route": "D", "topic": "claims", "rule": RULE_TEXT,
        "method": "Every credited claim was checked with the same window rule used at intake, with expiry from the batch master. "
                  "Yearly figure = period total divided by 2.5 years (1 Apr 2024 to 30 Sep 2026).",
        "credited_claims_checked": len(credited) - sum(1 for r in credited if r["group"] == "not_checked"),
        "not_checked_breakage_or_short_supply": sum(1 for r in credited if r["group"] == "not_checked"),
        "verifiable_breaches": group_total(firm, confirm),
        "firm_more_than_90_days_after_expiry": firm,
        "confirm_with_claims_team": confirm,
        "confirm_breakdown": {
            "raised_more_than_90_days_before_expiry": _count_value(by_code.get("TOO_EARLY", [])),
            "near_expiry_label_but_raised_1_to_90_days_after_expiry": _count_value(by_code.get("AFTER_EXPIRY", [])),
        },
        "cannot_verify_batch_not_in_master": group("cannot_verify", credited),
        "pending_claims_outside_window_to_hold": {
            "claims": len(pending_hold),
            "value_lakh": lakh(sum(_value(r) for r in pending_hold)),
            "claims_without_a_stated_value": sum(1 for r in pending_hold if not r["value_inr"]),
        },
        "export": "/api/recovery-list.csv",
    }


def group_total(a: dict, b: dict) -> dict:
    return {"claims": a["claims"] + b["claims"], "value_lakh": round(a["value_lakh"] + b["value_lakh"], 1),
            "value_lakh_per_year": round(a["value_lakh_per_year"] + b["value_lakh_per_year"], 1)}


def _count_value(rows: list[dict]) -> dict:
    return {"claims": len(rows), "value_lakh": lakh(sum(_value(r) for r in rows))}


def recovery_list_csv_path():
    return DATA / "claims_window_check.csv"
