"""The 90-day window rule, one test per edge. No model, no key."""
from datetime import date

import pytest

from agent import rules

EXPIRY = date(2026, 3, 31)


def day(offset: int) -> date:
    """A claim date `offset` days from expiry (negative = before)."""
    from datetime import timedelta
    return EXPIRY + timedelta(days=offset)


@pytest.mark.parametrize("offset,outcome,code", [
    (-91, "reject", "TOO_EARLY"),      # one day too early
    (-90, "pass", "OK"),               # first valid day
    (-1, "pass", "OK"),
    (0, "pass", "OK"),                 # expiry day itself is still near expiry
    (1, "escalate", "AFTER_EXPIRY"),   # near-expiry label, raised after expiry
    (90, "escalate", "AFTER_EXPIRY"),  # still inside 90 days after expiry: label question, not a breach
    (91, "reject", "TOO_LATE"),        # outside on any reading
])
def test_near_expiry_edges(offset, outcome, code):
    res = rules.window_check("Near expiry", day(offset), EXPIRY)
    assert (res["outcome"], res["code"]) == (outcome, code)


@pytest.mark.parametrize("offset,outcome,code", [
    (-5, "escalate", "TYPE_MISMATCH"),  # not yet expired
    (0, "escalate", "TYPE_MISMATCH"),
    (1, "pass", "OK"),
    (90, "pass", "OK"),
    (91, "reject", "TOO_LATE"),
])
def test_expired_edges(offset, outcome, code):
    res = rules.window_check("Expired", day(offset), EXPIRY)
    assert (res["outcome"], res["code"]) == (outcome, code)


def test_other_claim_types_are_not_covered_so_they_are_escalated_not_rejected():
    for t in ("Breakage in transit", "Short supply", None):
        assert rules.window_check(t, day(-300), EXPIRY)["code"] == "NOT_COVERED"


def test_too_early_reason_gives_the_first_valid_date():
    res = rules.window_check("Near expiry", day(-120), EXPIRY)
    assert res["valid_from"] == "2025-12-31" and "2025-12-31" in res["reason"]


def test_groups_firm_only_when_late_on_any_reading():
    assert rules.window_group("TOO_LATE") == "firm"
    assert rules.window_group("TOO_EARLY") == "confirm"
    assert rules.window_group("AFTER_EXPIRY") == "confirm"


def test_dates_in_the_three_pack_formats_all_read():
    assert rules.parse_date("30-09-2025") == rules.parse_date("2025-09-30") == rules.parse_date("30-Sep-2025")
    assert rules.parse_date("not a date") is None and rules.parse_date(None) is None


def test_claim_type_labels():
    assert rules.normalise_claim_type("near expiry") == "Near expiry"
    assert rules.normalise_claim_type("Expired") == "Expired"
    assert rules.normalise_claim_type("short supply") == "Short supply"
    assert rules.normalise_claim_type("something else") is None
