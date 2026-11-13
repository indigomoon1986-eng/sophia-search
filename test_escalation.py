#!/usr/bin/env python3
"""Tests for the Sophia escalation hook."""

import json
from escalation import (maybe_escalate, set_sophia_caller, get_escalation_log,
                        EscalationContext, _parse_sophia_response, _dispatch_action)


def test_local_routing_still_works():
    r = maybe_escalate("score 71 87 103")
    assert r["source"] == "local"
    assert r["result"]["score"] > 0.9
    print("PASS local routing")


def test_escalation_with_mock_sophia():
    def mock_sophia(prompt: str) -> str:
        assert "71" in prompt or "query" in prompt.lower()
        return json.dumps({"action": "score_triplet", "frequencies": [71, 87, 103]})

    set_sophia_caller(mock_sophia)
    r = maybe_escalate("tell me something interesting about the Fudan lines", force=True)
    assert r["source"] == "sophia"
    assert r["sophia_action"]["action"] == "score_triplet"
    assert r["result"]["score"] > 0.9
    print("PASS escalation with mock Sophia")


def test_unparseable_sophia_response():
    set_sophia_caller(lambda p: "I have no idea what you mean, sorry")
    r = maybe_escalate("ambiguous query here", force=True)
    assert r["source"] == "escalation_unparseable"
    assert "raw" in r
    print("PASS unparseable handling")


def test_sophia_failure_graceful():
    def boom(prompt: str):
        raise ConnectionError("Sophia is down")
    set_sophia_caller(boom)
    r = maybe_escalate("anything", force=True)
    assert r["source"] == "escalation_failed"
    assert "error" in r
    print("PASS Sophia failure graceful")


def test_parse_sophia_response_embedded_json():
    raw = "Sure thing. {\"action\": \"breathing\", \"density_shift\": -0.35} Hope that helps."
    obj = _parse_sophia_response(raw)
    assert obj["action"] == "breathing"
    assert obj["density_shift"] == -0.35
    print("PASS embedded JSON parse")


def test_dispatch_clarify():
    r = _dispatch_action({"action": "clarify", "question": "which mitochondria?"})
    assert r["clarification_needed"] == "which mitochondria?"
    print("PASS clarify dispatch")


def test_escalation_log_audit():
    set_sophia_caller(lambda p: json.dumps({"action": "trap_check", "frequencies": [87]}))
    maybe_escalate("is 87 a false positive", force=True)
    log = get_escalation_log()
    assert len(log) >= 1
    assert log[-1]["resolved"] is True
    print("PASS escalation log audit")


if __name__ == "__main__":
    test_local_routing_still_works()
    test_escalation_with_mock_sophia()
    test_unparseable_sophia_response()
    test_sophia_failure_graceful()
    test_parse_sophia_response_embedded_json()
    test_dispatch_clarify()
    test_escalation_log_audit()
    print("ALL TESTS PASSED")
