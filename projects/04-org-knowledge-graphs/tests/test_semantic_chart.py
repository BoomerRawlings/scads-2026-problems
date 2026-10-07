"""Semantic zoom must preserve coverage, provenance and snapshot boundaries."""
import json

from fastapi.testclient import TestClient
import pytest

from orggraph.api import create_app
from orggraph.semantic import team_id
from orggraph.store import Store


def corpus(count=460):
    units = [{"id": "division", "name": "Division", "type": "unit"},
             {"id": "department", "name": "Department", "type": "unit", "unit_id": "division"},
             {"id": "empty", "name": "Empty unit", "type": "unit"}]
    people = [{"id": f"p{i:04}", "name": f"Person {i:04}", "role": "Researcher", "type": "person", "unit_id": "department"} for i in range(count)]
    people += [{"id": "outside", "name": "Outside", "type": "person"}]
    assertions = []
    for i in range(1, min(count, 151)):
        # An inner branch plus a wide head gives multiple meaningful zoom levels.
        parent = "p0001" if 2 <= i < 75 else "p0000"
        assertions.append({"id": f"reports-{i}", "subject": f"p{i:04}", "object": parent, "relation": "reports_to", "origin": "source", "evidence_ids": ["directory"], "raw_score": None, "calibration_status": "unavailable"})
    return {"schema_version": 1, "corpus": {"id": "semantic-fixture", "name": "Semantic fixture", "synthetic": True},
            "entities": units + people, "messages": [], "assertions": assertions,
            "evidence": [{"id": "directory", "kind": "source_record", "source_ref": "fixture:directory", "available": True}],
            "labels": [{"subject": "outside", "object": "p0000", "secret": "never-serve-fixture-labels"}]}


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "semantic.sqlite3")
    result.import_dataset(corpus())
    return result


def reachable(store, lens="formal", snapshot=None):
    queue, visited, people = [None], set(), set()
    while queue:
        scope = queue.pop()
        if scope in visited:
            continue
        visited.add(scope)
        offset = 0
        while True:
            page = store.chart(lens=lens, scope=scope, offset=offset, limit=37, snapshot=snapshot)
            assert len(page["nodes"]) <= 37
            ids = {node["id"] for node in page["nodes"]}
            assert all(edge["source"] in ids and edge["target"] in ids for edge in page["edges"])
            for node in page["nodes"]:
                if node["kind"] == "person":
                    people.add(node["entity_id"])
                if node["expandable"]:
                    queue.append(node["id"])
            offset += 37
            if offset >= page["total"]:
                break
    return people, visited


def test_formal_rollups_nested_units_unassigned_and_no_labels(store):
    root = store.chart()
    assert root["total_people"] == 461
    assert {node["id"]: node["person_count"] for node in root["nodes"]} == {"unit:division": 460, "unit:empty": 0, "unassigned:formal": 1}
    assert not root["edges"]
    assert '"members":' not in json.dumps(root)
    assert "never-serve-fixture-labels" not in json.dumps(root)
    division = store.chart(scope="unit:division")
    assert [node["id"] for node in division["nodes"]] == ["unit:department"]
    department = store.chart(scope="unit:department")
    assert [crumb["id"] for crumb in department["breadcrumbs"]] == [None, "unit:division", "unit:department"]
    assert department["total"] > 200
    assert sum(node["person_count"] for node in store.chart(scope="unit:department", limit=200)["nodes"]) > 200
    reached, visited = reachable(store)
    assert reached == {f"p{i:04}" for i in range(460)} | {"outside"}
    assert any(scope and scope.startswith("team:") for scope in visited)


def test_focus_beyond_first_page_and_individual_edge_provenance(store):
    last = store.chart(person="p0459", limit=20)
    assert last["offset"] >= 200
    assert any(node.get("entity_id") == "p0459" and node["kind"] == "person" for node in last["nodes"])
    focused = store.chart(person="p0074", limit=200)
    assert focused["scope"].startswith("team:")
    assert focused["breadcrumbs"][-1]["id"] == focused["scope"]
    assert any(node.get("entity_id") == "p0074" for node in focused["nodes"])
    edge = next(edge for edge in focused["edges"] if edge["target"] == "person:p0074")
    assert edge["source"] == "person:p0001"
    assert edge["id"] == edge["assertion_id"] == "reports-74"
    assert edge["evidence_ids"] == ["directory"]
    assert edge["origin"] == "source" and edge["raw_score"] is None
    assert edge["selected_probability"] is None


def test_inferred_uses_full_membership_and_reaches_ungrouped(store):
    def engine(data, **kwargs):
        return {"assertions": [], "evidence": [], "metrics": {}, "groups": [
            {"id": "large", "name": "Large communication group", "members": [f"p{i:04}" for i in range(459)] + ["missing", "p0000"]},
            {"id": "overlap", "name": "Overlapping community", "members": ["p0000", "outside"]}], "model": {"id": "test"}}
    store.run_inference(base_revision=store.workspace()["revision"], engine=engine)
    root = store.chart(lens="inferred")
    counts = {node["id"]: node["person_count"] for node in root["nodes"]}
    assert counts == {"group:large": 459, "group:overlap": 2, "unassigned:inferred": 1}
    reached, _ = reachable(store, "inferred")
    assert reached == {f"p{i:04}" for i in range(460)} | {"outside"}
    target = store.chart(lens="inferred", person="p0458", limit=15)
    assert target["offset"] > 200
    assert any(node.get("entity_id") == "p0458" for node in target["nodes"])


def test_membership_rollup_deduplicates_ancestors_and_honors_dates(tmp_path):
    data = corpus(2)
    data["assertions"] += [
        {"id": "member-parent", "subject": "p0000", "object": "division", "relation": "member_of", "origin": "source"},
        {"id": "member-child", "subject": "p0000", "object": "department", "relation": "member_of", "origin": "source"},
        {"id": "member-ended", "subject": "p0001", "object": "department", "relation": "member_of", "origin": "source", "valid_from": "2020-01-01", "valid_to": "2021-01-01"}]
    store = Store(tmp_path / "dates.sqlite3")
    store.import_dataset(data)
    initial = store.workspace()["active_snapshot"]
    assert next(n for n in store.chart()["nodes"] if n["id"] == "unit:division")["person_count"] == 2
    assert all(n["kind"] != "person" for n in store.chart(scope="unit:division")["nodes"])
    store.run_inference(base_revision=store.workspace()["revision"], as_of="2026-01-01", engine=lambda data, **kwargs: {"model": {"id": "none"}})
    # Undated memberships do not silently regain validity from entity.unit_id.
    assert next(n for n in store.chart()["nodes"] if n["id"] == "unassigned:formal")["person_count"] == 3
    assert next(n for n in store.chart(snapshot=initial)["nodes"] if n["id"] == "unit:division")["person_count"] == 2


def test_unknown_scopes_lenses_and_cross_snapshot_isolation(store):
    old = store.workspace()["active_snapshot"]
    for scope in ("unit:absent", "group:absent", "person:p0000", "team:!", team_id("unit:department", "p0459")):
        with pytest.raises(KeyError):
            store.chart(scope=scope)
    with pytest.raises(KeyError):
        store.chart(person="absent")
    with pytest.raises(KeyError):
        store.chart(scope="unit:department", lens="inferred")
    with pytest.raises(ValueError):
        store.chart(lens="unknown")
    replacement = {**corpus(1), "corpus": {"id": "replacement"}}
    store.import_dataset(replacement, replace=True)
    assert store.chart()["total_people"] == 2
    assert store.chart(snapshot=old)["total_people"] == 461
    assert any(n.get("entity_id") == "p0459" for n in store.chart(person="p0459", snapshot=old)["nodes"])
    with pytest.raises(KeyError):
        store.chart(person="p0459")


def test_api_validation_and_snapshot_errors(tmp_path):
    app = create_app(tmp_path / "api.sqlite3")
    with TestClient(app) as client:
        assert client.get("/api/chart").status_code == 404
        app.state.store.import_dataset(corpus(5))
        assert client.get("/api/chart").json()["total_people"] == 6
        assert client.get("/api/chart", params={"person": "p0004"}).status_code == 200
        assert client.get("/api/chart", params={"limit": 201}).status_code == 422
        assert client.get("/api/chart", params={"offset": -1}).status_code == 422
        assert client.get("/api/chart", params={"lens": "invalid"}).status_code == 400
        assert client.get("/api/chart", params={"scope": "unit:missing"}).status_code == 404
        assert client.get("/api/chart", params={"snapshot": "missing"}).status_code == 404


def test_cyclic_unit_metadata_remains_reachable(tmp_path):
    data = corpus(4)
    data["entities"][0]["unit_id"] = "department"
    store = Store(tmp_path / "cycle.sqlite3")
    store.import_dataset(data)
    reached, _ = reachable(store)
    assert reached == {"p0000", "p0001", "p0002", "p0003", "outside"}
