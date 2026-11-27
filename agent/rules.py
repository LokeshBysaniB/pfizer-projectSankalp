"""Business rules for the scheme cap. Plain Python, no model, one test each (tests/test_rules.py).

Policy CO-POL-014 v4.2, section 4.4: the value of free goods issued under all schemes in a
quarter, at PTS, must not exceed 3% of the quarter's primary sales value of the portfolio.
Going above the cap needs the CFO's approval (section 4.3).

Sales base: billed packs x PTS (free packs excluded). The policy does not say whether free
goods belong in the base. Counting them would lower the excess, so this is the stricter reading.
"""
import re

CAP = 0.03
CRORE = 10_000_000

# Free packs per 10 bought. Source: policy Annexure B (scheme circular register).
# Tier A: 10 + 1 in Q1 and Q2 FY25, then 10 + 2. Tier B starts in Q3 FY25 at 10 + 1.
EARLY_QUARTERS = {"Q1 FY25", "Q2 FY25"}


def normalise_quarter(text: str) -> str | None:
    """'q3 fy2025', 'FY25 Q3', 'Q3FY25' -> 'Q3 FY25'. Returns None if it cannot be read."""
    if not text:
        return None
    t = text.upper()
    q = re.search(r"Q\s*([1-4])", t)
    fy = re.search(r"FY\s*(?:20)?(\d{2})", t)
    if not (q and fy):
        return None
    return f"Q{q.group(1)} FY{fy.group(1)}"


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def fiscal_quarter(month: int, year: int) -> str:
    """Calendar month and year -> fiscal quarter label. Fiscal year runs April to March."""
    fy = year + 1 if month >= 4 else year
    q = ((month - 4) % 12) // 3 + 1
    return f"Q{q} FY{fy % 100:02d}"


def quarter_from_text(text: str | None) -> str | None:
    """Reads 'Q3 FY25', 'FY25 Q3', 'December 2026', 'Dec 2026'. Returns a fiscal quarter label or None."""
    if not text:
        return None
    q = normalise_quarter(text)
    if q:
        return q
    t = text.lower()
    month = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", t)
    year = re.search(r"\b(20\d{2})\b", t)
    if month and year:
        return fiscal_quarter(MONTHS[month.group(1)], int(year.group(1)))
    return None


def quarter_key(label: str) -> tuple:
    q, fy = label.split()
    return int(fy[2:]), int(q[1])


def free_pct(sales: float, free: float) -> float:
    """Free goods as a share of sales, in percent."""
    return free / sales * 100


def allowed_free(sales: float) -> float:
    return CAP * sales


def excess_over_cap(sales: float, free: float) -> float:
    """Rupees of free goods above the cap. Zero when at or under the cap."""
    return max(0.0, free - allowed_free(sales))


def cr(value: float) -> float:
    """Rupees to crore, 2 decimals, for display."""
    return round(value / CRORE, 2)


def quarter_result(quarter: str, sales: float, free: float) -> dict:
    over = excess_over_cap(sales, free)
    return {
        "quarter": quarter,
        "sales_cr": cr(sales),
        "free_goods_cr": cr(free),
        "free_pct": round(free_pct(sales, free), 2),
        "allowed_free_cr": cr(allowed_free(sales)),
        "excess_cr": cr(over),
        "over_cap": over > 0,
    }


def period_summary(rows: list[tuple[str, float, float]]) -> dict:
    """rows: (quarter, sales, free). Totals the excess and turns it into a yearly figure."""
    rows = sorted(rows, key=lambda r: quarter_key(r[0]))
    per_q = [quarter_result(*r) for r in rows]
    total = sum(excess_over_cap(s, f) for _, s, f in rows)
    years = len(rows) / 4
    return {
        "quarters": per_q,
        "quarters_over_cap": [q["quarter"] for q in per_q if q["over_cap"]],
        "total_excess_cr": cr(total),
        "years_covered": years,
        "excess_per_year_cr": cr(total / years),
    }


def current_offer(quarter: str) -> tuple[float, float | None]:
    """(Tier A free per 10, Tier B free per 10 or None) in force in a quarter."""
    if quarter in EARLY_QUARTERS:
        return 1.0, None
    return 2.0, 1.0


def project_offer(quarter: str, sales: float, free_a: float, free_b: float,
                  new_a: float, new_b: float | None = None) -> dict:
    """What free goods would have been in `quarter` under a different offer, same orders.

    Free goods scale in proportion to the free packs per 10: moving Tier A from 10 + 2 to
    10 + 1 halves the Tier A free goods. Orders are assumed not to change.
    """
    cur_a, cur_b = current_offer(quarter)
    new_b = cur_b if new_b is None else new_b
    proj_a = free_a * new_a / cur_a
    proj_b = free_b * new_b / cur_b if (cur_b and new_b is not None) else free_b
    proj = proj_a + proj_b
    allowed = allowed_free(sales)
    max_a = max(0.0, (allowed - proj_b) * cur_a / free_a) if free_a else None
    over = excess_over_cap(sales, proj)
    return {
        "basis_quarter": quarter,
        "sales_cr": cr(sales),
        "actual_free_goods_cr": cr(free_a + free_b),
        "actual_free_pct": round(free_pct(sales, free_a + free_b), 2),
        "planned_tier_a_free_per_10": new_a,
        "planned_tier_b_free_per_10": new_b,
        "projected_free_goods_cr": cr(proj),
        "projected_free_pct": round(free_pct(sales, proj), 2),
        "allowed_free_cr": cr(allowed),
        "projected_excess_cr": cr(over),
        "over_cap": over > 0,
        "max_tier_a_free_per_10_within_cap": round(max_a, 2) if max_a is not None else None,
    }


def project_requests(quarter: str, sales: float, free_a: float, free_b: float,
                     ratio: tuple[float, float | None] | None, amounts: list[float],
                     extra_amounts: bool = False) -> dict:
    """Total free goods for one quarter from one or more approval requests, against 3% of sales.

    ratio:   (Tier A free per 10, Tier B free per 10 or None) for the quarter-end scheme, or None.
    amounts: rupee amounts of free goods asked for.
    Amounts are the whole of the free goods when there is no ratio offer, and are added on top
    of the ratio offer when there is one. With extra_amounts and no ratio, they are added on top
    of the current offer.
    """
    cur_a, cur_b = current_offer(quarter)
    base, proj_a, proj_b = 0.0, 0.0, 0.0
    if ratio is not None:
        new_a, new_b = ratio
        new_b = cur_b if new_b is None else new_b
        proj_a = free_a * new_a / cur_a
        proj_b = free_b * new_b / cur_b if (cur_b and new_b is not None) else free_b
        base = proj_a + proj_b
    elif extra_amounts:
        base = free_a + free_b
    added = sum(amounts)
    total = base + added
    allowed = allowed_free(sales)
    over = excess_over_cap(sales, total)
    max_a = None
    if ratio is not None and free_a:
        max_a = round(max(0.0, (allowed - proj_b - added) * cur_a / free_a), 2)
    return {
        "expected_sales_cr": cr(sales),
        "offer_free_goods_cr": cr(base),
        "requested_amounts_cr": cr(added),
        "total_free_goods_cr": cr(total),
        "total_free_pct": round(free_pct(sales, total), 2),
        "allowed_free_cr": cr(allowed),
        "excess_cr": cr(over),
        "headroom_cr": cr(max(0.0, allowed - total)),
        "within_cap": over == 0,
        "max_tier_a_free_per_10_within_cap": max_a,
    }


# ---------------------------------------------------------------------------------------
# Claims window rule. Plain Python, no model, tested in tests/test_window_rules.py.
#
# Policy section 5.2 (Doc 2): a near-expiry claim is valid only in the 90 days before the
# batch's expiry date; an expired claim only within 90 days after it. The expiry date is the
# one in the batch master (Doc 1 section 5.2; course answer in Discussion #58), not the date
# the stockist wrote on the claim form.
# ---------------------------------------------------------------------------------------
from datetime import date, datetime, timedelta  # noqa: E402

WINDOW_DAYS = 90
YEARS_COVERED = 2.5  # 1 Apr 2024 to 30 Sep 2026; yearly figure = period total / 2.5
DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%Y")


def parse_date(text) -> date | None:
    """Reads the date formats seen in the data pack. Returns None if it cannot be read."""
    if text is None:
        return None
    t = str(text).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def normalise_claim_type(text) -> str | None:
    """'near expiry', 'Expired', ... -> the label used in the register, or None."""
    if not text:
        return None
    t = str(text).lower()
    if "near" in t:
        return "Near expiry"
    if "expired" in t:
        return "Expired"
    if "breakage" in t:
        return "Breakage in transit"
    if "short" in t:
        return "Short supply"
    return None


def days_from_expiry(claim_date: date, expiry: date) -> int:
    """Negative = claim raised before expiry, positive = after."""
    return (claim_date - expiry).days


def window_check(claim_type: str | None, claim_date: date, expiry: date) -> dict:
    """One claim against the 90-day window. Returns outcome (pass / reject / escalate), a code and the reason.

    Near expiry: valid from 90 days before expiry up to the expiry date.
    Expired:     valid from the day after expiry up to 90 days after.
    A near-expiry claim raised after expiry, or an expired claim raised before it, is a label
    problem and goes to a person (escalate). Other claim types are not covered by this rule yet.
    """
    d = days_from_expiry(claim_date, expiry)
    base = {"days_from_expiry": d, "valid_from": (expiry - timedelta(days=WINDOW_DAYS)).isoformat(),
            "valid_until": (expiry + timedelta(days=WINDOW_DAYS)).isoformat()}
    if claim_type == "Near expiry":
        if -WINDOW_DAYS <= d <= 0:
            return {**base, "outcome": "pass", "code": "OK",
                    "reason": f"Raised {-d} days before expiry, inside the 90-day near-expiry window."}
        if d < -WINDOW_DAYS:
            return {**base, "outcome": "reject", "code": "TOO_EARLY",
                    "reason": f"Raised {-d} days before expiry. A near-expiry claim is valid only in the 90 days before expiry "
                              f"(from {base['valid_from']})."}
        if d <= WINDOW_DAYS:
            return {**base, "outcome": "escalate", "code": "AFTER_EXPIRY",
                    "reason": f"Labelled near expiry but raised {d} days after expiry. It would fit an expired claim (within 90 days "
                              f"after expiry), so a person should confirm the claim type."}
        return {**base, "outcome": "reject", "code": "TOO_LATE",
                "reason": f"Raised {d} days after expiry. Even as an expired claim, the window closed 90 days after expiry "
                          f"({base['valid_until']})."}
    if claim_type == "Expired":
        if 1 <= d <= WINDOW_DAYS:
            return {**base, "outcome": "pass", "code": "OK",
                    "reason": f"Raised {d} days after expiry, inside the 90-day expired-claim window."}
        if d > WINDOW_DAYS:
            return {**base, "outcome": "reject", "code": "TOO_LATE",
                    "reason": f"Raised {d} days after expiry. An expired claim is valid only within 90 days after expiry "
                              f"(until {base['valid_until']})."}
        return {**base, "outcome": "escalate", "code": "TYPE_MISMATCH",
                "reason": "Labelled expired, but the batch had not expired on the claim date. A person should confirm the claim type."}
    return {**base, "outcome": "escalate", "code": "NOT_COVERED",
            "reason": "The window check covers near-expiry and expired claims only. Other claim types are not checked yet."}


def window_group(code: str) -> str:
    """Where a failed claim goes in the recovery list.

    firm:    outside the window on any reading (more than 90 days after expiry).
    confirm: needs the claims team to confirm first (raised too early, or a label that may be wrong).
    """
    return "firm" if code == "TOO_LATE" else "confirm"
