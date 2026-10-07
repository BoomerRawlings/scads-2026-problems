"""Scale invariants without machine-dependent timing assertions."""

from orggraph.inference import infer


def test_large_roster_resolves_named_manager_without_dense_candidates():
    entities = [{"id": f"p-{index:05}", "name": f"Person {index:05}", "type": "person"} for index in range(10_000)]
    data = {
        "corpus": {"id": "large-roster", "synthetic": True},
        "entities": entities,
        "messages": [{
            "id": "explicit", "sender": "p-00000", "to": ["p-00001"], "cc": [],
            "timestamp": "2026-03-01T12:00:00Z", "source_ref": "fictional://explicit",
            "body": "I report directly to Person 09999.",
        }],
    }
    result = infer(data)
    assert len(result["metrics"]) == 10_000
    assert len(result["assertions"]) == 3
    selected = [item for item in result["assertions"] if item["selection_hint"]]
    assert [(item["subject"], item["object"]) for item in selected] == [("p-00000", "p-09999")]
    assert len(result["unresolved"]) == 9_999
    assert all(item["candidate_probability"] is None for item in result["assertions"])


def test_approval_uses_one_distinct_direct_person_recipient():
    data = {
        "corpus": {"id": "approval-recipients", "synthetic": True},
        "entities": [{"id": ident, "name": ident, "type": "person"} for ident in ("sender", "approver", "observer")],
        "messages": [{
            "id": "approval", "sender": "sender",
            "to": ["sender", "approver", "approver", "external-unknown"], "cc": ["observer"],
            "timestamp": "2026-03-01T12:00:00Z", "source_ref": "fictional://approval",
            "body": "Please approve the release.",
        }],
    }
    result = infer(data)
    authority = [item for item in result["assertions"] if item["relation"] == "higher_authority_than"]
    assert [(item["subject"], item["object"]) for item in authority] == [("approver", "sender")]
    assert not any(item["selection_hint"] for item in result["assertions"])
