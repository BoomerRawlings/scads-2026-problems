from copy import deepcopy
import json

import pytest

from orggraph.store import Conflict, Store, dumps, project


def assertion(subject="a", manager="b", **kwargs):
    return {"id": f"{subject}-{manager}", "subject": subject, "relation": "reports_to", "object": manager,
            "origin": "model", "reporting_type": "primary", "valid_from": "2026-01-01", "valid_to": None,
            "raw_score": .9, "candidate_probability": None, "selected_probability": None,
            "calibration_status": "uncalibrated", "evidence_ids": ["span", "aggregate"],
            "review_status": "unreviewed", **kwargs}


def dataset():
    return {"schema_version": 1, "corpus": {"id": "test", "name": "Test organization", "synthetic": True},
            "entities": [{"id": i, "name": name, "type": "person", "aliases": []} for i, name in zip("abcd", ["Alice", "Bob", "Carol", "David"])],
            "messages": [{"id": "m1", "sender": "a", "to": ["b"], "cc": [], "timestamp": "2026-01-05T10:00:00Z", "body": "I report directly to Bob.", "raw_body_copy": "I report directly to Bob.", "subject": "Reporting", "source_ref": "mail:1"}],
            "assertions": [], "evidence": [], "labels": [{"subject": "a", "object": "b", "label": 1}]}


def result():
    return {"assertions": [assertion(), assertion(manager="c", raw_score=.6)],
            "evidence": [{"id": "span", "kind": "message_span", "source_ref": "mail:1", "text": "I report directly to Bob.", "available": True, "message_ids": ["m1"]},
                         {"id": "aggregate", "kind": "communication_aggregate", "source_ref": "corpus:test", "available": True, "message_ids": ["m1"], "details": {"source_refs": ["mail:1"]}}],
            "metrics": {}, "groups": [], "model": {"id": "test-baseline", "calibration_status": "uncalibrated"}}


def engine(data, **kwargs):
    assert "labels" not in data
    assert "assertions" not in data
    return result()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "graph.sqlite3")
    s.import_dataset(dataset())
    s.run_inference(base_revision=s.workspace()["revision"], engine=engine)
    return s


def review(s, action, **kwargs):
    return s.review({"action": action, "subject": "a", "reason": "Verified against directory", "base_revision": s.workspace()["revision"], **kwargs})


def test_idempotent_import_and_immutable_history(store):
    current = store.workspace()
    assert store.import_dataset(dataset())["duplicate"]
    assert store.workspace()["revision"] == current["revision"]
    assert store.detail("a")["manager"]["object"] == "b"
    assert store.detail("a", current["snapshots"][-1]["id"])["manager"] is None
    with pytest.raises(Conflict):
        store.import_dataset({**dataset(), "messages": []})


def test_rejection_survives_refresh_without_promoting_alternative_and_undo_restores(store):
    event = review(store, "reject", assertion_id="a-b")["event"]
    assert store.detail("a")["manager"] is None
    assert store.entities(status="reviewed")["total"] == store.workspace()["counts"]["reviewed"] == 1
    store.run_inference(base_revision=store.workspace()["revision"], engine=engine)
    assert store.detail("a")["manager"] is None
    assert store.detail("a")["unresolved_reason"] == "analyst_rejected"
    review(store, "undo", event_id=event["id"])
    assert store.detail("a")["manager"]["object"] == "b"
    assert store.detail("a")["history"][0]["undone"]


def test_replacement_persists_with_evidence_and_null_probabilities(store):
    event = review(store, "replace", object="d")["event"]
    store.run_inference(base_revision=store.workspace()["revision"], engine=engine)
    manager = store.detail("a")["manager"]
    assert manager["object"] == "d"
    assert manager["raw_score"] is manager["selected_probability"] is manager["candidate_probability"] is None
    assert manager["evidence"][0]["text"] == event["reason"]
    assert manager["evidence"][0]["kind"] == "analyst_reference"


def test_accept_keeps_original_evidence_after_model_changes(store):
    review(store, "accept", assertion_id="a-b")
    def changed(data, **kwargs):
        return {"assertions": [], "evidence": [], "model": {"id": "changed"}}
    store.run_inference(base_revision=store.workspace()["revision"], engine=changed)
    assert len(store.detail("a")["manager"]["evidence"]) == 2


def test_review_conflicts_cycles_and_idempotency(store):
    request = {"action": "replace", "subject": "a", "object": "d", "reason": "Directory", "base_revision": 2, "idempotency_key": "one"}
    store.review(request)
    assert store.review(request)["duplicate"]
    with pytest.raises(Conflict):
        store.review({**request, "object": "c"})
    with pytest.raises(Conflict):
        store.review({**request, "idempotency_key": "two"})
    with pytest.raises(ValueError):
        review(store, "replace", object="a")
    with pytest.raises(Conflict, match="cycle"):
        store.review({"action": "replace", "subject": "d", "object": "a", "reason": "Cycle", "base_revision": store.workspace()["revision"]})


def test_effective_intervals_half_open_and_unknown_date_abstention(store):
    review(store, "replace", object="d", valid_from="2026-03-01", valid_to="2026-04-01")
    for as_of, expected in [("2026-02-01", "b"), ("2026-03-01", "d"), ("2026-04-01", "b")]:
        store.run_inference(base_revision=store.workspace()["revision"], engine=engine, as_of=as_of)
        assert store.detail("a")["manager"]["object"] == expected
    _, selected, unresolved = project(dataset()["entities"], [assertion(valid_from=None)], [], as_of="2026-01-01")
    assert not selected and unresolved["a"] == "unknown_dates"


def test_package_roundtrip_preserves_history_reviews_and_evidence(store, tmp_path):
    event = review(store, "replace", object="d")["event"]
    review(store, "undo", event_id=event["id"])
    review(store, "reject", assertion_id="a-c")
    store.run_inference(base_revision=store.workspace()["revision"], engine=engine)
    package = store.export_package()
    assert "labels" not in package["dataset"]
    restored = Store(tmp_path / "restored.sqlite3")
    restored.restore_package(package)
    assert restored.workspace()["counts"] == store.workspace()["counts"]
    assert restored.workspace()["active_snapshot"] == store.workspace()["active_snapshot"]
    for snapshot in store.workspace()["snapshots"]:
        before = store.detail("a", snapshot["id"])
        after = restored.detail("a", snapshot["id"])
        assert after == before
    with pytest.raises(Conflict):
        restored.restore_package(package)


def test_failed_run_and_cancel_leave_published_snapshot(store):
    sid = store.workspace()["active_snapshot"]
    def broken(data, **kwargs):
        raise RuntimeError("simulated failure")
    with pytest.raises(RuntimeError):
        store.run_inference(base_revision=2, engine=broken)
    assert store.workspace()["active_snapshot"] == sid
    assert store.workspace()["jobs"][0]["state"] == "failed"
    def cancel(data, **kwargs):
        store.cancel_job(store.workspace()["jobs"][0]["id"])
        return result()
    outcome = store.run_inference(base_revision=2, engine=cancel)
    assert outcome["job"]["state"] == "cancelled"
    assert store.workspace()["active_snapshot"] == sid
    store.retry_job(outcome["job"]["id"], base_revision=2)
    assert store.workspace()["revision"] == 3


def test_withdrawal_invalidates_dependent_score_redacts_history_and_filters_rerun(store, tmp_path):
    old = store.workspace()["active_snapshot"]
    review(store, "accept", assertion_id="a-b")
    store.withdraw_source("mail:1", "Removed from corpus", store.workspace()["revision"])
    assert all(not e["available"] and e["text"] is None for e in store.detail("a", old)["evidence"])
    package = store.export_package()
    assert "I report directly to Bob." not in dumps(package)
    def check(data, **kwargs):
        assert not data["messages"]
        return {"assertions": [], "evidence": [], "model": {"id": "check"}}
    store.run_inference(base_revision=store.workspace()["revision"], engine=check)
    assert not store.detail("a")["manager"]["evidence"][0]["available"]
    # A fresh workspace with no analyst override must abstain immediately.
    s = Store(tmp_path / "unreviewed.sqlite3")
    s.import_dataset(dataset())
    s.run_inference(base_revision=1, engine=engine)
    s.withdraw_source("mail:1", "Removed", 2)
    assert s.detail("a")["manager"] is None
    assert s.detail("a")["unresolved_reason"] == "evidence_unavailable"


def test_semantic_diff_ignores_generated_ids(store):
    before = store.workspace()["active_snapshot"]
    def new_ids(data, **kwargs):
        value = result()
        for a in value["assertions"]:
            a["id"] += "-new"
        return value
    store.run_inference(base_revision=2, engine=new_ids)
    assert store.compare(before, store.workspace()["active_snapshot"])["total"] == 0
    review(store, "replace", object="d")
    assert store.compare(before, store.workspace()["active_snapshot"])["changes"][0]["kind"] == "manager_changed"


def test_graph_and_directory_bounds_and_literal_search(store):
    assert len(store.graph(limit=2)["nodes"]) == 2
    assert store.entities(limit=2)["total"] == 4
    assert len(store.entities(offset=2, limit=2)["items"]) == 2
    assert store.entities(q="%")["total"] == 0
    with pytest.raises(ValueError):
        store.graph(limit=201)


def test_new_store_does_not_interrupt_job_in_live_process(store):
    def engine_with_reader(data, **kwargs):
        second = Store(store.path)
        assert second.workspace()["jobs"][0]["state"] == "running"
        return result()
    store.run_inference(base_revision=2, engine=engine_with_reader)


def test_matrix_review_cannot_replace_primary_parent(store):
    def matrix(data, **kwargs):
        value = result()
        value["assertions"].append(assertion(manager="d", reporting_type="matrix"))
        return value
    store.run_inference(base_revision=2, engine=matrix)
    for action in ("accept", "reject"):
        with pytest.raises(ValueError, match="primary reporting only"):
            review(store, action, assertion_id="a-d")
    assert store.detail("a")["manager"]["object"] == "b"


def test_dated_formal_groups_exclude_expired_memberships(tmp_path):
    data = dataset()
    data["entities"].append({"id": "unit", "name": "Research", "type": "unit", "aliases": []})
    data["assertions"] = [assertion(manager="unit", relation="member_of", origin="source", valid_to="2026-03-01", evidence_ids=[])]
    s = Store(tmp_path / "group.sqlite3")
    s.import_dataset(data)
    assert s.groups()["items"][0]["members"] == ["a"]
    s.run_inference(base_revision=1, as_of="2026-03-01", engine=engine)
    assert s.groups()["items"][0]["members"] == []


def test_group_member_names_are_bounded_and_bound_to_snapshot_import(tmp_path):
    people = [{"id": f"person-{index:03}", "name": f"Original person {index}", "type": "person"} for index in range(205)]
    data = {"schema_version": 1, "corpus": {"id": "names", "name": "Member names"},
            "entities": people + [{"id": "unit", "name": "Research", "type": "unit"}],
            "assertions": [{"id": f"member-{person['id']}", "subject": person["id"], "object": "unit", "relation": "member_of", "origin": "source"}
                           for person in people]}
    s = Store(tmp_path / "member-names.sqlite3")
    s.import_dataset(data)
    original_snapshot = s.workspace()["active_snapshot"]
    group = s.groups()["items"][0]
    assert len(group["members"]) == len(group["member_names"]) == 200
    assert group["member_count"] == 205 and group["members_truncated"]
    assert set(group["member_names"]) == set(group["members"])
    assert group["member_names"]["person-199"] == "Original person 199"
    assert "person-204" not in group["member_names"]
    renamed = deepcopy(data)
    renamed["entities"][199]["name"] = "Renamed person"
    s.import_dataset(renamed, replace=True, base_revision=1)
    assert s.groups()["items"][0]["member_names"]["person-199"] == "Renamed person"
    assert s.groups(original_snapshot)["items"][0]["member_names"]["person-199"] == "Original person 199"


def test_inferred_group_member_names_resolve_only_existing_returned_members(store):
    def group_engine(data, **kwargs):
        return {**result(), "groups": [{"id": "g", "members": ["d", "missing", "a"]}]}
    store.run_inference(base_revision=2, engine=group_engine)
    group = store.groups()["items"][0]
    assert group["members"] == ["d", "missing", "a"]
    assert group["member_names"] == {"d": "David", "a": "Alice"}
    assert group["kind"] == "inferred"


def test_csv_formula_names_are_neutralized(tmp_path):
    data = dataset()
    data["entities"][0]["name"] = '=HYPERLINK("https://example.invalid")'
    s = Store(tmp_path / "chart.sqlite3")
    s.import_dataset(data)
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(s.export_chart())))
    assert rows[0]["employee"].startswith("'=")
