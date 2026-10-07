"""Behavioral guarantees for the connected synthetic communication corpus."""
from collections import Counter
import hashlib
import json

import pytest

from orggraph.demo import demo_dataset
from orggraph.ingest import parse_bytes


@pytest.fixture(scope="module")
def large_demo():
    return demo_dataset(person_count=10_000)


def test_default_fixture_is_unchanged():
    encoded = json.dumps(demo_dataset(), sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(encoded).hexdigest() == "c1bc74cc7be3a8174a6ba3a118e22f51b8e6c91f9e4bf52422fd7e0d7de5777a"
    assert demo_dataset() == demo_dataset(person_count=72)


@pytest.mark.parametrize("count", [71, 100_001, 10000.0, "10000", True, None])
def test_scale_rejects_invalid_person_counts(count):
    with pytest.raises(ValueError, match="integer between 72 and 100000"):
        demo_dataset(person_count=count)


def test_scale_accepts_small_nonround_expansion():
    data = demo_dataset(person_count=73)
    assert sum(e["type"] == "person" for e in data["entities"]) == 73
    assert data["labels"][-1]["object"] == "research-00"
    assert data["corpus"]["generator"]["added_people"] == 1


def test_exact_person_count_and_preserved_records(large_demo):
    entities = large_demo["entities"]
    assert Counter(e["type"] for e in entities) == {"person": 10_000, "unit": 45, "shared_mailbox": 2}
    assert sum(bool(e.get("external")) for e in entities) == 2
    original = demo_dataset()
    for field in ("entities", "messages", "assertions", "evidence", "labels"):
        assert large_demo[field][:len(original[field])] == original[field]
    added_names = [e["name"] for e in entities[len(original["entities"]):] if e["type"] == "person"]
    assert len(added_names) == len(set(added_names))
    assert large_demo["corpus"]["synthetic"] is True
    assert large_demo["corpus"]["id"] != original["corpus"]["id"]


def test_scale_is_repeatable(large_demo):
    assert demo_dataset(person_count=10_000) == large_demo


def test_ids_and_dependency_closure(large_demo):
    for field in ("entities", "messages", "assertions", "evidence", "labels"):
        identifiers = [item["id"] for item in large_demo[field]]
        assert len(identifiers) == len(set(identifiers)), field
    entities = {item["id"]: item for item in large_demo["entities"]}
    evidence = {item["id"] for item in large_demo["evidence"]}
    source_messages = set()
    for message in large_demo["messages"]:
        assert message["sender"] in entities
        assert set(message["to"] + message["cc"]) <= entities.keys()
        assert message["source_message_id"] not in source_messages
        source_messages.add(message["source_message_id"])
    for assertion in large_demo["assertions"]:
        assert assertion["subject"] in entities and assertion["object"] in entities
        assert set(assertion["evidence_ids"]) <= evidence
        assert assertion["candidate_probability"] is None
        assert assertion["selected_probability"] is None
    for entity in entities.values():
        if entity.get("unit_id"):
            assert entities[entity["unit_id"]]["type"] == "unit"


def test_one_acyclic_multilevel_organization_and_partial_source_anchors(large_demo):
    parents = {label["subject"]: label["object"] for label in large_demo["labels"]}
    assert len(parents) == 9_993  # CEO, four original sparse people, and two externals have no gold manager.
    maximum_depth = 0
    for person in parents:
        seen = set()
        while person in parents:
            assert person not in seen
            seen.add(person)
            person = parents[person]
        assert person == "avery-stone"
        maximum_depth = max(maximum_depth, len(seen))
    assert maximum_depth >= 5
    sources = [a for a in large_demo["assertions"] if a["relation"] == "reports_to"]
    assert 10 < len(sources) < len(parents) // 20
    assert all(parents[a["subject"]] == a["object"] for a in sources)
    assert all(label["source_role"] == "fixture_validation_only" and label["independent_of_model_input"] for label in large_demo["labels"])


def test_real_traffic_includes_uncertainty_and_nonmanager_hub(large_demo):
    messages = large_demo["messages"]
    assert 60_000 < len(messages) < 100_000
    by_sender = Counter(message["sender"] for message in messages)
    new_people = {e["id"] for e in large_demo["entities"] if "-scale-" in e["id"]}
    assert new_people <= by_sender.keys()
    assert sum(not message["body"] for message in messages) >= 490
    assert sum(message["body"].startswith("> I report directly") for message in messages) >= 490
    assert sum("conflicting directory entries" in message["body"] for message in messages) >= 490
    assert sum("Please approve" in message["body"] for message in messages) >= 490
    assert sum("is my line manager" in message["body"] for message in messages) >= 7_000
    hub_senders = {message["sender"] for message in messages if "intelligence-05" in message["to"]}
    assert len(hub_senders) > 500
    assert not any(label["object"] == "intelligence-05" for label in large_demo["labels"])
    assert sum("shared-help" in message["to"] for message in messages) > 700


def test_full_corpus_passes_real_import_validation(large_demo):
    parsed = parse_bytes(json.dumps(large_demo).encode(), "meridian-10000.json")
    report = parsed["report"]
    assert report["quarantined"] == report["duplicate"] == report["unsupported"] == 0
    assert report["read"] == report["accepted"]
    for field in ("entities", "messages", "assertions", "evidence", "labels"):
        assert len(parsed["dataset"][field]) == len(large_demo[field])
