"""The API runs the whole graph with a fake model. No key, no cost."""
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import agent.graph as g
from app import app


class FakeLLM:
    """Returns the scripted replies in order: first the 'understand' JSON, then the explanation."""

    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return AIMessage(content=self.replies.pop(0))


def ask(monkeypatch, fake, question="x"):
    monkeypatch.setattr(g, "get_llm", lambda: fake)
    return TestClient(app).post("/api/ask", json={"question": question})


def test_route_a_one_quarter(monkeypatch):
    fake = FakeLLM('{"route": "A", "period": "Q3 FY25", "requests": []}', "Free goods were 4.95% of sales.")
    body = ask(monkeypatch, fake).json()
    assert '"free_pct": 4.95' in body["evidence"][0]
    assert '"excess_cr": 1.1' in body["evidence"][0]
    assert body["result"]["route"] == "A" and body["result"]["quarter"] == "Q3 FY25"
    assert body["show_table"] is False
    assert body["answer"].endswith("Sales, the Controller and the CFO decide.")
    assert body["model_calls"] == 2
    assert body["elapsed_ms"] >= 0
    assert body["total_tokens"] == 0


def test_route_a_whole_period(monkeypatch):
    fake = FakeLLM('{"route": "A", "period": null, "requests": []}', "Seven quarters were over.")
    body = ask(monkeypatch, fake).json()
    assert '"total_excess_cr": 3.95' in body["evidence"][0]
    assert body["show_table"] is True


def test_route_b_planned_offer(monkeypatch):
    fake = FakeLLM('{"route": "B", "period": "Q3 FY25", "requests": [{"tier_a_free": 1}]}', "It would stay under the cap.")
    body = ask(monkeypatch, fake).json()
    assert '"within_cap": true' in body["evidence"][0]
    assert "assumptions" in body["evidence"][0]


def test_route_b_rupee_amount_for_a_month(monkeypatch):
    fake = FakeLLM('{"route": "B", "period": "December 2026", "requests": [{"amount_cr": 1.2}]}', "Within the cap.")
    ev = ask(monkeypatch, fake).json()["evidence"][0]
    assert '"requested_for": "Q3 FY27"' in ev and '"basis_quarter": "Q3 FY27"' in ev and '"history"' in ev


def test_route_b_several_requests_are_added_together(monkeypatch):
    fake = FakeLLM('{"route": "B", "period": "December 2026", "requests": [{"tier_a_free": 1.5}, {"amount_cr": 0.3}]}', "Over by a little.")
    ev = ask(monkeypatch, fake).json()["evidence"][0]
    assert '"total_free_goods_cr": 1.5' in ev and '"within_cap": true' in ev


def test_route_b_without_an_offer_asks_for_it(monkeypatch):
    fake = FakeLLM('{"route": "B", "period": null, "requests": []}')
    body = ask(monkeypatch, fake).json()
    assert "Tell me the request" in body["answer"]
    assert body["model_calls"] == 1


def test_other_questions_are_declined_without_a_second_model_call(monkeypatch):
    fake = FakeLLM('{"route": "other"}')
    body = ask(monkeypatch, fake).json()
    assert "3% scheme cap" in body["answer"]
    assert body["evidence"] == [] and body["model_calls"] == 1


def test_unreadable_model_output_is_declined_not_crashed(monkeypatch):
    fake = FakeLLM("sorry, I cannot do that")
    assert ask(monkeypatch, fake).status_code == 200


def test_health():
    assert TestClient(app).get("/api/health").json()["ok"] is True
