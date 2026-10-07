"""Guided choices preserve release boundaries and a single catalog snapshot."""
import copy
import json

import pytest

from vopt.catalog import Catalog
from vopt.ontology import ATTRIBUTES
from vopt.query import parse_query
from vopt.schema import seal_bundle
from vopt.workspace import Workspace
from test_interfaces import request, running_server
from test_lifecycle import bundle


def test_options_only_project_public_choices_not_source_or_numeric_claims(tmp_path):
    b = bundle(tmp_path)
    b["assertions"][0].update(conditions=["at full load"], variant="standard")
    cat = Catalog(tmp_path / "public.sqlite3")
    cat.import_bundle(seal_bundle(b))
    result = cat.options()
    assert result["numeric_filters"] is True
    assert result["sequence"] == 1
    assert result["integrity"] == seal_bundle(b)["integrity"]
    assert {option["key"] for option in result["attributes"]} == set(ATTRIBUTES)
    assert result["scopes"][0]["attributes"] == [{
        "key": "output_power", "label": "output power", "unit": "W",
        "conditions": ["at full load"], "qualifiers": ["rated"], "variants": ["standard"],
    }]
    serialized = json.dumps(result)
    for excluded in ("SOURCE_ONLY_SECRET", "30000", "source_uri", "evidence", "confidence", "value_max", "tolerance", "processing_status"):
        assert excluded not in serialized
    for option in result["attributes"]:
        assert parse_query(option["label"])["clauses"][0]["attributes"] == [
            {"attribute": option["key"], "qualifier": None}]


def test_scope_choices_do_not_mix_equipment_categories_or_attributes(tmp_path):
    b = bundle(tmp_path)
    b["documents"][0].update(models=["G1", "E1", "C1"], model_categories={"E1": "engine", "C1": "compressor"})
    horsepower = {**b["assertions"][0], "assertion_id": "a2", "model": "E1", "attribute": "horsepower", "unit": "hp", "value": 15}
    b["assertions"].append(horsepower)
    cat = Catalog(tmp_path / "public.sqlite3")
    cat.import_bundle(seal_bundle(b))
    scopes = {scope["model"]: scope for scope in cat.options()["scopes"]}
    assert scopes["C1"]["category"] == "compressor" and scopes["C1"]["attributes"] == []
    assert scopes["E1"]["category"] == "engine"
    assert [a["key"] for a in scopes["E1"]["attributes"]] == ["horsepower"]
    assert scopes["G1"]["category"] == "generator"
    assert [a["key"] for a in scopes["G1"]["attributes"]] == ["output_power"]


def test_coverage_options_disable_comparisons_and_never_restore_withdrawn_conditions(tmp_path):
    b = bundle(tmp_path)
    b["assertions"][0].update(conditions=["source condition no longer releasable"], variant="standard")
    cat = Catalog(tmp_path / "public.sqlite3")
    cat.import_bundle(seal_bundle(b))
    coverage = bundle(tmp_path, "coverage", 2)
    coverage["policy"]["version"] = 2
    coverage["assertions"][0]["variant"] = "standard"
    cat.import_bundle(seal_bundle(coverage))
    result = cat.options()
    assert result["profile"] == "coverage" and result["numeric_filters"] is False
    attribute = result["scopes"][0]["attributes"][0]
    assert attribute["unit"] == "W"  # Public ontology unit, not a specification claim.
    assert attribute["conditions"] == []
    assert attribute["qualifiers"] == ["rated"] and attribute["variants"] == ["standard"]
    assert "30000" not in json.dumps(result)
    assert "source condition" not in json.dumps(result)


def test_model_less_document_and_empty_release_remain_browsable(tmp_path):
    cat = Catalog(tmp_path / "public.sqlite3")
    with pytest.raises(ValueError, match="No metadata bundle"):
        cat.options()
    b = bundle(tmp_path)
    b["documents"][0]["models"] = []
    b["assertions"] = []
    cat.import_bundle(seal_bundle(b))
    result = cat.options()
    assert result["scopes"][0]["model"] == ""
    assert result["scopes"][0]["attributes"] == []
    assert len(result["attributes"]) == 13
    b.update(sequence=2, documents=[])
    cat.import_bundle(seal_bundle(b))
    assert cat.options()["scopes"] == []


def test_options_route_is_discovery_only(tmp_path, running_server):
    path = tmp_path / "public.sqlite3"
    cat = Catalog(path)
    cat.import_bundle(bundle(tmp_path))
    port = running_server(catalog=path)
    status, body, headers = request(port, "/api/options")
    assert status == 200 and json.loads(body) == cat.options()
    assert headers["Cache-Control"] == "no-store"
    assert request(port, "/api/options", method="POST", body="{}")[0] == 404
    review = running_server(workspace=Workspace(tmp_path / "private").path)
    assert request(review, "/api/options")[0] == 404


def test_empty_catalog_endpoint_exposes_supported_fields_without_inventing_scopes(tmp_path, running_server):
    path = tmp_path / "empty.sqlite3"
    b = bundle(tmp_path)
    b.update(documents=[], assertions=[])
    Catalog(path).import_bundle(seal_bundle(b))
    port = running_server(catalog=path)
    status, body, _ = request(port, "/api/options")
    result = json.loads(body)
    assert status == 200 and result["scopes"] == []
    assert len(result["attributes"]) == 13
    assert result["catalog_id"] == b["catalog_id"] and result["sequence"] == 1


def test_options_do_not_mix_new_assertions_with_old_catalog_identity(tmp_path, monkeypatch):
    cat = Catalog(tmp_path / "public.sqlite3")
    initial = bundle(tmp_path)
    cat.import_bundle(initial)
    expected = cat.options()
    replacement = copy.deepcopy(initial)
    replacement["sequence"] = 2
    replacement["documents"][0]["title"] = "Replacement document"
    replacement["assertions"][0]["attribute"] = "input_power"
    replacement = seal_bundle(replacement)
    writer = Catalog(cat.path)
    with cat.connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
    connect = cat.connect
    switched = []

    def interleaved_connect():
        db = connect()

        def swap_before_assertions(statement):
            if statement.startswith("SELECT data FROM assertions") and not switched:
                switched.append(True)
                writer.import_bundle(replacement)
        db.set_trace_callback(swap_before_assertions)
        return db

    monkeypatch.setattr(cat, "connect", interleaved_connect)
    assert cat.options() == expected
    assert switched
    assert writer.options()["sequence"] == 2
    assert writer.options()["scopes"][0]["attributes"][0]["key"] == "input_power"
