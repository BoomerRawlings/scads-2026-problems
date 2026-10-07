"""Authored regression tests, not an estimate of real-world retrieval accuracy."""
import json
import sqlite3

import pytest

from vopt.ontology import semantic_tokens, unit_value
from vopt.query import parse_query
from vopt.search import build_index, search


def document(doc_id="d1", models=None, **changes):
    return {"doc_id": doc_id, "title": "Acme Drill Service Manual", "manufacturer": "Acme", "models": models or ["AX-1"],
            "category": "drill", "language": "en", "revision": "1", "request_ref": f"request:{doc_id}:1",
            "processing_status": "complete", **changes}


def assertion(assertion_id, model="AX-1", attribute="input_voltage", value=120, doc_id="d1", **changes):
    unit = {"input_voltage": "V", "output_voltage": "V", "horsepower": "hp", "weight": "kg", "speed": "rpm", "input_power": "W", "pressure": "kPa"}.get(attribute, "W")
    return {"assertion_id": assertion_id, "doc_id": doc_id, "model": model, "variant": None, "attribute": attribute,
            "qualifier": "rated", "status": "reviewed", "value": value, "value_max": None, "unit": unit, **changes}


def catalog(documents=None, assertions=None, profile="values"):
    documents = documents or [document()]
    assertions = assertions if assertions is not None else [assertion("a1")]
    if profile == "coverage":
        assertions = [{k: v for k, v in item.items() if k not in {"value", "value_max", "unit", "tolerance"}} for item in assertions]
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE documents(doc_id TEXT PRIMARY KEY,data TEXT)")
    connection.execute("CREATE TABLE assertions(assertion_id TEXT PRIMARY KEY,doc_id TEXT,model TEXT,attribute TEXT,data TEXT)")
    connection.execute("CREATE TABLE catalog_meta(key TEXT PRIMARY KEY,value TEXT)")
    connection.execute("INSERT INTO catalog_meta VALUES (?,?)", ("profile", json.dumps(profile)))
    for item in documents:
        connection.execute("INSERT INTO documents VALUES (?,?)", (item["doc_id"], json.dumps(item)))
    for item in assertions:
        connection.execute("INSERT INTO assertions VALUES (?,?,?,?,?)", (item["assertion_id"], item["doc_id"], item["model"], item["attribute"], json.dumps(item)))
    build_index(connection, documents, assertions)
    return connection


@pytest.mark.parametrize("method", ["lexical", "semantic"])
def test_same_model_conjunction_does_not_join_specs_from_siblings(method):
    connection = catalog([document(models=["AX-1", "BX-2"])], [
        assertion("a1", "AX-1", "input_voltage", 120), assertion("a2", "AX-1", "horsepower", 1),
        assertion("b1", "BX-2", "input_voltage", 230), assertion("b2", "BX-2", "horsepower", 3)])
    result = search(connection, "drills with input voltage below 200 V and horsepower above 2 hp", method=method)
    assert result["status"] == "no_match"
    assert not result["results"]
    result = search(connection, "input voltage above 200 V and horsepower above 2 hp", method=method)
    assert [item["model"] for item in result["results"]] == ["BX-2"]
    assert result["results"][0]["matched_assertions"] == ["b1", "b2"]


def test_exact_model_identity_does_not_match_manual_title_sibling():
    connection = catalog([document(models=["AX-1", "AX-10"], title="AX-1 and AX-10")], [assertion("a1"), assertion("b1", "AX-10")])
    assert [row["model"] for row in search(connection, "AX-1")["results"]] == ["AX-1"]
    assert search(connection, "model AX-999")["status"] == "no_match"


def test_variant_constraints_do_not_mix_and_generic_fact_applies():
    connection = catalog(assertions=[assertion("v1", variant="EU", value=230), assertion("v2", variant="US", value=120),
                                    assertion("w1", attribute="weight", value=5, variant="EU"), assertion("w2", attribute="weight", value=10, variant="US"),
                                    assertion("s1", attribute="speed", value=3000)])
    assert search(connection, "input voltage above 200 V and weight above 8 kg")["status"] == "no_match"
    results = search(connection, "variant EU and speed > 2000 rpm")["results"]
    assert len(results) == 1 and results[0]["variant"] == "EU"


def test_ranges_units_and_tolerances_are_conservative():
    connection = catalog(assertions=[assertion("w1", attribute="weight", value=4.5359237),
                                    assertion("s1", attribute="speed", value=1000, value_max=2000),
                                    assertion("v1", value=120, tolerance={"minus": 5, "plus": 5, "unit": "V"})])
    assert search(connection, "weight at most 10 lbs")["results"]
    assert search(connection, "speed between 900 and 2100 rpm")["results"]
    assert search(connection, "speed > 1500 rpm")["status"] == "no_match"
    assert search(connection, "input voltage >= 120 V")["status"] == "no_match"
    assert search(connection, "input voltage >= 115 V")["results"]
    assert search(connection, "speed 1500 rpm")["status"] == "no_match"


def test_coverage_rejects_numeric_queries_and_retains_presence():
    connection = catalog(profile="coverage")
    assert search(connection, "input voltage")["results"]
    assert search(connection, "input voltage > 100 V")["status"] == "unsupported"
    assert "120" not in connection.execute("SELECT text FROM search_entries").fetchone()[0]


def test_missing_attribute_is_unknown_even_for_complete_document():
    connection = catalog()
    result = search(connection, "horsepower > 3 hp")
    assert result["status"] == "unknown"
    assert result["diagnostics"]["unknown_scopes"] == 1
    assert search(connection, "without horsepower")["status"] == "unsupported"


def test_unknown_and_incomplete_processing_are_visible():
    connection = catalog([document(processing_status="partial")])
    result = search(connection, "weight below 5 kg")
    assert result["status"] == "unknown"
    assert result["diagnostics"]["partial_documents"] == 1
    result = search(connection, "input voltage")
    assert result["results"][0]["processing_status"] == "partial"
    assert "partial" in result["results"][0]["warnings"][0]


def test_conditions_require_explicit_resolution():
    connection = catalog(assertions=[assertion("p1", attribute="horsepower", value=3, conditions=["at sea level"])])
    result = search(connection, "horsepower > 2 hp")
    assert result["status"] == "unknown"
    assert "conditions" in str(result["diagnostics"])
    assert search(connection, 'horsepower > 2 hp and condition "at sea level"')["results"]
    assert search(connection, 'horsepower > 2 hp and condition "high altitude"')["status"] == "unknown"


def test_conflicting_values_are_not_arbitrarily_selected():
    connection = catalog(assertions=[assertion("a1", value=120), assertion("a2", value=230)])
    result = search(connection, "input voltage >= 110 V")
    assert result["status"] == "conflict"
    assert result["diagnostics"]["conflicting_scopes"] == 1
    # Presence remains observed even when exact values conflict.
    assert search(connection, "input voltage")["results"]


def test_qualifier_ambiguity_and_explicit_rating():
    connection = catalog(assertions=[assertion("r1", attribute="horsepower", value=1, qualifier="rated"),
                                    assertion("p1", attribute="horsepower", value=3, qualifier="peak")])
    assert search(connection, "horsepower > 2 hp")["status"] == "unknown"
    assert search(connection, "peak horsepower > 2 hp")["results"]
    assert search(connection, "rated horsepower > 2 hp")["status"] == "no_match"


def test_revisions_preserved_and_disagreements_warned():
    connection = catalog([document("d1", revision="1"), document("d2", revision="2")],
                         [assertion("a1", value=120), assertion("a2", value=230, doc_id="d2")])
    results = search(connection, "input voltage > 200 V")["results"]
    assert len(results) == 1 and results[0]["revision"] == "2"
    assert "revision 1" in results[0]["warnings"][0]
    assert results[0]["request_ref"] == "request:d2:1"


def test_boolean_disjunction_and_supported_negation():
    connection = catalog([document("d1"), document("d2", models=["S-1"], category="saw")],
                         [assertion("w1", attribute="weight", value=3), assertion("w2", "S-1", "weight", 4, doc_id="d2")])
    assert len(search(connection, "(drills or saws) and weight below 5 kg")["results"]) == 2
    assert [r["doc_id"] for r in search(connection, "not drills")["results"]] == ["d2"]
    assert [r["doc_id"] for r in search(connection, "weight not above 3 kg")["results"]] == ["d1"]
    assert [r["doc_id"] for r in search(connection, "weight not 3 kg")["results"]] == ["d2"]
    assert search(connection, "drills or saws below 5 kg")["status"] == "clarify"


@pytest.mark.parametrize("query", ["input voltage above 120 V and weight below 5 bananas", "weight -1 kg", "pressure > 10 furlongs",
                                   "waterproof drills", "drills below 30 decibels", "input voltage 120 V AC", "weight approximately 5 kg",
                                   "input voltage 120 V and not waterproof", "input power 746 W and horsepower 1 kW",
                                   "weight about 5 kg", "direct current below 5 A"])
def test_unsupported_predicates_are_not_silently_dropped(query):
    result = parse_query(query)
    assert result["status"] in {"unsupported", "clarify"}
    assert not result["clauses"]


@pytest.mark.parametrize("query", ["power above 100 W", "voltage 120 V", "120 V", "weight below 5", "drills or saws under 5 kg", "(drills or)", "drills and", "((drills)"])
def test_ambiguity_yields_no_executable_plan(query):
    result = parse_query(query)
    assert result["status"] in {"unsupported", "clarify"}
    assert not result["clauses"]


def test_output_voltage_distinct_from_input_voltage():
    connection = catalog([document(category="generator")], [assertion("out", attribute="output_voltage", value=250)])
    assert search(connection, "generators with output voltage >= 125 V")["results"]
    assert search(connection, "input voltage >= 125 V")["status"] == "unknown"
    assert search(connection, "voltage >= 125 V")["status"] == "clarify"


def test_physical_roles_never_convert_input_power_to_horsepower():
    connection = catalog(assertions=[assertion("p1", attribute="input_power", value=746)])
    assert search(connection, "horsepower > 0.9 hp")["status"] == "unknown"
    assert search(connection, "input power between 0.7 kW and 1 kW")["results"]
    with pytest.raises(ValueError):
        unit_value(746, "W", "horsepower")


def test_literal_injection_cannot_execute_sql_or_fts_operators():
    connection = catalog()
    for value in ['"; DROP TABLE documents; --', "AX-1 OR 1=1", "NEAR(foo bar)", "input voltage' OR '1'='1"]:
        result = search(connection, value)
        assert not result["results"]
    assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_rebuild_is_transactional_and_removes_derived_metadata():
    connection = catalog()
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    build_index(connection, [], [])
    assert connection.in_transaction
    assert connection.execute("SELECT count(*) FROM search_fts").fetchone()[0] == 0
    connection.rollback()
    assert connection.execute("SELECT count(*) FROM search_fts").fetchone()[0] == 1
    assert search(connection, "input voltage")["results"]
    build_index(connection, [document()], [])
    assert "120" not in connection.execute("SELECT text FROM search_entries").fetchone()[0]
    assert "input voltage" not in connection.execute("SELECT text FROM search_fts").fetchone()[0]


def test_private_fields_cannot_enter_search_indexes():
    connection = catalog()
    with pytest.raises(ValueError, match="released document"):
        build_index(connection, [document(source_uri="secret.pdf")], [])
    with pytest.raises(ValueError, match="released assertions"):
        build_index(connection, [document()], [assertion("a1", evidence={"text": "private sentinel"})])
    assert search(connection, "private sentinel")["status"] == "no_match"


def test_ranker_labels_and_determinism():
    connection = catalog()
    lexical = search(connection, "supply voltage", method="lexical")
    semantic = search(connection, "supply voltage", method="semantic")
    assert lexical["results"] and semantic["results"]
    assert "FTS5" in lexical["scoring"]
    assert "not pretrained" in semantic["scoring"]
    assert semantic == search(connection, "supply voltage", method="semantic")
    assert semantic_tokens("supply voltage") == semantic_tokens("input voltage")


def test_resource_bounds_and_bad_arguments():
    connection = catalog()
    with pytest.raises(ValueError):
        search(connection, "drills", limit=0)
    with pytest.raises(ValueError):
        search(connection, "drills", method="remote")
    assert parse_query("x" * 2001)["status"] == "unsupported"
    assert parse_query("(" * 9 + "drills" + ")" * 9)["status"] == "unsupported"
    assert parse_query("")["status"] == "clarify"


def test_presence_and_inequalities_support_paraphrases():
    connection = catalog(assertions=[assertion("a1", attribute="input_current", value=4, unit="A"), assertion("w1", attribute="weight", value=2)])
    assert search(connection, "find manuals containing amperage for drills")["results"]
    assert search(connection, "drills weighing less than 3 kilograms and current draw at most 5 amps")["results"]


def test_quoted_condition_boolean_word_is_literal():
    connection = catalog(assertions=[assertion("a1", attribute="horsepower", value=3, conditions=["warm and dry"])])
    assert search(connection, 'horsepower > 2 hp and condition "warm and dry"')["results"]


def test_direct_answer_request_explicitly_deferred():
    assert parse_query("what is the weight of model AX-1")["status"] == "unsupported"


def test_exact_released_title_revision_language_and_document_identity():
    connection = catalog([document(title="Series 2000 (service)", revision="2026.1")])
    assert search(connection, 'title "Series 2000 (service)" and revision 2026.1 and language en and doc_id d1')["results"]
    assert search(connection, "revision 2025")["status"] == "no_match"


def test_pure_numeric_models_do_not_hijack_quantities():
    connection = catalog([document(models=["3000"])], [assertion("s1", model="3000", attribute="speed", value=3000)])
    assert search(connection, "speed at least 3000 rpm")["results"]
    assert search(connection, "model 3000")["results"]


def test_conversion_roundoff_does_not_create_false_conflict():
    connection = catalog(assertions=[assertion("w1", attribute="weight", value=4.5359237),
                                    assertion("w2", attribute="weight", value=10, unit="lb")])
    assert search(connection, "weight below 5 kg")["results"]


def test_document_without_product_model_still_discoverable():
    doc = document()
    doc["models"] = []
    connection = catalog([doc], [])
    assert search(connection, 'title "Acme Drill Service Manual"')["results"][0]["model"] == ""
    assert search(connection, "doc_id d1")["results"]
    assert search(connection, "input voltage")["status"] == "unknown"


def test_fts_shadow_segments_do_not_retain_withdrawn_terms(tmp_path):
    path = tmp_path / "index.sqlite"
    connection = sqlite3.connect(path)
    sentinel = "uniquewithdrawnsentinel583791"
    doc = document(title=sentinel)
    build_index(connection, [doc], [])
    connection.commit()
    assert sentinel.encode() in path.read_bytes()
    build_index(connection, [document(title="Safe remaining title")], [])
    connection.commit()
    shadow = b"".join(row[0] for row in connection.execute("SELECT block FROM search_fts_data"))
    assert sentinel.encode() not in shadow
    connection.close()
    assert sentinel.encode() not in path.read_bytes()


def test_model_categories_override_compendium_category_without_cross_model_leak():
    connection = catalog([document(models=["C-1", "G-1"], category="workshop equipment", model_categories={"C-1": "compressor", "G-1": "generator"})],
                         [assertion("c1", "C-1", "horsepower", 1.5), assertion("g1", "G-1", "horsepower", 3)])
    assert [r["model"] for r in search(connection, "compressors with horsepower > 1 hp")["results"]] == ["C-1"]
    assert not search(connection, "compressors with horsepower > 2 hp")["results"]
    assert search(connection, "generators with horsepower > 2 hp")["results"]


@pytest.mark.parametrize("condition", ["approximate value; tolerance unspecified", "Unresolved footnote marker *"])
def test_unknown_bound_cannot_be_resolved_by_selecting_its_label(condition):
    connection = catalog(assertions=[assertion("a1", attribute="speed", value=600, conditions=[condition])])
    result = search(connection, f'speed > 500 rpm and condition "{condition}"')
    assert result["status"] == "unknown"
    assert not result["results"]
    assert result["diagnostics"]["details"][0]["available_conditions"] == [condition]
    assert result["diagnostics"]["details"][0]["available_qualifiers"] == ["rated"]
    assert search(connection, "speed")["results"]


def test_unknown_diagnostics_reveal_only_released_refinement_labels():
    connection = catalog(assertions=[assertion("a1", attribute="horsepower", value=3, qualifier="unspecified", conditions=["at sea level"])])
    detail = search(connection, "horsepower > 2 hp")["diagnostics"]["details"][0]
    assert detail["available_conditions"] == ["at sea level"]
    assert detail["available_qualifiers"] == ["unspecified"]
    assert detail["request_ref"] == "request:d1:1" and detail["title"] == "Acme Drill Service Manual" and detail["revision"] == "1"
    assert search(connection, 'unspecified horsepower > 2 hp and condition "at sea level"')["results"]


def test_catalog_known_model_with_spaces_is_not_truncated():
    connection = catalog([document(models=["VG-959 QMC", "VG-959"])],
                         [assertion("v1", model="VG-959 QMC", attribute="horsepower", value=5.25),
                          assertion("v2", model="VG-959", attribute="horsepower", value=1)])
    assert [r["model"] for r in search(connection, "model VG-959 QMC and horsepower > 5 hp")["results"]] == ["VG-959 QMC"]


def test_sentence_punctuation_after_units_is_accepted_without_partial_numbers():
    connection = catalog()
    assert search(connection, "Find manuals with input voltage at least 100 V.")["results"]
    assert search(connection, "input voltage between 100 and 130 V.")["results"]
    assert parse_query("input voltage 120 V.5")["status"] != "ready"


def test_compound_energy_unit_cannot_be_parsed_as_power_plus_keyword():
    connection = catalog([document(title="Drill hours manual")], [assertion("w1", attribute="input_power", value=1000)])
    assert search(connection, "input power 1 kilowatt-hours")["status"] in {"unsupported", "clarify"}
    assert parse_query("input power 100W-200W")["status"] == "ready"


@pytest.mark.parametrize("unit", ["V/m", "V / m", "V*A", "V·A"])
def test_unsupported_composite_units_do_not_reduce_to_voltage(unit):
    assert parse_query("input voltage 120 " + unit, [document(models=["m", "A"])])["status"] != "ready"


def test_attribute_phrase_does_not_invent_an_equipment_category_predicate():
    connection = catalog([document(models=["C-1", "E-1"], category="workshop equipment", model_categories={"C-1": "compressor", "E-1": "engine"})],
                         [assertion("c1", "C-1", "horsepower", 1.5), assertion("e1", "E-1", "horsepower", 50)])
    assert len(search(connection, "engine horsepower")["results"]) == 2
    assert [r["model"] for r in search(connection, "compressors with engine horsepower")["results"]] == ["C-1"]
    assert [r["model"] for r in search(connection, "engines with horsepower")["results"]] == ["E-1"]
    assert parse_query("generator voltage")["attributes"] == ["output_voltage"]
