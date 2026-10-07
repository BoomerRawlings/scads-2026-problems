import copy
import sqlite3
import pytest
from vopt.catalog import Catalog
from vopt.schema import seal_bundle, validate_bundle
from vopt.review import ReviewStore, record_fingerprint
from vopt.release import export_bundle


def private_record():
    return {
        "schema_version": 1, "sha256": "a" * 64, "processing_version": "test-v1", "processing_status": "complete",
        "document": {"doc_id": "d1", "title": "Engineering fixture generator", "manufacturer": "Fictional",
            "models": ["G1"], "category": "generator", "language": "en", "revision": "1", "source_uri": "private://SOURCE_ONLY_SECRET",
            "rights": {"basis": "CC0", "evidence_url": "fixture://authored", "attribution": "Synthetic engineering fixture"}},
        "pages": [{"page_number": 1, "status": "ok", "text": "SOURCE_ONLY_SECRET Rated output 30000 W", "lines": []}],
        "assertions": [{"assertion_id": "a1", "doc_id": "d1", "model": "G1", "variant": None, "attribute": "output_power", "value": 30000, "value_max": None,
            "unit": "W", "qualifier": "rated", "status": "candidate", "confidence": .8, "method": "fixture",
            "evidence": {"page": 1, "bbox": [0, 0, 100, 10], "text": "Rated output 30000 W"}}],
    }


def bundle(tmp_path, profile="values", sequence=1):
    r = private_record()
    reviews = ReviewStore(tmp_path / "reviews.sqlite3")
    latest = reviews.status(r)["items"][0]["event"]
    reviews.decide(r, "a1", "accept", "engineering-test", actor_kind="fixture", expected_fingerprint=record_fingerprint(r), expected_event_id=latest["event_id"] if latest else 0)
    return export_bundle([r], reviews, "fixture-catalog", sequence, profile, required_kind="fixture")


def reseal(b):
    b.pop("integrity", None)
    return seal_bundle(b)


def test_export_excludes_private_content_and_default_requires_human(tmp_path):
    r = private_record()
    reviews = ReviewStore(tmp_path / "r.sqlite3")
    reviews.decide(r, "a1", "accept", "model-review", actor_kind="agent", expected_fingerprint=record_fingerprint(r))
    with pytest.raises(ValueError, match="human"):
        export_bundle([r], reviews, "cat", 1)
    b = export_bundle([r], reviews, "cat", 1, "coverage", required_kind="agent")
    assert "SOURCE_ONLY_SECRET" not in str(b)
    assert "evidence" not in str(b)
    assert not ({"value", "unit", "value_max"} & b["assertions"][0].keys())


def test_stale_review_not_reused_and_correction_audit_preserved(tmp_path):
    r = private_record()
    reviews = ReviewStore(tmp_path / "r.sqlite3")
    before = record_fingerprint(r)
    reviews.decide(r, "a1", "correct", "reviewer", correction={"value": 25000}, expected_fingerprint=before)
    assert reviews.approved(r)[0]["value"] == 25000
    assert r["assertions"][0]["value"] == 30000
    r["processing_version"] = "new-method"
    assert reviews.status(r)["items"][0]["review_status"] == "stale"
    with pytest.raises(ValueError, match="Stale"):
        reviews.decide(r, "a1", "accept", "reviewer", expected_fingerprint=before)
    with pytest.raises(ValueError, match="stale"):
        export_bundle([r], reviews, "cat", 1)
    assert len(reviews.audit()) == 1


def test_partial_processing_preserves_uncertainty(tmp_path):
    r = private_record()
    r["pages"].append({"page_number": 2, "status": "failed", "text": "", "error": "Unreadable"})
    reviews = ReviewStore(tmp_path / "r.sqlite3")
    reviews.decide(r, "a1", "accept", "reviewer", expected_fingerprint=record_fingerprint(r))
    b = export_bundle([r], reviews, "cat", 1)
    assert b["documents"][0]["processing_status"] == "partial"


def test_discrete_candidates_can_release_presence_but_not_fake_numeric_range(tmp_path):
    r = private_record()
    r["assertions"][0].update(attribute="output_voltage", value="125/250", unit="V")
    reviews = ReviewStore(tmp_path / "r.sqlite3")
    reviews.decide(r, "a1", "accept", "reviewer", expected_fingerprint=record_fingerprint(r))
    b = export_bundle([r], reviews, "cat", 1, "coverage")
    assert b["assertions"][0]["attribute"] == "output_voltage"
    assert "125" not in str(b)
    with pytest.raises(ValueError, match="unresolved discrete"):
        export_bundle([r], reviews, "cat", 1, "values")


def test_failed_inherited_header_blocks_release(tmp_path):
    r = private_record()
    r["pages"].append({"page_number": 2, "status": "failed", "text": "", "error": "Decode failed"})
    r["assertions"][0]["evidence"]["context"] = [{"page": 2, "bbox": [0, 0, 100, 10], "text": "Model G1"}]
    reviews = ReviewStore(tmp_path / "r.sqlite3")
    reviews.decide(r, "a1", "accept", "reviewer", expected_fingerprint=record_fingerprint(r))
    with pytest.raises(ValueError, match="context-page"):
        export_bundle([r], reviews, "cat", 1, "coverage")


def test_rejected_source_cannot_be_published_as_empty_success(tmp_path):
    r = private_record()
    r.update(processing_status="rejected", pages=[], assertions=[])
    with pytest.raises(ValueError, match="rejected source"):
        export_bundle([r], ReviewStore(tmp_path / "r.sqlite3"), "cat", 1)


@pytest.mark.parametrize("mutation", [
    lambda b: b["documents"][0].update(ocr_text="LEAK"),
    lambda b: b["assertions"][0].update(evidence={"text": "LEAK"}),
    lambda b: b["assertions"][0].update(model="OTHER_MODEL"),
    lambda b: b["assertions"][0].update(unit="kW"),
    lambda b: b["assertions"][0].update(value=-2),
    lambda b: b["assertions"].append(copy.deepcopy(b["assertions"][0])),
])
def test_invalid_release_records_rejected(tmp_path, mutation):
    b = bundle(tmp_path)
    mutation(b)
    with pytest.raises(ValueError):
        validate_bundle(reseal(b))


def test_tampered_bundle_and_nonfinite_values(tmp_path):
    b = bundle(tmp_path)
    b["documents"][0]["title"] = "Tampered"
    with pytest.raises(ValueError, match="integrity"):
        validate_bundle(b)
    b["assertions"][0]["value"] = float("nan")
    with pytest.raises(ValueError):
        reseal(b)


def test_atomic_failure_keeps_old_catalog_and_history(tmp_path, monkeypatch):
    import vopt.search
    b = bundle(tmp_path)
    cat = Catalog(tmp_path / "catalog.sqlite3")
    cat.import_bundle(b)
    before = cat.info()
    new = copy.deepcopy(b)
    new["sequence"] = 2
    new["documents"][0]["title"] = "Never committed"
    def fail(db, docs, assertions):
        db.execute("CREATE TABLE transient_failure (x INTEGER)")
        raise RuntimeError("simulated index rebuild failure")
    monkeypatch.setattr(vopt.search, "build_index", fail)
    with pytest.raises(RuntimeError):
        cat.import_bundle(reseal(new))
    assert cat.info() == before
    with cat.connect() as db:
        assert "Never committed" not in db.execute("SELECT data FROM documents").fetchone()[0]
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='transient_failure'").fetchall()


def test_withdrawal_purges_old_snapshots_and_blocks_reintroduction(tmp_path):
    b = bundle(tmp_path)
    cat = Catalog(tmp_path / "catalog.sqlite3")
    cat.import_bundle(b)
    withdrawn = copy.deepcopy(b)
    withdrawn.update(sequence=2, documents=[], assertions=[], policy={"version": 2, "revoked_doc_ids": ["d1"], "revoked_assertion_ids": []})
    cat.import_bundle(reseal(withdrawn))
    assert cat.info()["document_count"] == 0
    assert cat.info()["eligible_snapshots"] == [2]
    with pytest.raises(ValueError, match="eligible"):
        cat.rollback(1)
    b["sequence"] = 3
    b["policy"]["version"] = 3
    with pytest.raises(ValueError, match="Revocations"):
        cat.import_bundle(reseal(b))


def test_profile_downgrade_no_numeric_queries_or_old_value_rollback(tmp_path):
    cat = Catalog(tmp_path / "c.sqlite3")
    cat.import_bundle(bundle(tmp_path))
    cov = bundle(tmp_path, "coverage", 2)
    cov["policy"]["version"] = 2
    cat.import_bundle(reseal(cov))
    assert cat.info()["profile"] == "coverage"
    assert cat.info()["eligible_snapshots"] == [2]
    assert cat.search("output power over 20 kW")["status"] in ("unsupported", "clarify")
    with pytest.raises(ValueError):
        cat.rollback(1)


def test_rollback_does_not_enable_replay(tmp_path):
    cat = Catalog(tmp_path / "c.sqlite3")
    first = bundle(tmp_path)
    cat.import_bundle(first)
    second = copy.deepcopy(first)
    second["sequence"] = 2
    second["documents"][0]["title"] = "Second edition metadata"
    cat.import_bundle(reseal(second))
    cat.rollback(1)
    assert cat.info()["highest_sequence"] == 2
    with pytest.raises(ValueError, match="Stale/replayed"):
        cat.import_bundle(reseal(second))


def test_readonly_discovery_and_source_change_invariance(tmp_path):
    b = bundle(tmp_path)
    path = tmp_path / "c.sqlite3"
    Catalog(path).import_bundle(b)
    cat = Catalog(path, readonly=True)
    before = cat.search("generator")
    (tmp_path / "private.txt").write_text("Changed secrets and unreleased horsepower")
    assert cat.search("generator") == before
    assert not cat.search("SOURCE_ONLY_SECRET")["results"]
    with pytest.raises(ValueError, match="Read-only"):
        cat.import_bundle(b)
