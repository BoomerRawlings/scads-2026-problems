"""Reproducible synthetic generation and explicit workspace expansion."""
import json

from fastapi.testclient import TestClient

from orggraph.api import create_app
from orggraph.cli import main


def test_generate_only_writes_canonical_fixture_without_database(tmp_path, monkeypatch, capsys):
    output, database = tmp_path / "synthetic.json", tmp_path / "untouched.sqlite3"
    monkeypatch.setattr("sys.argv", ["orggraph", "--db", str(database), "demo", "--people", "120", "--output", str(output), "--generate-only"])
    main()
    assert not database.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert sum(e["type"] == "person" for e in data["entities"]) == 120
    assert data["messages"] and data["labels"] and data["corpus"]["synthetic"]
    assert json.loads(capsys.readouterr().out)["people"] == 120


def test_sized_demo_requires_explicit_switch_and_preserves_old_snapshot(tmp_path):
    with TestClient(create_app(tmp_path / "workspace.sqlite3")) as client:
        old = client.post("/api/demo").json()
        assert old["counts"]["people"] == 72
        assert client.post("/api/demo", json={"people": 120}).status_code == 409
        assert client.post("/api/demo", json={"people": 120, "replace": True}).status_code == 400
        assert client.post("/api/demo", json={"people": 120, "replace": True, "base_revision": 0}).status_code == 409
        response = client.post("/api/demo", json={"people": 120, "replace": True, "base_revision": old["revision"]})
        assert response.status_code == 200, response.text
        enlarged = response.json()
        assert enlarged["counts"]["people"] == 120
        assert client.get("/api/entities", params={"snapshot": old["active_snapshot"]}).json()["total"] == 72
        assert client.get("/api/entities/avery-stone").status_code == 200
        assert client.post("/api/demo", json={"people": 120}).json()["active_snapshot"] == enlarged["active_snapshot"]
        for value in (71, 100001, 72.5, True):
            assert client.post("/api/demo", json={"people": value}).status_code == 422


def test_demo_retries_inference_after_failed_first_run(tmp_path, monkeypatch):
    from orggraph import inference
    original = inference.infer
    attempts = []

    def flaky(dataset, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("simulated first run failure")
        return original(dataset, **kwargs)

    monkeypatch.setattr(inference, "infer", flaky)
    with TestClient(create_app(tmp_path / "workspace.sqlite3"), raise_server_exceptions=False) as client:
        assert client.post("/api/demo").status_code == 500
        response = client.post("/api/demo")
        assert response.status_code == 200, response.text
        assert response.json()["counts"]["selected"] > 0
        assert len(attempts) == 2
