"""Behavioral acceptance checks, not claims of real-world inference accuracy."""
from copy import deepcopy

import pytest

from orggraph.inference import infer


def dataset(messages=None):
    return {
        "corpus": {"id": "test", "name": "Fictional test", "synthetic": True},
        "entities": [
            {"id": "p-a", "name": "Ari Lee", "type": "person", "unit_id": "u-1"},
            {"id": "p-b", "name": "Blair King", "type": "person", "email": "blair@example.test", "unit_id": "u-1"},
            {"id": "p-c", "name": "Casey Wu", "type": "person", "unit_id": "u-2"},
            {"id": "p-d", "name": "Devin Snow", "type": "person"},
            {"id": "shared", "name": "Helpdesk", "type": "shared_mailbox"},
            {"id": "u-1", "name": "Research", "type": "unit"},
            {"id": "u-2", "name": "Design", "type": "unit"},
        ],
        "messages": messages or [], "labels": [], "assertions": [],
    }


def message(mid="m1", sender="p-a", to=None, body="", timestamp="2026-03-01T12:00:00Z", cc=None):
    return {"id": mid, "sender": sender, "to": to if to is not None else ["p-b"], "cc": cc or [], "body": body, "subject": "Project", "timestamp": timestamp, "source_ref": f"fixture/{mid}.eml"}


def selected(result):
    return [item for item in result["assertions"] if item["selection_hint"]]


def test_headers_only_preserves_unknown_and_reproducible_aggregate():
    data = dataset([message("m1"), message("m2", "p-b", ["p-a"]), message("m3", "p-a", ["p-c", "p-c"], cc=["p-c"])])
    result = infer(data)
    assert not selected(result)
    assert result["unresolved"]["p-a"] == "weak_evidence"
    assert all(item["kind"] == "communication_aggregate" for item in result["evidence"])
    aggregate = next(item for item in result["evidence"] if item["details"]["subject"] == "p-a" and item["details"]["candidate"] == "p-b")
    assert aggregate["message_ids"] == ["m1", "m2"]
    assert aggregate["details"]["sent_to_candidate"] == 1
    assert aggregate["details"]["received_from_candidate"] == 1
    assert aggregate["details"]["total_outgoing_interactions"] == 2
    assert aggregate["details"]["outgoing_share"] == 0.5
    assert result["metrics"]["p-a"] == {"breadth": 2, "sent": 2, "received": 1, "cross_unit": 1, "cross_unit_eligible": 3}
    assert result["model"]["calibration_status"] == "uncalibrated"
    assert all(item["candidate_probability"] is None and item["selected_probability"] is None for item in result["assertions"])


@pytest.mark.parametrize("text,expected", [
    ("I report directly to Blair King.", "I report directly to Blair King"),
    ("Hello.\nI report to Blair King.\nThanks!", "I report to Blair King"),
    ("Blair King is my line manager.", "Blair King is my line manager"),
    ("Blair King is my direct manager.", "Blair King is my direct manager"),
    ("I report to blair@example.test.", "I report to blair@example.test"),
])
def test_explicit_self_report_exact_attributable_span(text, expected):
    result = infer(dataset([message(body=text)]))
    chosen = selected(result)
    assert len(chosen) == 1
    assert (chosen[0]["subject"], chosen[0]["object"], chosen[0]["relation"]) == ("p-a", "p-b", "reports_to")
    assert chosen[0]["valid_from"] == "2026-03-01"
    assert chosen[0]["temporal_basis"] == "observed_statement"
    spans = [item for item in result["evidence"] if item["kind"] == "message_span"]
    assert len(spans) == 1
    span = spans[0]
    assert span["text"] == expected == text[span["start"]:span["end"]]
    assert span["source_ref"] == "fixture/m1.eml"
    assert span["details"]["speaker"] == "p-a"
    assert span["id"] in chosen[0]["evidence_ids"]


@pytest.mark.parametrize("body", [
    "> I report to Blair King.",
    'Ari said: "I report to Blair King."',
    '"I report to Blair King."',
    "'I report to Blair King.'",
    "On Tuesday Ari wrote:\nI report to Blair King.",
    "-----Original Message-----\nI report to Blair King.",
    "From: Ari Lee\nI report to Blair King.",
    "If I report to Blair King, will I move teams?",
    "I report to the team every Friday.",
    "I report on Blair King's project.",
    "Blair King said I report to Casey Wu.",
    "I report to Unknown Person.",
    "I report to Ari Lee.",
])
def test_quotes_hypotheticals_generic_reporting_and_self_edges_not_claims(body):
    result = infer(dataset([message(body=body)]))
    assert not selected(result)
    assert not [item for item in result["evidence"] if item["kind"] == "message_span"]


def test_authority_remains_separate_from_direct_manager():
    result = infer(dataset([message(body="Please approve the release before Friday.")]))
    authority = [item for item in result["assertions"] if item["relation"] == "higher_authority_than"]
    assert len(authority) == 1
    assert (authority[0]["subject"], authority[0]["object"]) == ("p-b", "p-a")
    assert authority[0]["selection_hint"] is False
    assert not selected(result)
    plain = infer(dataset([message()]))
    direct = lambda output: {(item["subject"], item["object"]): item["raw_score"] for item in output["assertions"] if item["relation"] == "reports_to"}
    assert direct(result) == direct(plain)


def test_ambiguous_shared_name_does_not_pick_arbitrary_person():
    data = dataset([message(body="I report to Blair King.")])
    data["entities"][2]["name"] = "Blair King"
    assert not selected(infer(data))


def test_unknown_person_remains_searchable_without_invented_outside_corpus_claim():
    result = infer(dataset())
    assert result["unresolved"]["p-d"] == "empty_candidate_set"
    assert result["metrics"]["p-d"]["breadth"] == 0
    assert not result["groups"]
    assert not result["assertions"]


def test_future_evidence_excluded_and_undated_stays_explicit():
    data = dataset([
        message("old", body="I report to Blair King.", timestamp="2026-01-01T12:00:00Z"),
        message("future", to=["p-c"], body="I report to Casey Wu.", timestamp="2026-07-01T12:00:00Z"),
        message("undated", "p-d", ["p-b"], "I report to Blair King.", timestamp=None),
    ])
    result = infer(data, as_of="2026-03-01")
    assert [(item["subject"], item["object"]) for item in selected(result)] == [("p-a", "p-b")]
    assert result["unresolved"]["p-d"] == "unknown_dates"
    assert all("future" not in item["message_ids"] for item in result["evidence"])
    undated = next(item for item in result["assertions"] if item["subject"] == "p-d")
    assert undated["valid_from"] is None
    assert result["model"]["window"]["undated_messages_included"] == 1
    assert any(item["subject"] == "p-d" for item in selected(infer(data)))


def test_competing_direct_claims_abstain():
    result = infer(dataset([message("one", body="I report to Blair King."), message("two", to=["p-c"], body="I report to Casey Wu.")]))
    assert result["unresolved"]["p-a"] == "close_alternatives"
    assert not selected(result)


def test_negative_statement_prevents_strong_selection():
    result = infer(dataset([message("one", body="I report to Blair King."), message("two", body="I no longer report to Blair King.")]))
    assert not selected(result)
    assert result["unresolved"]["p-a"] == "conflicting_evidence"
    candidate = next(item for item in result["assertions"] if item["subject"] == "p-a")
    assert candidate["signals"]["contradicting_statement_count"] == 1


def test_labels_and_human_assertions_cannot_leak_into_inference():
    data = dataset([message(body="I report to Blair King.")])
    expected = infer(data)
    modified = deepcopy(data)
    modified["labels"] = [{"subject": "p-a", "object": "p-c", "relation": "reports_to", "label": 1}]
    modified["assertions"] = [{"subject": "p-a", "object": "p-c", "origin": "source", "relation": "reports_to"}]
    modified["gold"] = {"p-a": "p-c"}
    assert infer(modified) == expected
    assert data["assertions"] == []


def test_groups_are_deterministic_and_not_formal_memberships():
    data = dataset([message("m1"), message("m2", "p-b", ["p-a"]), message("m3", "p-c", ["p-d"])])
    first = infer(data)
    reversed_input = deepcopy(data)
    reversed_input["messages"].reverse()
    reversed_input["entities"].reverse()
    assert infer(reversed_input) == first
    assert len(first["groups"]) == 2
    assert all(group["kind"] == "inferred" and group["formal_unit"] is False for group in first["groups"])
    assert all(0 <= group["stability"]["mean_best_jaccard"] <= 1 for group in first["groups"])
    assert all(item["relation"] != "member_of" for item in first["assertions"])


def test_shared_mailboxes_broadcasts_and_duplicate_messages_do_not_inflate_metrics():
    direct = message()
    data = dataset([direct, deepcopy(direct), message("shared", "shared", ["p-a"], "I report to Blair King."), message("broadcast", to=[f"unknown-{index}" for index in range(21)] + ["p-b"], body="I report to Blair King.")])
    result = infer(data)
    assert result["metrics"]["p-a"]["sent"] == 1
    assert result["metrics"]["p-b"]["received"] == 1
    assert result["model"]["coverage"]["duplicate_message_ids"] == 1
    assert result["model"]["coverage"]["broadcast_messages_excluded"] == 1
    assert not selected(result)


def test_sparse_candidate_budget_retains_explicit_named_manager():
    data = dataset()
    data["entities"].extend({"id": f"neighbor-{index}", "type": "person", "name": f"Neighbor {index}"} for index in range(50))
    data["messages"] = [message(f"m{index}", to=[f"neighbor-{index}"]) for index in range(50)] + [message("explicit", to=[], body="I report to Blair King.")]
    result = infer(data)
    candidates = [item for item in result["assertions"] if item["subject"] == "p-a"]
    assert len(candidates) == 9
    assert [(item["subject"], item["object"]) for item in selected(result)] == [("p-a", "p-b")]


@pytest.mark.parametrize("kwargs", [{"threshold": -0.1}, {"margin": 2}, {"as_of": "tomorrow"}, {"as_of": "2026-01-01T00:00:00Z"}])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        infer(dataset(), **kwargs)


def calibration_fixture():
    records = [{"subject": f"fit-{index}", "object": "manager", "raw_score": index / 20, "label": int(index >= 10)} for index in range(20)]
    scope = {"corpus_id": "fictional", "model_id": "test-scorer", "relation": "reports_to", "population": "candidate", "policy_id": "test-candidates-v1", "window": {"as_of": "2026-03-01"}, "label_provenance": "synthetic software fixture; no validity claim"}
    return records, scope


def test_calibration_is_explicit_scoped_and_not_a_validation_claim():
    from orggraph.calibration import apply_calibrator, evaluate_calibrator, fit_calibrator

    records, scope = calibration_fixture()
    artifact = fit_calibrator(records, scope=scope, split_id="fit")
    applied = apply_calibrator(artifact, [{"raw_score": 0.8, "origin": "model"}, {"raw_score": 0.8, "origin": "analyst"}], scope=scope)
    assert 0 < applied[0]["candidate_probability"] < 1
    assert applied[0]["selected_probability"] is None
    assert applied[0]["calibration_status"] == "fitted_unvalidated"
    assert applied[1]["candidate_probability"] is None
    transfer = apply_calibrator(artifact, [{"raw_score": 0.8}], scope={**scope, "corpus_id": "unlabeled-target"})
    assert transfer[0]["candidate_probability"] is None
    assert transfer[0]["calibration_status"] == "outside_calibration_scope"
    evaluation = [{**record, "subject": record["subject"].replace("fit", "test")} for record in records]
    report = evaluate_calibrator(artifact, evaluation, scope=scope, split_id="independent-test")
    assert report["count"] == 20
    assert 0 <= report["brier_score"] <= 1
    assert report["acceptance"] == "not_assessed"
    assert sum(item["count"] for item in report["reliability"]) == 20
    assert artifact["status"] == "fitted_unvalidated"


def test_calibration_rejects_missing_labels_duplicates_and_split_leakage():
    from orggraph.calibration import evaluate_calibrator, fit_calibrator

    records, scope = calibration_fixture()
    artifact = fit_calibrator(records, scope=scope, split_id="fit")
    with pytest.raises(ValueError, match="overlap"):
        evaluate_calibrator(artifact, records, scope=scope, split_id="renamed-test")
    with pytest.raises(ValueError, match="Duplicate"):
        fit_calibrator(records + [records[0]], scope=scope, split_id="fit")
    with pytest.raises(ValueError, match="explicit binary label"):
        fit_calibrator([{key: value for key, value in record.items() if key != "label"} for record in records], scope=scope, split_id="fit")
    with pytest.raises(ValueError, match="training"):
        fit_calibrator(records, scope=scope, split_id="fit", training_relationship_keys=artifact["relationship_keys"])
