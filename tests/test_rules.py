"""Known answers for the scheme cap. Each rule has a test. No API key needed."""
from agent import rules, tools


def test_free_pct_q3_fy25():
    sales, free = tools._quarters()["Q3 FY25"]
    assert round(rules.free_pct(sales, free), 2) == 4.95


def test_excess_q3_fy25_is_1_10_crore():
    sales, free = tools._quarters()["Q3 FY25"]
    assert rules.cr(rules.excess_over_cap(sales, free)) == 1.10


def test_q2_fy27_is_under_the_cap():
    sales, free = tools._quarters()["Q2 FY27"]
    assert round(rules.free_pct(sales, free), 2) == 2.82
    assert rules.excess_over_cap(sales, free) == 0


def test_q3_fy27_is_under_the_cap():
    sales, free = tools._quarters()["Q3 FY27"]
    assert round(rules.free_pct(sales, free), 2) == 2.92
    assert rules.excess_over_cap(sales, free) == 0


def test_excess_is_never_negative():
    assert rules.excess_over_cap(100.0, 1.0) == 0


def test_seven_quarters_over_cap_total_3_95_crore():
    s = tools.scheme_summary()
    assert s["quarters_over_cap"] == ["Q3 FY25", "Q4 FY25", "Q1 FY26", "Q2 FY26", "Q3 FY26", "Q4 FY26", "Q1 FY27"]
    assert s["total_excess_cr"] == 3.95
    assert s["excess_per_year_cr"] == 1.44


def test_quarter_names_are_normalised():
    assert rules.normalise_quarter("q3 fy2025") == "Q3 FY25"
    assert rules.normalise_quarter("FY25 Q3") == "Q3 FY25"
    assert rules.normalise_quarter("sometime last year") is None


def test_planned_offer_same_as_today_matches_actual():
    p = tools.planned_offer(2, None, "Q3 FY25")
    assert p["projected_free_pct"] == 4.95 and p["projected_excess_cr"] == 1.10


def test_planned_10_plus_1_is_under_the_cap_and_10_plus_2_is_over():
    assert tools.planned_offer(1, None, "Q3 FY25")["over_cap"] is False
    assert tools.planned_offer(2, None, "Q3 FY25")["over_cap"] is True


def test_largest_tier_a_offer_within_cap_is_found():
    best = tools.planned_offer(2, None, "Q3 FY25")["max_tier_a_free_per_10_within_cap"]
    assert tools.planned_offer(best, None, "Q3 FY25")["projected_excess_cr"] == 0
    assert tools.planned_offer(best + 0.2, None, "Q3 FY25")["over_cap"] is True


def test_unknown_quarter_is_reported_not_invented():
    assert tools.scheme_quarter("Q1 FY40")["found"] is False


def test_missing_planned_offer_asks_for_it():
    assert tools.planned_offer(None)["found"] is False


def test_month_and_year_become_a_fiscal_quarter():
    assert rules.quarter_from_text("December 2026") == "Q3 FY27"
    assert rules.quarter_from_text("Dec 2026") == "Q3 FY27"
    assert rules.quarter_from_text("March 2026") == "Q4 FY26"
    assert rules.quarter_from_text("April 2026") == "Q1 FY27"
    assert rules.quarter_from_text("Q3 FY25") == "Q3 FY25"
    assert rules.quarter_from_text("soon") is None


def test_ratio_request_for_next_quarter_uses_latest_full_quarter():
    r = tools.assess_requests([{"tier_a_free": 2}], "December 2026")
    assert r["requested_for"] == "Q3 FY27" and r["basis_quarter"] == "Q3 FY27"
    assert r["total_free_pct"] == 2.92 and r["excess_cr"] == 0.0


def test_rupee_amount_is_the_whole_free_goods_by_default():
    r = tools.assess_requests([{"amount_cr": 1.2}], "December 2026")
    assert r["total_free_goods_cr"] == 1.2 and r["within_cap"] is True and r["headroom_cr"] == 0.32


def test_extra_amount_sits_on_top_of_the_current_offer():
    r = tools.assess_requests([{"amount_cr": 0.5, "extra": True}], "Q3 FY27")
    assert r["total_free_goods_cr"] == 1.98 and r["excess_cr"] == 0.46


def test_several_requests_add_up_against_one_cap():
    r = tools.assess_requests([{"tier_a_free": 1.5}, {"amount_cr": 0.3}], "December 2026")
    assert r["total_free_goods_cr"] == 1.5 and r["excess_cr"] == 0.0 and r["within_cap"] is True


def test_request_answer_carries_the_history():
    h = tools.assess_requests([{"amount_cr": 1.0}], "December 2026")["history"]
    assert h == {"quarters_over_cap": 7, "total_excess_cr": 3.95, "excess_per_year_cr": 1.44}


def test_unreadable_period_and_empty_request_are_reported():
    assert tools.assess_requests([{"amount_cr": 1.0}], "whenever")["found"] is False
    assert tools.assess_requests([], "December 2026")["found"] is False
