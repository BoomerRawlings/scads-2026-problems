"""Regression tests for corrections against effective, dated ancestry."""
import pytest

from orggraph.store import Conflict, Store


def edge(subject, parent, start="2026-01-01", end=None, **extra):
    return {"id": f"{subject}-{parent}-{start}", "subject": subject, "object": parent, "relation": "reports_to", "origin": "source", "reporting_type": "primary", "valid_from": start, "valid_to": end, "evidence_ids": [], "review_status": "unreviewed", **extra}


def workspace(tmp_path, assertions):
    store = Store(tmp_path / "temporal.sqlite3")
    store.import_dataset({"schema_version": 1, "corpus": {"id": "temporal-test", "name": "Fictional temporal test", "synthetic": True}, "entities": [{"id": key, "name": key, "type": "person", "aliases": []} for key in "abcd"], "messages": [], "assertions": assertions, "evidence": []})
    return store


def replace(store, subject, parent, start="2026-01-01", end=None):
    return store.review({"base_revision": store.workspace()["revision"], "subject": subject, "object": parent, "action": "replace", "valid_from": start, "valid_to": end, "reason": "Audited correction"})


def test_superseded_source_link_does_not_invent_a_cycle(tmp_path):
    store = workspace(tmp_path, [edge("b", "a")])
    replace(store, "b", "c")
    replace(store, "a", "b")
    assert store.detail("a")["manager"]["object"] == "b"
    assert store.detail("b")["manager"]["object"] == "c"


def test_temporal_override_only_removes_cycle_inside_its_interval(tmp_path):
    store = workspace(tmp_path, [edge("b", "a")])
    replace(store, "b", "c", start="2026-06-01", end="2026-09-01")
    replace(store, "a", "b", start="2026-06-01", end="2026-09-01")
    with pytest.raises(Conflict, match="cycle"):
        replace(store, "a", "b", start="2026-05-01", end="2026-07-01")
    with pytest.raises(Conflict, match="cycle"):
        replace(store, "a", "b", start="2026-08-01", end="2026-10-01")


def test_disjoint_half_open_intervals_do_not_cycle(tmp_path):
    store = workspace(tmp_path, [edge("b", "a", end="2026-06-01")])
    replace(store, "a", "b", start="2026-06-01")


def test_true_multihop_cycle_is_rejected_without_revision_change(tmp_path):
    store = workspace(tmp_path, [edge("b", "c"), edge("c", "a")])
    revision = store.workspace()["revision"]
    with pytest.raises(Conflict, match="cycle"):
        replace(store, "a", "b")
    assert store.workspace()["revision"] == revision


def test_unknown_date_source_not_assumed_active_in_a_dated_cycle(tmp_path):
    store = workspace(tmp_path, [edge("b", "a", start=None)])
    replace(store, "a", "b", start="2026-06-01")


def test_undated_exploration_still_rejects_a_cycle(tmp_path):
    store = workspace(tmp_path, [edge("b", "a", start=None)])
    with pytest.raises(Conflict, match="cycle"):
        replace(store, "a", "b", start=None)


def test_undo_restores_previous_cycle_constraint(tmp_path):
    store = workspace(tmp_path, [edge("b", "a")])
    review = replace(store, "b", "c")["event"]
    store.review({"base_revision": store.workspace()["revision"], "subject": "b", "action": "undo", "event_id": review["id"], "reason": "Correction withdrawn"})
    with pytest.raises(Conflict, match="cycle"):
        replace(store, "a", "b")


def test_rejected_source_not_used_as_effective_parent(tmp_path):
    source = edge("b", "a")
    store = workspace(tmp_path, [source])
    store.review({"base_revision": store.workspace()["revision"], "subject": "b", "action": "reject", "assertion_id": source["id"], "reason": "Disputed source"})
    replace(store, "a", "b")


def test_ambiguous_source_ancestry_does_not_create_a_hard_cycle(tmp_path):
    store = workspace(tmp_path, [edge("b", "a"), edge("b", "c")])
    replace(store, "a", "b")
    assert store.detail("b")["unresolved_reason"] == "conflicting_sources"


def test_weak_model_candidate_not_used_as_confirmed_ancestry(tmp_path):
    store = workspace(tmp_path, [edge("b", "a", origin="model", raw_score=.4, selection_hint=False)])
    replace(store, "a", "b")


def test_undo_cannot_reactivate_cycle_between_accepted_edits(tmp_path):
    store = workspace(tmp_path, [])
    replace(store, "b", "a")
    later = replace(store, "b", "c")["event"]
    replace(store, "a", "b")
    revision = store.workspace()["revision"]
    with pytest.raises(Conflict, match="cycle"):
        store.review({"base_revision": revision, "subject": "b", "action": "undo", "event_id": later["id"], "reason": "Revert latest correction"})
    assert store.workspace()["revision"] == revision
    assert store.detail("a")["manager"]["object"] == "b"
    assert store.detail("b")["manager"]["object"] == "c"
    assert not next(event for event in store.detail("b")["history"] if event["id"] == later["id"])["undone"]


def test_undo_old_overridden_review_does_not_check_its_obsolete_cycle(tmp_path):
    store = workspace(tmp_path, [])
    oldest = replace(store, "b", "a")["event"]
    replace(store, "b", "c")
    replace(store, "a", "b")
    store.review({"base_revision": store.workspace()["revision"], "subject": "b", "action": "undo", "event_id": oldest["id"], "reason": "Remove obsolete review"})
    assert store.detail("a")["manager"]["object"] == "b"
    assert store.detail("b")["manager"]["object"] == "c"


def test_undo_reactivation_respects_disjoint_accepted_intervals(tmp_path):
    store = workspace(tmp_path, [])
    replace(store, "b", "a", start="2026-01-01", end="2026-06-01")
    later = replace(store, "b", "c", start="2026-01-01", end="2026-06-01")["event"]
    replace(store, "a", "b", start="2026-06-01")
    store.review({"base_revision": store.workspace()["revision"], "subject": "b", "action": "undo", "event_id": later["id"], "reason": "Revert historical review"})


def test_undo_undated_reactivation_checks_accepted_cycle(tmp_path):
    store = workspace(tmp_path, [])
    replace(store, "b", "a", start=None)
    later = replace(store, "b", "c", start=None)["event"]
    replace(store, "a", "b", start=None)
    with pytest.raises(Conflict, match="cycle"):
        store.review({"base_revision": store.workspace()["revision"], "subject": "b", "action": "undo", "event_id": later["id"], "reason": "Revert undated review"})
