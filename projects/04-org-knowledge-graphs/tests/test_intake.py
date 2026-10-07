"""Dataset preflight stays read-only; only reviewed builds publish records."""
from copy import deepcopy
import json
import threading
import time

from fastapi.testclient import TestClient
import pytest

from orggraph.api import create_app
from orggraph.demo import demo_dataset
from orggraph.intake import IntakeManager, dataset_profile, graph_plan
from orggraph.store import Conflict, Store


def fixture_data():
    return {"schema_version": 1, "corpus": {"id": "intake-fixture", "name": "Intake fixture", "synthetic": True},
            "entities": [{"id": "a", "name": "Ava Moss", "type": "person", "role": "Director"},
                         {"id": "b", "name": "Bea Vale", "type": "person"},
                         {"id": "u", "name": "Research", "type": "unit"},
                         {"id": "s", "name": "Help", "type": "shared_mailbox"}],
            "messages": [{"id": "m1", "sender": "b", "to": ["a", "b"], "cc": ["a", "s"],
                          "body": "I report directly to Ava Moss.", "subject": "Report", "timestamp": "2026-01-01T10:00:00Z"},
                         {"id": "m2", "sender": "b", "to": ["a"], "body": "", "timestamp": None}],
            "assertions": [{"id": "membership", "subject": "b", "object": "u", "relation": "member_of"}],
            "evidence": [], "labels": [{"id": "gold", "subject": "a", "object": "b", "relation": "reports_to"}]}


def settled(manager, ident, states=("ready_for_review", "failed", "cancelled")):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = manager.get(ident)
        with manager.lock:
            running = ident in manager.running
        if result["status"] in states and not running:
            return result
        time.sleep(.005)
    raise AssertionError(f"Intake did not settle: {manager.get(ident)}")


def prepare(manager, data=None):
    return settled(manager, manager.upload(json.dumps(data or fixture_data()).encode(), "fixture.json")["id"])


def database_counts(store):
    with store.connection() as db:
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("imports", "entities", "snapshots", "reviews", "jobs", "assertions")}


@pytest.fixture
def manager(tmp_path):
    return IntakeManager(Store(tmp_path / "workspace.sqlite3"))


def test_profile_is_read_only_and_counts_normalized_records(manager):
    before = database_counts(manager.store)
    job = prepare(manager)
    assert job["status"] == "ready_for_review"
    assert manager.store.workspace()["revision"] == 0
    assert database_counts(manager.store) == before
    counts = job["profile"]["counts"]
    assert counts == {"entities": 4, "people": 2, "units": 1, "shared_mailboxes": 1,
                      "messages": 2, "assertions": 1, "evidence": 0, "labels": 1,
                      "data_points": 7, "communication_links": 2, "communication_events": 3}
    fields = {item["id"]: item for item in job["profile"]["fields"]}
    assert fields["roles"]["present"] == 1 and fields["roles"]["missing"] == 1
    assert fields["bodies"]["missing"] == fields["timestamps"]["missing"] == 1
    assert fields["names"]["total"] == 2
    assert job["profile"]["canonical_bytes"] > 0
    assert [s["status"] for s in job["stages"]] == ["complete"] * 3 + ["queued"] * 3
    assert "_payload" not in job


def test_preview_uses_source_links_not_evaluation_labels(manager):
    job = prepare(manager)
    assert {e["relation"] for e in job["plan"]["edges"]} == {"member_of", "communicates_with"}
    assert not any(e["relation"] == "reports_to" for e in job["plan"]["edges"])
    assert job["profile"]["relations"] == [{"relation": "member_of", "count": 1}]
    assert any("excluded" in note for note in job["profile"]["notes"])


def test_partial_bad_records_count_only_accepted_data(manager):
    data = fixture_data()
    data["entities"].append({"id": "bad", "name": ""})
    data["entities"].append(deepcopy(data["entities"][0]))
    data["messages"].append({"id": "bad-message", "sender": "unknown"})
    job = prepare(manager, data)
    assert job["profile"]["counts"]["people"] == 2
    assert job["profile"]["quality"]["quarantined"] == 2
    assert job["profile"]["quality"]["duplicate"] == 1
    assert job["profile"]["quality"]["read"] == sum(job["profile"]["quality"][key] for key in ("accepted", "quarantined", "duplicate", "unsupported"))


@pytest.mark.parametrize("data,name", [(b"not json", "bad.json"), (b"pdf bytes", "bad.pdf"), (b"{}", "empty.json")])
def test_malformed_empty_and_unsupported_uploads_do_not_write(manager, data, name):
    job = settled(manager, manager.upload(data, name)["id"])
    assert job["status"] == "failed" and job["error"] and not job["retryable"]
    assert database_counts(manager.store)["imports"] == 0
    with pytest.raises(Conflict):
        manager.build(job["id"], base_revision=0)


def test_zero_people_unit_only_preview_is_honest(manager):
    data = {"entities": [{"id": "u", "name": "Only unit", "type": "unit"}]}
    job = prepare(manager, data)
    assert job["status"] == "ready_for_review"
    assert job["profile"]["counts"]["people"] == 0
    assert all(field["total"] == 0 for field in job["profile"]["fields"])


def test_graph_sample_has_bounded_nodes_edges_and_closed_endpoints():
    data = demo_dataset(person_count=1000)
    plan = graph_plan(data)
    ids = {node["id"] for node in plan["nodes"]}
    assert len(ids) <= 24 and len(plan["edges"]) <= 40
    assert plan["total_nodes"] > 1000 and plan["sampled"]
    assert all(edge["source"] in ids and edge["target"] in ids for edge in plan["edges"])


def test_build_saves_then_infers_without_labels_and_is_idempotent(manager, monkeypatch):
    from orggraph import inference
    original = inference.infer
    seen = []

    def guarded(dataset, **kwargs):
        seen.append(dataset)
        assert "labels" not in dataset
        return original(dataset, **kwargs)
    monkeypatch.setattr(inference, "infer", guarded)
    job = prepare(manager)
    manager.build(job["id"], base_revision=0)
    ready = settled(manager, job["id"], ("ready", "failed"))
    assert ready["status"] == "ready", ready["error"]
    assert seen and ready["result"]["revision"] == 2
    assert all(stage["status"] == "complete" for stage in ready["stages"])
    before = database_counts(manager.store)
    assert manager.build(job["id"], base_revision=0)["result"] == ready["result"]
    assert database_counts(manager.store) == before
    assert manager.jobs[job["id"]]["_payload"] is None


def test_stale_revision_and_explicit_replacement_checked_before_write(manager):
    job = prepare(manager)
    manager.store.import_dataset(demo_dataset(), base_revision=0)
    before = database_counts(manager.store)
    with pytest.raises(Conflict, match="changed"):
        manager.build(job["id"], base_revision=0)
    assert database_counts(manager.store) == before
    with pytest.raises(Conflict, match="Explicit replacement"):
        manager.build(job["id"], base_revision=1)
    assert database_counts(manager.store) == before
    manager.build(job["id"], base_revision=1, replace=True)
    ready = settled(manager, job["id"], ("ready", "failed"))
    assert ready["status"] == "ready"
    assert database_counts(manager.store)["imports"] == 2
    assert database_counts(manager.store)["snapshots"] == 3


def test_synthetic_identical_dataset_reuses_published_model(manager):
    manager.store.import_dataset(demo_dataset(), base_revision=0)
    manager.store.run_inference(base_revision=1)
    before = database_counts(manager.store)
    job = settled(manager, manager.synthetic(72)["id"])
    assert job["source"]["bytes"] > 0
    assert job["workspace"]["same_dataset"] and job["workspace"]["can_reuse"]
    assert database_counts(manager.store) == before
    manager.build(job["id"], base_revision=2)
    ready = settled(manager, job["id"], ("ready", "failed"))
    assert ready["status"] == "ready"
    assert next(stage for stage in ready["stages"] if stage["id"] == "infer")["status"] == "skipped"
    assert database_counts(manager.store) == before


def test_failed_inference_keeps_saved_source_and_can_retry(manager, monkeypatch):
    original = manager.store.run_inference
    monkeypatch.setattr(manager.store, "run_inference", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("temporary engine failure")))
    job = prepare(manager)
    manager.build(job["id"], base_revision=0)
    failed = settled(manager, job["id"], ("ready", "failed"))
    assert failed["status"] == "failed" and failed["retryable"]
    assert failed["workspace"]["base_revision"] == 1
    assert database_counts(manager.store)["imports"] == 1
    monkeypatch.setattr(manager.store, "run_inference", original)
    manager.build(job["id"], base_revision=1)
    ready = settled(manager, job["id"], ("ready", "failed"))
    assert ready["status"] == "ready" and ready["result"]["revision"] == 2
    assert database_counts(manager.store)["imports"] == 1


def test_profile_capacity_expiry_and_cancel_release_payload(manager):
    first, second = prepare(manager), prepare(manager)
    with pytest.raises(Conflict, match="Two dataset previews"):
        prepare(manager)
    manager.cancel(first["id"])
    assert manager.jobs[first["id"]]["_payload"] is None
    third = prepare(manager)
    assert first["id"] not in manager.jobs and len(manager.jobs) == 2
    manager.jobs[second["id"]]["_touched"] -= manager.ttl + 1
    with pytest.raises(KeyError, match="expired"):
        manager.get(second["id"])
    assert manager.get(third["id"])["status"] == "ready_for_review"


def test_one_worker_and_cancelling_profile_cannot_write(manager, monkeypatch):
    from orggraph import intake
    started, release = threading.Event(), threading.Event()
    original = intake.parse_bytes

    def slow(*args):
        started.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(intake, "parse_bytes", slow)
    job = manager.upload(json.dumps(fixture_data()).encode(), "fixture.json")
    assert started.wait(2)
    with pytest.raises(Conflict, match="Another intake"):
        manager.synthetic(72)
    manager.cancel(job["id"])
    with pytest.raises(Conflict):
        manager.synthetic(72)
    release.set()
    result = settled(manager, job["id"])
    assert result["status"] == "cancelled"
    assert database_counts(manager.store)["imports"] == 0


def test_package_history_restores_without_reinference(tmp_path, monkeypatch):
    source = Store(tmp_path / "source.sqlite3")
    source.import_dataset(demo_dataset(), base_revision=0)
    source.run_inference(base_revision=1)
    person = source.entities(status="inferred", limit=1)["items"][0]
    detail = source.detail(person["id"])
    review = source.review({"base_revision": 2, "subject": person["id"], "action": "reject",
                            "assertion_id": detail["manager"]["id"], "reason": "Verify imported history"})
    source.review({"base_revision": 3, "subject": person["id"], "action": "undo",
                   "event_id": review["event"]["id"], "reason": "Restore original decision"})
    package = source.export_package()
    manager = IntakeManager(Store(tmp_path / "target.sqlite3"))
    job = prepare(manager, package)
    assert job["status"] == "ready_for_review", job["error"]
    assert database_counts(manager.store)["snapshots"] == 0
    monkeypatch.setattr(manager.store, "run_inference", lambda **kw: pytest.fail("Package must not be inferred again"))
    manager.build(job["id"], base_revision=0)
    ready = settled(manager, job["id"], ("ready", "failed"))
    assert ready["status"] == "ready", ready["error"]
    assert ready["result"]["active_snapshot"] == source.workspace()["active_snapshot"]
    assert database_counts(manager.store)["reviews"] == 2
    assert next(s for s in ready["stages"] if s["id"] == "infer")["status"] == "skipped"


def test_malformed_package_history_fails_before_any_write(manager):
    package = {"format": "orggraph-package", "schema_version": 1, "dataset": fixture_data(),
               "history": {"snapshots": [{"metadata": {"id": "bad", "revision": 1}}]}}
    job = prepare(manager, package)
    assert job["status"] == "failed" and not job["retryable"]
    assert database_counts(manager.store)["imports"] == 0


@pytest.mark.parametrize("field,value", [
    ("evidence", [{"id": "e", "kind": "source_assertion", "details": []}]),
    ("assertions", [{"id": "a", "subject": "a", "object": "b", "relation": "reports_to", "evidence_ids": [{}]}]),
    ("groups", [{"id": "g", "members": [{}]}]),
    ("metrics", {"a": []}),
])
def test_malformed_history_record_shapes_fail_during_preflight(manager, field, value):
    snapshot = {"metadata": {"id": "snap", "revision": 1, "reason": "Imported", "created_at": "2026-01-01T00:00:00Z"}, field: value}
    package = {"format": "orggraph-package", "schema_version": 1, "dataset": fixture_data(), "history": {"snapshots": [snapshot]}}
    job = prepare(manager, package)
    assert job["status"] == "failed" and not job["retryable"]
    assert database_counts(manager.store)["imports"] == 0


def test_package_restore_is_explicitly_blocked_in_populated_workspace(manager):
    manager.store.import_dataset(demo_dataset(), base_revision=0)
    package = manager.store.export_package()
    before = database_counts(manager.store)
    job = prepare(manager, package)
    assert job["workspace"]["package_requires_empty"]
    with pytest.raises(Conflict, match="empty workspace"):
        manager.build(job["id"], base_revision=1, replace=True)
    assert database_counts(manager.store) == before


def test_foreign_inference_result_is_not_reported_as_our_chart(manager, monkeypatch):
    original = manager.store.run_inference

    def raced(**kwargs):
        result = original(**kwargs)
        other = deepcopy(result["workspace"])
        other["active_snapshot"] = "different-snapshot"
        return {**result, "workspace": other}
    monkeypatch.setattr(manager.store, "run_inference", raced)
    job = prepare(manager)
    manager.build(job["id"], base_revision=0)
    result = settled(manager, job["id"], ("ready", "failed"))
    assert result["status"] == "failed" and result["result"] is None
    assert "changed after analysis" in result["error"]


def test_api_contract_strict_sizes_and_real_async_profile(tmp_path):
    app = create_app(tmp_path / "api.sqlite3")
    with TestClient(app) as client:
        for people in (True, 71, 100001, 72.5, "72"):
            assert client.post("/api/intake/synthetic", json={"people": people}).status_code == 422
        response = client.post("/api/intake/import", files={"file": ("test.json", json.dumps(fixture_data()).encode(), "application/json")})
        assert response.status_code == 202
        job = settled(app.state.intake, response.json()["id"])
        assert client.get(f"/api/intake/{job['id']}").json()["status"] == "ready_for_review"
        assert client.get("/api/workspace").json()["revision"] == 0
        assert client.post(f"/api/intake/{job['id']}/build", json={"base_revision": True}).status_code == 422
        assert client.post(f"/api/intake/{job['id']}/build", json={"base_revision": 0}).status_code == 202
        ready = settled(app.state.intake, job["id"], ("ready", "failed"))
        assert ready["status"] == "ready"
        assert client.delete(f"/api/intake/{job['id']}").status_code == 409
        assert client.get("/api/intake/absent").status_code == 404


def test_request_key_recovers_and_reuses_synthetic_preview_without_writes(manager):
    key = "synthetic-request-001"
    before = database_counts(manager.store)
    job = settled(manager, manager.synthetic(72, request_key=key)["id"])
    assert manager.get_request(key)["id"] == job["id"]
    assert manager.synthetic(72, request_key=key)["id"] == job["id"]
    assert len(manager.jobs) == 1
    assert database_counts(manager.store) == before
    assert "_request_key" not in job and "_request_signature" not in job
    with pytest.raises(Conflict, match="another dataset"):
        manager.synthetic(73, request_key=key)
    with pytest.raises(Conflict, match="another dataset"):
        manager.upload(json.dumps(fixture_data()).encode(), "fixture.json", request_key=key)
    assert len(manager.jobs) == 1 and database_counts(manager.store) == before


def test_repeated_upload_request_during_processing_does_not_start_another_worker(manager, monkeypatch):
    from orggraph import intake
    started, release = threading.Event(), threading.Event()
    original = intake.parse_bytes
    calls = []

    def slow(*args):
        calls.append(args)
        started.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(intake, "parse_bytes", slow)
    data, key = json.dumps(fixture_data()).encode(), "upload-request-001"
    first = manager.upload(data, "fixture.json", request_key=key)
    try:
        assert started.wait(2)
        assert manager.get_request(key)["id"] == first["id"]
        assert manager.upload(data, "fixture.json", request_key=key)["id"] == first["id"]
        with pytest.raises(Conflict, match="another dataset"):
            manager.upload(data + b" ", "fixture.json", request_key=key)
        with pytest.raises(Conflict, match="another dataset"):
            manager.upload(data, "other.json", request_key=key)
        assert len(manager.jobs) == len(manager.running) == len(calls) == 1
    finally:
        release.set()
    assert settled(manager, first["id"])["status"] == "ready_for_review"
    assert database_counts(manager.store)["imports"] == 0


def test_request_recovery_respects_cancellation_and_expiry(manager):
    key = "recover-request-001"
    with pytest.raises(ValueError, match="request key"):
        manager.get_request(None)
    job = settled(manager, manager.synthetic(72, request_key=key)["id"])
    manager.cancel(job["id"])
    assert manager.get_request(key)["status"] == "cancelled"
    assert manager.synthetic(72, request_key=key)["status"] == "cancelled"
    assert manager.jobs[job["id"]]["_payload"] is None
    manager.jobs[job["id"]]["_touched"] -= manager.ttl + 1
    with pytest.raises(KeyError, match="expired"):
        manager.get_request(key)
    next_job = manager.synthetic(72, request_key=key)
    assert next_job["id"] != job["id"]
    settled(manager, next_job["id"])
    assert database_counts(manager.store)["imports"] == 0


@pytest.mark.parametrize("key", ["", "short", "a" * 129, "has spaces here", "path/invalid", 42])
def test_invalid_request_keys_do_not_create_jobs(manager, key):
    with pytest.raises(ValueError, match="request key"):
        manager.synthetic(72, request_key=key)
    assert not manager.jobs and not manager.running


def test_request_recovery_api_handles_lost_reply_for_both_source_modes(tmp_path):
    app = create_app(tmp_path / "recovery.sqlite3")
    data = json.dumps(fixture_data()).encode()
    with TestClient(app) as client:
        key = "import-api-request-001"
        upload = lambda content=data: client.post("/api/intake/import", data={"request_key": key},
                                                  files={"file": ("fixture.json", content, "application/json")})
        first = upload()
        assert first.status_code == 202
        recovered = client.get(f"/api/intake/request/{key}")
        assert recovered.status_code == 200 and recovered.json()["id"] == first.json()["id"]
        settled(app.state.intake, recovered.json()["id"])
        assert upload().json()["id"] == recovered.json()["id"]
        assert upload(data + b" ").status_code == 409
        synthetic_key = "synthetic-api-request-001"
        synthetic = client.post("/api/intake/synthetic", json={"people": 72, "request_key": synthetic_key})
        assert synthetic.status_code == 202
        assert client.get(f"/api/intake/request/{synthetic_key}").json()["id"] == synthetic.json()["id"]
        settled(app.state.intake, synthetic.json()["id"])
        assert client.post("/api/intake/synthetic", json={"people": 72, "request_key": synthetic_key}).json()["id"] == synthetic.json()["id"]
        assert client.get("/api/intake/request/missing-request-key").status_code == 404
        assert client.post("/api/intake/synthetic", json={"people": 72, "request_key": "bad key"}).status_code == 422
        assert client.post("/api/intake/import", data={"request_key": "bad key"},
                           files={"file": ("fixture.json", data, "application/json")}).status_code == 422
        assert len(app.state.intake.jobs) == 2
        assert client.get("/api/workspace").json()["revision"] == 0
        assert database_counts(app.state.store)["imports"] == 0
