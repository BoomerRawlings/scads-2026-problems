"""HTTP-level workflows: request validation, durable edits, and package replay."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from orggraph.api import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "workspace.sqlite3")) as active:
        yield active


def small_dataset():
    return {
        "schema_version": 1,
        "corpus": {"id": "api-fixture", "name": "Fictional API fixture", "synthetic": True},
        "entities": [
            {"id": "ada", "name": "Ada Moss", "type": "person", "email": "ada@example.org", "aliases": [], "role": "Director"},
            {"id": "bea", "name": "Bea Vale", "type": "person", "email": "bea@example.org", "aliases": []},
            {"id": "cy", "name": "Cy Reed", "type": "person", "email": "cy@example.org", "aliases": []},
            {"id": "drew", "name": "Drew Chen", "type": "person", "email": "drew@example.org", "aliases": []},
        ],
        "messages": [
            {"id": "m1", "sender": "bea", "to": ["ada"], "cc": [], "timestamp": "2026-01-05T17:00:00Z",
             "subject": "Directory confirmation", "body": "I report directly to Ada Moss.", "source_ref": "fixture://m1"},
            {"id": "m2", "sender": "bea", "to": ["cy"], "cc": [], "timestamp": "2026-01-06T17:00:00Z",
             "subject": "Coverage", "body": "Ada Moss is my line manager.", "source_ref": "fixture://m2"},
            {"id": "m3", "sender": "cy", "to": ["bea"], "cc": [], "timestamp": "2026-01-07T17:00:00Z",
             "subject": "Project", "body": "Please send the workshop slides for this temporary project.", "source_ref": "fixture://m3"},
        ],
        "assertions": [], "evidence": [],
        "labels": [{"id": "gold-bea", "subject": "bea", "object": "ada", "relation": "reports_to", "source_role": "fixture_validation_only"}],
    }


def upload(client, dataset=None):
    payload = small_dataset() if dataset is None else dataset
    return client.post("/api/import", files={"file": ("fixture.json", json.dumps(payload).encode(), "application/json")})


def imported_and_inferred(client):
    imported = upload(client)
    assert imported.status_code == 200, imported.text
    revision = imported.json()["workspace"]["revision"]
    inferred = client.post("/api/infer", json={"base_revision": revision})
    assert inferred.status_code == 200, inferred.text
    assert inferred.json()["job"]["state"] == "complete"
    return inferred.json()["workspace"]


def test_empty_workspace_health_and_validation(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    workspace = client.get("/api/workspace").json()
    assert workspace["active_snapshot"] is None and workspace["counts"]["entities"] == 0
    assert client.get("/api/entities").status_code == 404
    assert client.post("/api/infer", json={"base_revision": 0}).status_code == 404
    assert client.get("/api/entities?limit=201").status_code == 422
    assert client.get("/api/graph?limit=0").status_code == 422
    assert client.post("/api/infer", json={"base_revision": 0, "threshold": 1.5}).status_code == 422
    assert client.post("/api/import").status_code == 422


def test_demo_idempotency_and_nonempty_import_conflict(client):
    response = client.post("/api/demo")
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["corpus"]["synthetic"] is True
    assert first["counts"]["people"] >= 60 and first["counts"]["selected"] > 0
    second = client.post("/api/demo").json()
    assert second["active_snapshot"] == first["active_snapshot"]
    assert second["revision"] == first["revision"]
    conflict = upload(client)
    assert conflict.status_code == 409
    assert client.get("/api/workspace").json()["active_snapshot"] == first["active_snapshot"]


def test_import_infer_search_detail_children_and_bounded_graph(client):
    workspace = imported_and_inferred(client)
    snapshot = workspace["active_snapshot"]
    found = client.get("/api/entities", params={"q": "BEA@EXAMPLE.ORG", "limit": 1, "snapshot": snapshot}).json()
    assert found["total"] == 1 and found["items"][0]["id"] == "bea"
    assert found["snapshot"] == snapshot
    detail = client.get("/api/entities/bea", params={"snapshot": snapshot}).json()
    assert detail["manager"]["object"] == "ada"
    assert detail["manager"]["origin"] == "model"
    assert detail["manager"]["candidate_probability"] is None
    assert detail["manager"]["calibration_status"] == "uncalibrated"
    assert detail["evidence"] and detail["ancestors"][0]["id"] == "ada"
    bodies = {m["id"]: m["body"] for m in small_dataset()["messages"]}
    for evidence in detail["evidence"]:
        if evidence["kind"] == "message_span":
            assert bodies[evidence["message_ids"][0]][evidence["start"]:evidence["end"]] == evidence["text"]
    children = client.get("/api/children", params={"parent": "ada", "snapshot": snapshot}).json()
    assert "bea" in {item["id"] for item in children["items"]}
    graph = client.get("/api/graph", params={"focus": "bea", "limit": 2, "snapshot": snapshot}).json()
    assert graph["returned_nodes"] <= 2
    assert graph["omitted_nodes"] == graph["total_nodes"] - graph["returned_nodes"]
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "bea" in node_ids
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"])
    unresolved = client.get("/api/entities", params={"status": "unresolved"}).json()
    assert "drew" in {item["id"] for item in unresolved["items"]}
    assert client.get("/api/entities/not-present").status_code == 404
    assert client.get("/api/graph?focus=not-present").status_code == 404
    assert client.get("/api/groups").json()["snapshot"] == snapshot


def test_reject_refresh_undo_preserves_history_and_old_snapshot(client):
    workspace = imported_and_inferred(client)
    original_snapshot = workspace["active_snapshot"]
    detail = client.get("/api/entities/bea").json()
    request = {"base_revision": workspace["revision"], "subject": "bea", "action": "reject", "assertion_id": detail["manager"]["id"],
               "reason": "Analyst checked the directory; leave unresolved.", "idempotency_key": "review-bea-once"}
    rejected = client.post("/api/reviews", json=request)
    assert rejected.status_code == 200, rejected.text
    rejected = rejected.json()
    assert client.get("/api/entities/bea").json()["manager"] is None
    replay = client.post("/api/reviews", json=request)
    assert replay.status_code == 200 and replay.json()["duplicate"] is True
    assert replay.json()["event"]["id"] == rejected["event"]["id"]
    stale = client.post("/api/reviews", json={**request, "idempotency_key": "different-key"})
    assert stale.status_code == 409
    assert "detail" in stale.json()
    rerun = client.post("/api/infer", json={"base_revision": rejected["workspace"]["revision"]})
    assert rerun.status_code == 200, rerun.text
    current = client.get("/api/entities/bea").json()
    assert current["manager"] is None and current["unresolved_reason"] == "analyst_rejected"
    assert client.get("/api/entities/bea", params={"snapshot": original_snapshot}).json()["manager"]["object"] == "ada"
    undone = client.post("/api/reviews", json={"base_revision": rerun.json()["workspace"]["revision"], "subject": "bea", "action": "undo",
                                               "event_id": rejected["event"]["id"], "reason": "Restore the original proposal for reassessment."})
    assert undone.status_code == 200, undone.text
    current = client.get("/api/entities/bea").json()
    assert current["manager"]["object"] == "ada"
    assert len(current["history"]) == 2 and current["history"][0]["undone"] is True
    comparison = client.get("/api/compare", params={"before": original_snapshot, "after": rejected["workspace"]["active_snapshot"]}).json()
    assert any(change["subject"] == "bea" and change["kind"] == "relationship_removed" for change in comparison["changes"])


def test_replacement_nulls_probabilities_and_invalid_reviews_do_not_write(client):
    workspace = imported_and_inferred(client)
    before = workspace["revision"]
    bad = client.post("/api/reviews", json={"base_revision": before, "subject": "bea", "action": "replace", "object": "bea", "reason": "Invalid self edge"})
    assert bad.status_code == 400
    assert client.get("/api/workspace").json()["revision"] == before
    assert client.post("/api/reviews", json={"base_revision": before, "subject": "bea", "action": "replace", "object": "cy", "reason": ""}).status_code == 422
    response = client.post("/api/reviews", json={"base_revision": before, "subject": "bea", "action": "replace", "object": "cy",
                                                 "valid_from": "2026-01-01", "reason": "Verified by an independent directory entry."})
    assert response.status_code == 200, response.text
    manager = client.get("/api/entities/bea").json()["manager"]
    assert manager["object"] == "cy" and manager["origin"] == "analyst"
    assert manager["raw_score"] is manager["candidate_probability"] is manager["selected_probability"] is None
    assert client.post("/api/infer", json={"base_revision": before}).status_code == 409


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "http://localhost:9999", "http://testserver:9999"])
def test_cross_origin_writes_rejected_without_mutation(client, origin):
    response = client.post("/api/demo", headers={"Origin": origin})
    assert response.status_code == 403
    assert client.get("/api/workspace").json()["active_snapshot"] is None


def test_same_origin_and_untrusted_host(client):
    response = upload(client)
    assert response.status_code == 200
    revision = response.json()["workspace"]["revision"]
    assert client.post("/api/infer", json={"base_revision": revision}, headers={"Origin": "http://testserver"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


@pytest.mark.parametrize("filename,data", [("bad.json", b"{"), ("bad.csv", b"from,to\n,missing@example.org\n"), ("archive.pst", b"unsupported")])
def test_unusable_uploads_fail_without_creating_snapshot(client, filename, data):
    response = client.post("/api/import", files={"file": (filename, data)})
    assert response.status_code == 400
    assert "detail" in response.json()
    assert client.get("/api/workspace").json()["active_snapshot"] is None


def test_partly_invalid_import_reports_quarantine_and_repeat_is_idempotent(client):
    dataset = small_dataset()
    dataset["messages"].append({"id": "bad", "sender": "unknown", "to": ["ada"], "body": "bad"})
    response = upload(client, dataset)
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["quarantined"] == 1
    assert report["read"] == sum(report[key] for key in ("accepted", "duplicate", "quarantined", "unsupported"))
    repeated = upload(client, dataset)
    assert repeated.status_code == 200
    assert repeated.json()["workspace"]["active_snapshot"] == response.json()["workspace"]["active_snapshot"]


def test_export_restore_retains_projection_history_and_snapshot_ids(client, tmp_path):
    workspace = imported_and_inferred(client)
    first_snapshot = workspace["active_snapshot"]
    response = client.post("/api/reviews", json={"base_revision": workspace["revision"], "subject": "bea", "action": "replace", "object": "cy",
                                                 "valid_from": "2026-01-01", "reason": "Independent directory correction."})
    assert response.status_code == 200, response.text
    final_workspace = response.json()["workspace"]
    downloaded = client.get("/api/export?format=json")
    assert downloaded.status_code == 200
    assert "attachment" in downloaded.headers["content-disposition"]
    package = downloaded.json()
    assert package["format"] == "orggraph-package"
    assert not package["dataset"].get("labels")
    assert package["history"]["reviews"]
    assert client.get("/api/export?format=csv").text.find("Lossy primary chart") >= 0
    assert "not calibrated probabilities" in client.get("/api/export?format=report").text
    assert client.get("/api/export?format=invalid").status_code == 400
    with TestClient(create_app(tmp_path / "restored.sqlite3")) as restored:
        result = restored.post("/api/import", files={"file": ("organization-atlas.json", downloaded.content, "application/json")})
        assert result.status_code == 200, result.text
        workspace = result.json()["workspace"]
        assert workspace["active_snapshot"] == final_workspace["active_snapshot"]
        assert workspace["counts"] == final_workspace["counts"]
        assert workspace["revision"] == final_workspace["revision"]
        detail = restored.get("/api/entities/bea").json()
        assert detail["manager"]["object"] == "cy"
        assert detail["manager"]["origin"] == "analyst" and len(detail["history"]) == 1
        old = restored.get("/api/entities/bea", params={"snapshot": first_snapshot}).json()
        assert old["manager"]["object"] == "ada"
        assert restored.post("/api/import", files={"file": ("again.json", downloaded.content)}).status_code == 409


def test_corrupt_package_restore_is_atomic(client, tmp_path):
    imported_and_inferred(client)
    package = copy.deepcopy(client.get("/api/export").json())
    assert package["history"]["snapshots"][-1]["assertions"]
    package["history"]["snapshots"][-1]["assertions"][0]["object"] = "unknown-person"
    with TestClient(create_app(tmp_path / "corrupt-restore.sqlite3")) as restored:
        response = upload(restored, package)
        assert response.status_code == 400, response.text
        assert restored.get("/api/workspace").json()["active_snapshot"] is None
