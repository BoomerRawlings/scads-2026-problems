"""End-to-end local interface boundaries, not a claim of human evaluation."""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import threading
import pytest
from vopt.catalog import Catalog
from vopt.io import write_json
from vopt.review import record_fingerprint
from vopt.schema import seal_bundle, validate_bundle
from vopt.server import make_server
from vopt.workspace import Workspace
from test_lifecycle import bundle, private_record


@pytest.fixture
def running_server():
    servers = []
    def start(**kwargs):
        server = make_server(port=0, **kwargs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server.server_port
    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(port, path, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    status, payload, result_headers = response.status, response.read(), dict(response.getheaders())
    connection.close()
    return status, payload, result_headers


def test_discovery_interface_has_no_source_review_or_mutation_routes(tmp_path, running_server):
    path = tmp_path / "public.sqlite3"
    Catalog(path).import_bundle(bundle(tmp_path))
    port = running_server(catalog=path)
    status, body, headers = request(port, "/")
    assert status == 200 and b"Find a manual" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    status, body, _ = request(port, "/api/search?q=output%20power%20above%2020%20kW")
    result = json.loads(body)
    assert status == 200 and result["results"][0]["doc_id"] == "d1"
    assert "SOURCE_ONLY_SECRET" not in body.decode()
    assert "csrf" not in json.loads(request(port, "/api/info")[1])
    for route in ("/api/records", "/api/record/d1", "/api/page/d1", "/../../reviews.sqlite3"):
        assert request(port, route)[0] == 404
    assert request(port, "/api/review", method="POST", body="{}")[0] == 404
    assert request(port, "/api/info", headers={"Host": "attacker.example"})[0] == 403


def test_review_csrf_stale_decision_and_invalid_correction(tmp_path, running_server):
    ws = Workspace(tmp_path / "private")
    record = private_record()
    write_json(ws.record_path("d1"), record)
    port = running_server(workspace=ws.path)
    info = json.loads(request(port, "/api/info")[1])
    body = {"doc_id": "d1", "assertion_id": "a1", "decision": "correct", "actor": "Test reviewer",
        "fingerprint": record_fingerprint(record), "event_id": 0, "correction": {"value": 25000}}
    headers = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "X-VOPT-Token": info["csrf"]}
    assert request(port, "/api/review", method="POST", body=json.dumps(body))[0] == 403
    bad_headers = {**headers, "Origin": "https://attacker.example"}
    assert request(port, "/api/review", method="POST", body=json.dumps(body), headers=bad_headers)[0] == 403
    invalid = {**body, "correction": {"model": "wrong-model", "value": -1}}
    assert request(port, "/api/review", method="POST", body=json.dumps(invalid), headers=headers)[0] == 400
    assert ws.reviews.audit() == []
    assert request(port, "/api/review", method="POST", body=json.dumps(body), headers=headers)[0] == 200
    assert ws.reviews.approved(record)[0]["value"] == 25000
    assert ws.reviews.audit()[0]["actor_kind"] == "human"
    assert request(port, "/api/review", method="POST", body=json.dumps(body), headers=headers)[0] == 400
    assert len(ws.reviews.audit()) == 1
    record["processing_version"] = "changed"
    write_json(ws.record_path("d1"), record)
    assert request(port, "/api/review", method="POST", body=json.dumps(body), headers=headers)[0] == 400
    assert len(ws.reviews.audit()) == 1
    assert request(port, "/api/search?q=generator")[0] == 404


def test_source_page_hash_change_blocks_review_raster(tmp_path, running_server):
    import pymupdf
    import os
    source = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((30, 40), "Original engineering fixture")
        pdf.save(source)
    ws = Workspace(tmp_path / "private")
    record = private_record()
    record.update(source_path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    write_json(ws.record_path("d1"), record)
    port = running_server(workspace=ws.path)
    status, image, _ = request(port, "/api/page/d1?page=1")
    assert status == 200 and image.startswith(b"\x89PNG")
    original = source.read_bytes()
    stamp = source.stat()
    assert original.startswith(b"%PDF-1.7")
    source.write_bytes(original.replace(b"%PDF-1.7", b"%PDF-1.6", 1))
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert source.stat().st_size == stamp.st_size
    assert request(port, "/api/page/d1?page=1")[0] == 400
    source.write_bytes(source.read_bytes() + b"modified")
    assert request(port, "/api/page/d1?page=1")[0] == 400


def test_manifest_candidates_skipped_and_integrity_pin_enforced(tmp_path, monkeypatch):
    import vopt.ingest
    calls = []
    monkeypatch.setattr(vopt.ingest, "ingest_pdf", lambda *a, **kw: calls.append(a))
    doc = private_record()["document"]
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"not opened: integrity must fail before parser")
    manifest = tmp_path / "manifest.json"
    ws = Workspace(tmp_path / "workspace")
    entry = {"path": "manual.pdf", "document": doc, "admission_status": "candidate"}
    write_json(manifest, [entry])
    assert ws.ingest_manifest(manifest) == [] and not calls
    entry.update(admission_status="admitted", sha256="0"*64)
    write_json(manifest, [entry])
    with pytest.raises(ValueError, match="hash mismatch"):
        ws.ingest_manifest(manifest)
    assert not calls
    entry.update(sha256=hashlib.sha256(source.read_bytes()).hexdigest(), byte_size=1)
    write_json(manifest, [entry])
    with pytest.raises(ValueError, match="size mismatch"):
        ws.ingest_manifest(manifest)


@pytest.mark.parametrize("field,value", [("doc_id", []), ("attribute", {}), ("value", 10**400)])
def test_malformed_bundle_returns_validation_error(tmp_path, field, value):
    b = bundle(tmp_path)
    b["assertions"][0][field] = value
    with pytest.raises(ValueError):
        validate_bundle(seal_bundle(b))


def test_withdrawal_removes_fts_shadow_and_database_terms(tmp_path):
    b = bundle(tmp_path)
    marker = "uniquewithdrawnsentinel583791"
    b["documents"][0]["title"] = marker
    b = seal_bundle(b)
    cat = Catalog(tmp_path / "withdrawal.sqlite3")
    cat.import_bundle(b)
    b.update(sequence=2, documents=[], assertions=[], policy={"version": 2, "revoked_doc_ids": ["d1"], "revoked_assertion_ids": []})
    cat.import_bundle(seal_bundle(b))
    with cat.connect() as db:
        blocks = b"".join(bytes(row[0]) for row in db.execute("SELECT block FROM search_fts_data"))
    assert marker.encode() not in blocks
    assert marker.encode() not in cat.path.read_bytes()
    assert b"30000" not in blocks


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "3601"])
def test_cli_rejects_unbounded_native_timeout(value):
    from vopt.cli import parser
    with pytest.raises(SystemExit):
        parser().parse_args(["ingest", "manifest.json", "--workspace", "private", "--page-timeout-seconds", value])


def test_cli_passes_native_timeout_to_workspace(tmp_path, monkeypatch):
    from vopt.cli import parser, run
    observed = {}
    def ingest(self, *args, **kwargs):
        observed.update(kwargs)
        return []
    monkeypatch.setattr(Workspace, "ingest_manifest", ingest)
    args = parser().parse_args(["ingest", "manifest.json", "--workspace", str(tmp_path), "--page-timeout-seconds", "7.5"])
    assert run(args) == {"records": []}
    assert observed["page_timeout_seconds"] == 7.5
