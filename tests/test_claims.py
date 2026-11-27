"""Claims tools and routes C and D. The recovery list numbers are pinned so a change shows up."""
from fastapi.testclient import TestClient

from agent import claims
from app import app
from tests.test_api import FakeLLM, ask


def test_intake_too_early_claim_is_rejected_with_the_valid_from_date():
    res = claims.check_claim("K2310149", "20-12-2024", "near expiry")  # expiry 31-03-2025 in the batch master
    assert res["outcome"] == "reject" and res["code"] == "TOO_EARLY"
    assert res["expiry_date"] == "2025-03-31" and res["days_from_expiry"] == -101
    assert res["valid_from"] == "2024-12-31"


def test_intake_claim_inside_the_window_passes():
    res = claims.check_claim("K2310149", "15-02-2025", "Near expiry")
    assert res["outcome"] == "pass"


def test_intake_expired_claim_after_90_days_is_rejected():
    res = claims.check_claim("K2330377", "21-07-2025", "Expired")
    assert res["outcome"] == "reject" and res["code"] == "TOO_LATE" and res["days_from_expiry"] == 112


def test_intake_batch_not_in_master_is_escalated_not_rejected():
    res = claims.check_claim("ZZ999", "21-07-2025", "Expired")
    assert res["outcome"] == "escalate" and res["code"] == "NO_BATCH"


def test_intake_asks_for_what_is_missing():
    assert "batch number" in claims.check_claim(None, "01-01-2026", "expired")["message"]
    assert "claim type" in claims.check_claim("K2310149", "01-01-2026", None)["message"]
    assert "date" in claims.check_claim("K2310149", "tomorrow-ish", "expired")["message"]


def test_recovery_list_numbers():
    s = claims.window_summary()
    assert s["verifiable_breaches"]["claims"] == 184
    assert s["firm_more_than_90_days_after_expiry"]["claims"] == 64
    assert s["confirm_with_claims_team"]["claims"] == 120
    assert s["confirm_breakdown"]["raised_more_than_90_days_before_expiry"]["claims"] == 101
    assert s["cannot_verify_batch_not_in_master"]["claims"] == 47
    assert s["pending_claims_outside_window_to_hold"]["claims"] == 45
    assert s["verifiable_breaches"]["value_lakh"] == 34.5


def test_intake_and_list_use_the_same_rule():
    """Every claim in the file must get the same answer when checked one at a time."""
    from agent import rules
    checked = 0
    for r in claims._rows():
        if r["group"] not in ("firm", "confirm"):
            continue
        res = claims.check_claim(r["batch_no"], rules.parse_date(r["claim_date"]).strftime("%d-%m-%Y"), r["claim_type"])
        assert res["code"] == r["code"], r["claim_no"]
        checked += 1
    assert checked == 184 + 45  # credited 184, pending 45 (3 of them have no stated value)


def test_route_c_through_the_api(monkeypatch):
    fake = FakeLLM('{"route": "C", "period": null, "requests": [], "claim": {"batch_no": "K2310149", "claim_date": "20-12-2024", "claim_type": "near expiry"}}',
                   "Reject: raised 101 days before expiry.")
    body = ask(monkeypatch, fake).json()
    assert '"outcome": "reject"' in body["evidence"][0] and '"days_from_expiry": -101' in body["evidence"][0]
    assert body["answer"].endswith("The claims team and the credit note owners decide.")
    assert body["model_calls"] == 2
    assert body["show_table"] is False


def test_route_c_missing_batch_asks_and_makes_no_second_model_call(monkeypatch):
    fake = FakeLLM('{"route": "C", "claim": {"batch_no": null, "claim_date": "20-12-2024", "claim_type": "expired"}}')
    body = ask(monkeypatch, fake).json()
    assert "batch number" in body["answer"] and body["model_calls"] == 1


def test_route_d_through_the_api(monkeypatch):
    fake = FakeLLM('{"route": "D", "period": null, "requests": [], "claim": null}', "184 claims broke the window.")
    body = ask(monkeypatch, fake).json()
    assert '"claims": 184' in body["evidence"][0] and "/api/recovery-list.csv" in body["evidence"][0]
    assert body["result"]["route"] == "D" and body["result"]["verifiable_breaches"]["claims"] == 184
    assert body["show_table"] is True


def test_scheme_answers_keep_their_own_closing_line(monkeypatch):
    fake = FakeLLM('{"route": "A", "period": "Q3 FY25", "requests": []}', "Over the cap.")
    assert ask(monkeypatch, fake).json()["answer"].endswith("Sales, the Controller and the CFO decide.")


def test_recovery_list_download():
    res = TestClient(app).get("/api/recovery-list.csv")
    assert res.status_code == 200 and res.text.startswith("claim_no,status")
