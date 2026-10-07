"""Engineering fixtures, never presented as real-manual accuracy evidence."""

import copy
import json
import os
from pathlib import Path
import socket
import time
import textwrap

import pymupdf
import pytest

from vopt import ingest
from vopt import extraction_worker
from vopt.extract import extract_assertions, reextract_record


def document(models=None, **extra):
    return {"doc_id": "engineering-fixture", "title": "ENGINEERING TEST FIXTURE", "manufacturer": "Fixture",
            "models": models if models is not None else ["T100"], "category": "saw", "language": "en",
            "revision": "test-1", "source_uri": "fixture:generated", "rights": {"basis": "test fixture", "evidence_url": "", "attribution": ""}, **extra}


def line(text, x=30, y=40, width=None):
    return {"text": text, "bbox": [x, y, x + (width if width is not None else len(text) * 6), y + 12]}


def page(lines, number=1, **extra):
    return {"page_number": number, "width": 600, "height": 800, "status": "ok", "engine": "fixture",
            "text": "\n".join(item["text"] for item in lines), "lines": lines, "error": None, **extra}


def pdf_fixture(path, pages=1, scanned=False, rotated=False):
    """Create isolated software-test PDFs; these are not publication artifacts."""
    pdf = pymupdf.open()
    for index in range(pages):
        current = pdf.new_page(width=600, height=400)
        for text, y in [("ENGINEERING TEST FIXTURE", 45), ("Model T100", 80), ("Input voltage: 230 V", 130),
                        ("Input power: 1.5 kW", 170), ("No-load speed: 2800 rpm", 210)]:
            current.insert_text((40, y), text, fontsize=20)
        if rotated:
            current.set_rotation(90)
    if scanned:
        output = pymupdf.open()
        for source in pdf:
            pixmap = source.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            target = output.new_page(width=source.rect.width, height=source.rect.height)
            target.insert_image(target.rect, stream=pixmap.tobytes("png"))
        pdf.close()
        pdf = output
    pdf.set_metadata({"title": "ENGINEERING TEST FIXTURE - not empirical accuracy evidence"})
    pdf.save(path)
    pdf.close()
    return path


def test_label_units_qualifiers_and_ranges():
    data = page([line("Rated input power: 1.2 kW", y=20), line("Mechanical output power: 800 W", y=50),
                 line("Peak horsepower: 2 hp", y=80), line("No-load speed: 0-2800 rpm", y=110),
                 line("Blade diameter: 10 inches", y=140), line("Input voltage: 220-240 V", y=170)])
    values = {item["attribute"]: item for item in extract_assertions([data], document())}
    assert values["input_power"]["value"] == 1200 and values["input_power"]["qualifier"] == "rated"
    assert values["output_power"]["value"] == 800
    assert values["horsepower"]["qualifier"] == "peak" and values["horsepower"]["unit"] == "hp"
    assert (values["speed"]["value"], values["speed"]["value_max"], values["speed"]["qualifier"]) == (0, 2800, "no_load")
    assert values["blade_diameter"]["value"] == 254
    assert values["input_voltage"]["value_max"] == 240
    assert all(item["status"] == "candidate" and item["evidence"]["page"] == 1 for item in values.values())


def test_multi_model_geometry_is_not_shared_across_models():
    data = page([line("Model", 30, 20), line("AX100", 250, 20, 35), line("AX200", 380, 20, 35),
                 line("Input power (W)", 30, 50), line("500", 250, 50, 35), line("750", 380, 50, 35),
                 line("Weight (kg)", 30, 80), line("2.5", 250, 80, 35), line("3.0", 380, 80, 35)])
    values = extract_assertions([data], document(["AX100", "AX200"]))
    assert {(item["model"], item["attribute"], item["value"]) for item in values} == {
        ("AX100", "input_power", 500), ("AX200", "input_power", 750), ("AX100", "weight", 2.5), ("AX200", "weight", 3)}
    assert all(item["evidence"]["context"][0]["text"] == "Model AX100 AX200" for item in values)
    assert extract_assertions([data], document(["AX100", "AX200"]), method="baseline") == []


def test_multi_model_missing_or_centered_header_abstains():
    assert extract_assertions([page([line("Input power: 500 W")])], document(["AX100", "AX200"])) == []
    data = page([line("AX100", 200, 20, 30), line("AX200", 400, 20, 30),
                 line("Input power", 30, 50), line("500 W", 300, 50, 30)])
    assert extract_assertions([data], document(["AX100", "AX200"])) == []


def test_explicit_model_in_row_and_no_numeric_model_capture():
    data = page([line("AX100 Input power (W): 500"), line("AX200 Input power (W): 750", y=80)])
    values = extract_assertions([data], document(["AX100", "AX200"]))
    assert [(item["model"], item["value"]) for item in values] == [("AX100", 500), ("AX200", 750)]


def test_unqualified_power_and_incompatible_unit_abstain():
    data = page([line("Power: 1200 W"), line("Input voltage: 220 kg", y=80), line("Weight: 23", y=110),
                 line("Input power (W): 200 bananas", y=140), line("Output current: 15 A", y=170)])
    assert extract_assertions([data], document()) == []


def test_output_voltage_and_ambiguous_generator_roles():
    data = page([line("Output voltage: 125/250 V"), line("Voltage: 240 V", y=80), line("Input voltage: 12 V", y=120)])
    values = extract_assertions([data], document(category="generator"))
    assert [(item["attribute"], item["value"]) for item in values] == [("output_voltage", "125/250"), ("input_voltage", 12)]


def test_tolerance_units_and_discrete_ratings_preserved():
    data = page([line("Weight: 2500 +/- 50 g"), line("Frequency: 50/60 Hz", y=80), line("Pressure: 1.5 bar", y=120)])
    values = {item["attribute"]: item for item in extract_assertions([data], document())}
    assert values["weight"]["value"] == 2.5
    assert values["weight"]["tolerance"] == {"minus": .05, "plus": .05, "unit": "kg"}
    assert values["frequency"]["value"] == "50/60" and values["frequency"]["value_max"] is None
    assert values["pressure"]["value"] == 150


def test_footnote_scoped_to_marked_model_and_unknown_note_retained():
    data = page([line("AX100", 250, 20, 35), line("AX200", 380, 20, 35),
                 line("Speed (rpm)", 30, 50), line("2000*", 250, 50, 35), line("3000", 380, 50, 35),
                 line("* No-load speed with optional attachment", 30, 150)])
    values = {item["model"]: item for item in extract_assertions([data], document(["AX100", "AX200"]))}
    assert values["AX100"]["qualifier"] == "no_load"
    assert "optional attachment" in values["AX100"]["conditions"][0]
    assert "conditions" not in values["AX200"] and values["AX200"]["qualifier"] == "unspecified"
    missing = extract_assertions([page([line("Input power: 100 W*")])], document())
    assert missing[0]["conditions"] == ["Unresolved footnote marker *"]


def test_conditions_and_capacity_roles_not_discarded():
    data = page([line("Fuel capacity: 2 L"), line("Oil capacity: 500 mL", y=70), line("Gross weight: 10 kg", y=100),
                 line("Input power: 50 W at 120 V", y=130)])
    values = extract_assertions([data], document())
    assert [(item["value"], item["conditions"][0]) for item in values[:3]] == [(2, "Fuel capacity"), (.5, "Oil capacity"), (10, "Gross weight")]
    assert values[3]["conditions"] == ["at 120 V"]


def test_failed_pages_and_missing_identity_create_no_coverage_claims():
    assert extract_assertions([page([line("Input voltage: 230 V")], status="failed")], document()) == []
    assert extract_assertions([page([line("Input voltage: 230 V")])], document([])) == []


def test_only_explicitly_continued_headers_cross_pages():
    first = page([line("AX100", 250, 20, 35), line("AX200", 380, 20, 35)])
    second = page([line("Specifications (continued)", 30, 20), line("Weight (kg)", 30, 50), line("2", 250, 50, 35), line("3", 380, 50, 35)], number=2)
    values = extract_assertions([first, second], document(["AX100", "AX200"]))
    assert len(values) == 2 and values[0]["evidence"]["context"][0]["page"] == 1
    second["lines"][0]["text"] = "Other specifications"
    assert extract_assertions([first, second], document(["AX100", "AX200"])) == []


def test_assertion_id_stable_but_evidence_and_revision_changes_invalidate():
    data = page([line("Input power: 100 W")])
    first = extract_assertions([data], document())
    assert first == extract_assertions([copy.deepcopy(data)], document())
    changed = copy.deepcopy(data)
    changed["lines"][0]["text"] = "Input power: 200 W"
    assert first[0]["assertion_id"] != extract_assertions([changed], document())[0]["assertion_id"]


def test_native_pdf_has_actual_geometry_and_stable_checkpoint(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["processing_status"] == "complete"
    assert result["coverage"]["successful_pages"] == 1
    assert result["pages"][0]["engine"] == "pymupdf-text"
    assert {item["attribute"] for item in result["assertions"]} == {"input_voltage", "input_power", "speed"}
    assert all(0 <= item["evidence"]["bbox"][0] < item["evidence"]["bbox"][2] <= 600 for item in result["assertions"])
    monkeypatch.setattr(ingest.PageProcess, "read_page", lambda *args: pytest.fail("successful cache must not rerun"))
    assert result == ingest.ingest_pdf(source, document(), tmp_path / "private")


def test_pdf_native_multimodel_cells(tmp_path):
    path = tmp_path / "table.pdf"
    pdf = pymupdf.open()
    current = pdf.new_page()
    for text, x, y in [("ENGINEERING TEST FIXTURE", 30, 40), ("AX100", 250, 80), ("AX200", 380, 80),
                        ("Input power (W)", 30, 110), ("500", 250, 110), ("750", 380, 110),
                        ("Weight (kg)", 30, 140), ("2.5", 250, 140), ("3.0", 380, 140)]:
        current.insert_text((x, y), text, fontsize=12)
    pdf.save(path)
    pdf.close()
    result = ingest.ingest_pdf(path, document(["AX100", "AX200"]), tmp_path / "out")
    assert {(item["model"], item["attribute"], item["value"]) for item in result["assertions"]} == {
        ("AX100", "input_power", 500), ("AX200", "input_power", 750), ("AX100", "weight", 2.5), ("AX200", "weight", 3)}


def test_page_limit_records_denominator_and_resumes(tmp_path):
    source = pdf_fixture(tmp_path / "fixture.pdf", pages=3)
    first = ingest.ingest_pdf(source, document(), tmp_path / "private", max_pages=1)
    assert first["coverage"] == {"total_pages": 3, "successful_pages": 1, "failed_pages": 2, "fraction": 1 / 3}
    assert first["processing_status"] == "partial" and "page_limit" in first["pages"][2]["error"]
    second = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert second["cache_key"] == first["cache_key"] and second["coverage"]["successful_pages"] == 3
    assert all(page["attempts"] == 1 for page in second["pages"])


def test_failure_is_bounded_and_explicit_reset_retries(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original = ingest._read_page
    calls = []
    def failing(*args):
        calls.append(True)
        raise RuntimeError("controlled OCR failure")
    monkeypatch.setattr(ingest, "_read_page", failing)
    for _ in range(5):
        result = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert len(calls) == 3 and result["pages"][0]["attempts"] == 3
    assert result["processing_status"] == "partial" and "controlled OCR failure" in result["pages"][0]["error"]
    monkeypatch.setattr(ingest, "_read_page", original)
    reset = ingest.ingest_pdf(source, document(), tmp_path / "private", resume=False, isolate_pages=False)
    assert reset["processing_status"] == "complete" and reset["pages"][0]["attempts"] == 1


def test_partial_retry_only_failed_page(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf", pages=2)
    original = ingest._read_page
    calls = []
    def fail_second(page, force):
        calls.append(page.number)
        if page.number == 1:
            raise RuntimeError("controlled page failure")
        return original(page, force)
    monkeypatch.setattr(ingest, "_read_page", fail_second)
    first = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert first["coverage"]["successful_pages"] == 1 and len(first["assertions"]) == 3
    monkeypatch.setattr(ingest, "_read_page", lambda page, force: (calls.append(page.number), original(page, force))[1])
    second = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert calls == [0, 1, 1] and second["processing_status"] == "complete"


def test_interrupt_checkpoint_survives(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf", pages=2)
    original = ingest._read_page
    def interrupted(page, force):
        if page.number == 1:
            raise KeyboardInterrupt()
        return original(page, force)
    monkeypatch.setattr(ingest, "_read_page", interrupted)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    saved = json.loads(next((tmp_path / "private").rglob("record.json")).read_text())
    assert saved["pages"][0]["status"] == "ok" and "interrupted" in saved["pages"][1]["error"]
    monkeypatch.setattr(ingest, "_read_page", original)
    resumed = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert resumed["processing_status"] == "complete" and all(item["attempts"] == 1 for item in resumed["pages"])


def test_cache_identity_source_document_config_and_corruption(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    first = ingest.ingest_pdf(source, document(), tmp_path / "private")
    renamed = ingest.ingest_pdf(source, document(doc_id="different"), tmp_path / "private")
    assert first["cache_key"] != renamed["cache_key"]
    revised = ingest.ingest_pdf(source, document(revision="test-2"), tmp_path / "private")
    assert first["cache_key"] == revised["cache_key"] and revised["document"]["revision"] == "test-2"
    cache = tmp_path / "private" / "cache" / first["cache_key"] / "record.json"
    cache.write_text("{malformed")
    repaired = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert repaired["processing_status"] == "complete" and "Invalid cache" in repaired["warnings"][0]
    monkeypatch.setattr(ingest, "RENDER_DPI", 180)
    configured = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert configured["cache_key"] != first["cache_key"]
    with pymupdf.open(source) as pdf:
        pdf[0].insert_text((40, 270), "changed source")
        updated = tmp_path / "updated.pdf"
        pdf.save(updated)
    changed = ingest.ingest_pdf(updated, document(), tmp_path / "private")
    assert changed["sha256"] != first["sha256"] and changed["cache_key"] != configured["cache_key"]


def test_invalid_pdf_and_identity_warning(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a PDF")
    rejected = ingest.ingest_pdf(bad, document(), tmp_path / "private")
    assert rejected["processing_status"] == "rejected" and rejected["errors"]
    source = pdf_fixture(tmp_path / "fixture.pdf")
    unknown = ingest.ingest_pdf(source, document([]), tmp_path / "private")
    assert unknown["assertions"] == [] and unknown["warnings"][0].startswith("identity_required")
    with pytest.raises(ValueError, match="positive integer"):
        ingest.ingest_pdf(source, document(), tmp_path / "private", max_pages=0)


def test_missing_local_models_fails_page_without_network(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "scan.pdf", scanned=True)
    def missing():
        raise RuntimeError("Offline OCR asset missing; no download attempted")
    monkeypatch.setattr(ingest, "local_ocr_assets", missing)
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("no networking allowed"))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert result["processing_status"] == "partial"
    assert "Offline OCR asset missing" in result["pages"][0]["error"] and not result["assertions"]


def test_actual_local_ocr_on_raster_pdf_network_blocked(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "scan.pdf", scanned=True)
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("OCR must run without networking"))
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("OCR must run without networking"))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["processing_status"] == "complete", result["pages"][0]["error"]
    assert result["pages"][0]["engine"] == "rapidocr-onnx"
    values = {item["attribute"]: item["value"] for item in result["assertions"]}
    assert values["input_voltage"] == 230 and values["input_power"] == 1500 and values["speed"] == 2800


def test_rotated_native_geometry_in_rendered_coordinates(tmp_path):
    source = pdf_fixture(tmp_path / "rotated.pdf", rotated=True)
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["pages"][0]["width"] == 400 and result["pages"][0]["height"] == 600
    assert all(0 <= item["bbox"][0] <= item["bbox"][2] <= 400 and 0 <= item["bbox"][1] <= item["bbox"][3] <= 600 for item in result["pages"][0]["lines"])
    assert {item["attribute"] for item in result["assertions"]} == {"input_voltage", "input_power", "speed"}


def test_unknown_component_identity_is_not_assigned_to_whole_assembly():
    data = page([line("Generator model X55", y=20), line("Output power: 100 W", y=50)])
    assert extract_assertions([data], document(["M18"])) == []


def test_model_prefix_and_numeric_identifiers_do_not_overlap_values():
    data = page([line("Model HR-28 Output power: 1500 W"), line("Input power: 500 W", y=90)])
    values = extract_assertions([data], document(["HR", "HR-28", "500"]))
    assert len(values) == 1 and values[0]["model"] == "HR-28"


def test_wrapped_generator_rating_keeps_power_voltage_and_frequency_roles():
    data = page([line("Rated generator output: 30-kw, 3-phase,", 30, 20),
                 line("60-cycle, 125-v or 30-kw (80 percent", 130, 34),
                 line("power factor), 3-phase, 60-cycle, 250-v", 130, 48)])
    values = extract_assertions([data], document(["M18"], category="generator"))
    assert {(item["attribute"], item["value"], item["qualifier"]) for item in values} == {
        ("output_power", 30000, "rated"), ("output_voltage", 125, "rated"), ("output_voltage", 250, "rated"), ("frequency", 60, "rated")}
    assert all(item["attribute"] != "input_voltage" for item in values)
    assert {item["variant"] for item in values} == {"output configuration: 125 V", "output configuration: 250 V"}


def test_cache_integrity_detects_valid_json_tampering(tmp_path):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    first = ingest.ingest_pdf(source, document(), tmp_path / "private")
    cache = tmp_path / "private" / "cache" / first["cache_key"] / "record.json"
    saved = json.loads(cache.read_text())
    saved["pages"][0]["lines"][2]["text"] = "Input voltage: 999 V"
    cache.write_text(json.dumps(saved))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert "Invalid cache" in result["warnings"][0]
    assert {item["value"] for item in result["assertions"] if item["attribute"] == "input_voltage"} == {230}


def test_prose_horsepower_never_takes_operating_rpm_as_hp():
    data = page([line("A gasoline engine of 5.25 horsepower at 2200 revolutions per minute")])
    values = extract_assertions([data], document(category="engine"))
    assert len(values) == 1 and values[0]["attribute"] == "horsepower" and values[0]["value"] == 5.25
    assert values[0]["conditions"] == ["at 2200"]
    fractional = extract_assertions([page([line("Driven by a 1 1/2-horsepower gasoline engine")])], document(category="engine"))
    assert len(fractional) == 1 and fractional[0]["value"] == 1.5


def test_unqualified_current_is_not_automatically_electrical_input():
    data = page([line("Current range: 50 to 400 amperes"), line("Rated current: 20 A", y=100)])
    assert extract_assertions([data], document()) == []


def test_prose_model_mentions_never_become_table_header():
    data = page([line("AX100 has been assigned to all AX200 units", 200, 20),
                 line("Weight (kg)", 30, 50), line("3.0", 380, 50, 35)])
    assert extract_assertions([data], document(["AX100", "AX200"])) == []


def test_three_discrete_values_abstain_without_partial_numeric_claim():
    assert extract_assertions([page([line("Frequency: 50/60/400 Hz")])], document()) == []


def test_reextract_is_offline_idempotent_and_does_not_mutate_source(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original = ingest.ingest_pdf(source, document(), tmp_path / "private")
    before = copy.deepcopy(original)
    monkeypatch.setattr(ingest, "_ocr_engine", lambda: pytest.fail("reextract cannot initialize OCR"))
    source.unlink()
    revised = reextract_record(original)
    assert original == before and revised == reextract_record(revised)
    assert revised["assertions"] == original["assertions"]
    correction = copy.deepcopy(revised)
    correction["document"]["models"] = ["T200"]
    corrected = reextract_record(correction)
    assert corrected["assertions"] == []  # Source explicitly says T100: do not silently relabel it T200.
    assert original["document"]["models"] == ["T100"]


def test_extractor_update_reuses_page_cache_and_invalidates_record_version(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert original["processing_status"] == "complete", original
    signature = ingest.processing_signature()
    signature["code"]["extract.py"] = "new-extraction-code"
    monkeypatch.setattr(ingest, "processing_signature", lambda: signature)
    monkeypatch.setattr(ingest.PageProcess, "read_page", lambda *args: pytest.fail("parser update cannot re-OCR unchanged pages"))
    import vopt.extract
    monkeypatch.setattr(vopt.extract, "extraction_signature", lambda: "changed-extractor")
    revised = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert revised["cache_key"] == original["cache_key"] and revised["processing_version"] != original["processing_version"]
    assert revised["page_processing_version"] == original["page_processing_version"]


def test_percent_tolerance_is_relative_and_spaced_untyped_numbers_abstain():
    values = extract_assertions([page([line("Weight: 10 kg +/- 5%")])], document())
    assert values[0]["value"] == 10 and values[0]["tolerance"] == {"minus": .5, "plus": .5, "unit": "kg"}
    assert extract_assertions([page([line("Weight (kg): 1 234")])], document()) == []


def test_actual_local_ocr_rotated_scan_keeps_reading_order_and_evidence(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "rotated-scan.pdf", scanned=True, rotated=True)
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("OCR must run offline"))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["processing_status"] == "complete", result["pages"][0]["error"]
    values = {item["attribute"]: item["value"] for item in result["assertions"]}
    assert values["input_voltage"] == 230 and values["input_power"] == 1500
    assert all(0 <= item["evidence"]["bbox"][0] < item["evidence"]["bbox"][2] <= 400 and 0 <= item["evidence"]["bbox"][1] < item["evidence"]["bbox"][3] <= 600 for item in result["assertions"])


def test_dry_weight_conditions_exclude_leaders_and_value_and_approximation_is_explicit():
    data = page([line("Weight, less fuel and water .......... 4,194 lb"), line("Speed: about 600 rpm", y=80)])
    values = {item["attribute"]: item for item in extract_assertions([data], document())}
    assert values["weight"]["conditions"] == ["less fuel and water"]
    assert values["speed"]["value"] == 600 and values["speed"]["conditions"] == ["approximate value; tolerance unspecified"]


def test_recoverable_decoder_error_cannot_be_called_complete(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    responses = iter(["", "format error: invalid code in 2d faxd"])
    monkeypatch.setattr(pymupdf.TOOLS, "mupdf_warnings", lambda **kwargs: next(responses))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert result["processing_status"] == "partial" and result["pages"][0]["status"] == "failed"
    assert "PDF decoder" in result["pages"][0]["error"] and result["assertions"] == []


def test_single_model_does_not_capture_component_specs_transport_examples_or_procedures():
    component = page([line("Make .... Engine Company", y=20), line("Model ........ XZLC-3", y=40), line("Weight: 945 lb", y=70)])
    transport = page([line("Example", y=20), line("Total weight of car and load: 169000 lb", y=50), line("Permissible weight of load: 132000 lb", y=80)])
    procedure = page([line("Engine speed is about 600 rpm", y=20), line("If speed of 1200 rpm is reached,", y=50), line("Of speed may vary from 40 to 70 rpm", y=80)])
    assert extract_assertions([component, transport, procedure], document(["M18"], category="generator")) == []


def test_render_pixel_guard_on_actual_oversized_pdf_page(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_RENDER_PIXELS", 1_000_000)
    pdf = pymupdf.open()
    current = pdf.new_page(width=3000, height=3000)
    pixels = ingest._render_array(current)
    assert 0 < pixels.shape[0] * pixels.shape[1] <= 1_002_001  # integer raster rounding
    pdf.close()


def test_encrypted_pdf_is_rejected_with_local_diagnostic(tmp_path):
    original = pdf_fixture(tmp_path / "plain.pdf")
    with pymupdf.open(original) as pdf:
        locked = tmp_path / "encrypted.pdf"
        pdf.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="fixture-owner", user_pw="fixture-reader")
    result = ingest.ingest_pdf(locked, document(), tmp_path / "private")
    assert result["processing_status"] == "rejected" and "Encrypted PDF" in result["errors"][0]


def test_running_product_header_scopes_specs_not_procedural_prose():
    data = page([line("GENERATING UNIT G1", y=10), line("G1A has been assigned to upgraded G1 units", y=40),
                 line("Rated generator output: 28-kw, 60-cycle, 125-v", y=80), line("If speed reaches 1200 rpm", y=110)])
    values = extract_assertions([data], document(["G1", "G1A"], category="generator"))
    assert {(item["model"], item["attribute"], item["value"]) for item in values} == {("G1", "output_power", 28000), ("G1", "frequency", 60), ("G1", "output_voltage", 125)}
    assert all(item["evidence"]["context"][0]["text"] == "GENERATING UNIT G1" for item in values)


def test_explicit_model_prose_preserves_component_and_role_and_wrapped_id():
    data = page([line("The generator is a Homelite model HR-28, 30-", y=10), line("volt, d-c type of 1500 watts rating.", y=24),
                 line("The gasoline engine is a Homelite model HR, 3400-3600 rpm.", y=60),
                 line("The heater-generator model HRH-", y=100), line("28 is designed for supplying 1500 watts, 30 volts, d-c power.", y=114)])
    values = extract_assertions([data], document(["HRH-28", "HR-28", "HR"], category="generator"))
    assert {(item["model"], item["attribute"], item["value"], item["value_max"], item["qualifier"]) for item in values} == {
        ("HR-28", "output_power", 1500, None, "rated"), ("HR-28", "output_voltage", 30, None, "rated"),
        ("HR", "speed", 3400, 3600, "unspecified"), ("HRH-28", "output_power", 1500, None, "unspecified"), ("HRH-28", "output_voltage", 30, None, "unspecified")}
    corrupted = page([line("The generator is a Homelite model HE-28, 30-volt, 1500 watts rating.")])
    assert extract_assertions([corrupted], document(["HR-28"], category="generator")) == []


def test_compact_improper_fraction_requires_source_resolution():
    doc = document(category="engine")
    ambiguous = extract_assertions([page([line("A gasoline engine of 11/2-horsepower")])], doc)
    assert ambiguous[0]["value"] == "11/2" and "unresolved compact fraction" in ambiguous[0]["conditions"][0]
    explicit = extract_assertions([page([line("A gasoline engine of 1½-horsepower")])], doc)
    assert explicit[0]["value"] == 1.5


def test_alternating_running_header_supports_only_adjacent_page_context():
    first = page([line("GENERATING UNIT G1", y=10)], number=5)
    second = page([line("INTRODUCTION", y=10), line("Rated generator output: 28 kW", y=50)], number=6)
    third = page([line("Weight: 12 kg", y=50)], number=7)
    values = extract_assertions([first, second, third], document(["G1", "G1A"], category="generator"))
    assert len(values) == 1 and values[0]["model"] == "G1" and values[0]["evidence"]["context"][0]["page"] == 5


def test_targeted_reocr_verifies_source_and_invalidates_record(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original = ingest.ingest_pdf(source, document(), tmp_path / "private")
    before = copy.deepcopy(original)
    def local_page(page, forced):
        assert forced is True
        return dict(original["pages"][0], engine="ocr-fixture")
    monkeypatch.setattr(ingest, "_read_page", local_page)
    updated = ingest.reocr_pages(source, original, [1], isolate_pages=False)
    assert original == before and updated["pages"][0]["engine"] == "ocr-fixture"
    assert updated["processing_version"] != original["processing_version"] and updated["page_refreshes"][0]["old_engine"] == "pymupdf-text"
    source.write_bytes(b"different source")
    with pytest.raises(ValueError, match="Source hash changed"):
        ingest.reocr_pages(source, original, [1])


def test_model_category_can_scope_explicit_model_prose_when_subject_wraps():
    data = page([line("Supplied is a model E2, 3400-3600 rpm.")])
    doc = document(["G1", "E2"], category="generator", model_categories={"G1": "generator", "E2": "engine"})
    values = extract_assertions([data], doc)
    assert len(values) == 1 and values[0]["model"] == "E2" and values[0]["attribute"] == "speed" and values[0]["value_max"] == 3600


def instrumented_worker(tmp_path, monkeypatch, page_body, setup=""):
    """Inject faults into a real child, never a timed-out thread in the parent."""
    events = tmp_path / "worker-events.jsonl"
    marker = tmp_path / "recover-now"
    script = tmp_path / "controlled-worker.py"
    script.write_text(
        "import sys, os, time, json, socket\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(Path(ingest.__file__).resolve().parent.parent)!r})\n"
        "from vopt import ingest, extraction_worker as worker\n"
        f"events = Path({str(events)!r})\nmarker = Path({str(marker)!r})\n"
        "original = ingest._read_page\n"
        "def observed(page, forced):\n"
        "    with events.open('a', encoding='utf-8') as stream:\n"
        "        stream.write(json.dumps({'page': page.number, 'pid': os.getpid()}) + '\\n')\n"
        + textwrap.indent(textwrap.dedent(page_body).strip(), "    ") + "\n"
        "ingest._read_page = observed\n" + textwrap.dedent(setup) + "\n"
        "worker.serve(sys.argv[1], sys.argv[2])\n", encoding="utf-8")
    monkeypatch.setattr(extraction_worker, "WORKER_SCRIPT", script)
    return events, marker


def test_native_process_timeout_crash_checkpoint_and_resume(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf", pages=4)
    events, marker = instrumented_worker(tmp_path, monkeypatch, """
        if not marker.exists() and page.number == 1:
            time.sleep(60)
        if not marker.exists() and page.number == 2:
            os._exit(77)
        return original(page, forced)
    """)
    processes = []
    real_popen = extraction_worker.subprocess.Popen
    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(extraction_worker.subprocess, "Popen", capture)
    start = time.monotonic()
    first = ingest.ingest_pdf(source, document(), tmp_path / "private", page_timeout_seconds=5)
    assert time.monotonic() - start < 25  # Hanging child sleeps 60s unless actually killed.
    assert [item["status"] for item in first["pages"]] == ["ok", "failed", "failed", "ok"]
    assert "PageTimeoutError" in first["pages"][1]["error"]
    assert "77" in first["pages"][2]["error"]
    assert first["coverage"]["successful_pages"] == 2 and first["processing_status"] == "partial"
    saved = json.loads(next((tmp_path / "private").rglob("record.json")).read_text(encoding="utf-8"))
    assert saved["pages"] == first["pages"]
    assert len(processes) == 3 and all(process.poll() is not None for process in processes)
    before = [json.loads(line) for line in events.read_text().splitlines()]
    assert [event["page"] for event in before] == [0, 1, 2, 3]
    # Child-reported os.getpid() must identify the supervised handles themselves,
    # not an unsupervised interpreter behind a Windows venv redirector.
    assert {event["pid"] for event in before} == {process.pid for process in processes}
    assert before[0]["pid"] == before[1]["pid"] and before[2]["pid"] != before[3]["pid"]
    marker.touch()
    resumed = ingest.ingest_pdf(source, document(), tmp_path / "private", page_timeout_seconds=5)
    assert resumed["processing_status"] == "complete" and resumed["cache_key"] == first["cache_key"]
    assert [item["attempts"] for item in resumed["pages"]] == [1, 2, 2, 1]
    after = [json.loads(line)["page"] for line in events.read_text().splitlines()]
    assert after == [0, 1, 2, 3, 1, 2]  # Successful checkpoint pages never rerun.
    assert all(process.poll() is not None for process in processes)


def test_native_open_timeout_is_rejected_and_child_reaped(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    script = tmp_path / "stuck-open.py"
    script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    monkeypatch.setattr(extraction_worker, "WORKER_SCRIPT", script)
    start = time.monotonic()
    result = ingest.ingest_pdf(source, document(), tmp_path / "private", page_timeout_seconds=.25)
    assert time.monotonic() - start < 4
    assert result["processing_status"] == "rejected" and result["pages"] == []
    assert "Native worker start exceeded" in result["errors"][0]


def test_native_partial_response_cannot_block_supervisor(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    instrumented_worker(tmp_path, monkeypatch, "return original(page, forced)", setup="""
        publish = worker._publish
        def incomplete(path, payload):
            if path.name.startswith('result-'):
                path.with_suffix('.tmp').write_text('{partial JSON', encoding='utf-8')
                time.sleep(60)
            publish(path, payload)
        worker._publish = incomplete
    """)
    with extraction_worker.PageProcess(source, 5) as reader:
        process = reader._process
        start = time.monotonic()
        with pytest.raises(extraction_worker.PageTimeoutError):
            reader.read_page(0, False)
        assert time.monotonic() - start < 8 and process.poll() is not None


def test_native_network_guard_and_bounded_output(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    instrumented_worker(tmp_path, monkeypatch, "socket.create_connection(('127.0.0.1', 9))")
    denied = ingest.ingest_pdf(source, document(), tmp_path / "guard")
    assert denied["pages"][0]["status"] == "failed"
    assert "forbids Python network" in denied["pages"][0]["error"]
    assert denied["pages"][0]["worker_network_attempts"] == 1
    instrumented_worker(tmp_path, monkeypatch, "return original(page, forced)", setup="worker.MAX_RESULT_BYTES = 128")
    oversized = ingest.ingest_pdf(source, document(), tmp_path / "output-limit")
    assert oversized["pages"][0]["status"] == "failed"
    assert "bounded IPC size" in oversized["pages"][0]["error"]


def test_native_worker_reuses_real_ocr_and_discards_noisy_output(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "two-scans.pdf", scanned=True, pages=2)
    events, marker = instrumented_worker(tmp_path, monkeypatch, """
        print('native-output' * 10000)
        print('native-error' * 10000, file=sys.stderr)
        result = original(page, forced)
        with marker.open('a', encoding='utf-8') as stream:
            stream.write(str(id(next(iter(ingest._OCR.values())))) + '\\n')
        return result
    """)
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["processing_status"] == "complete", result.get("errors", result["pages"])
    assert all(item["engine"] == "rapidocr-onnx" and item["worker_network_attempts"] == 0 for item in result["pages"])
    assert len(set(json.loads(line)["pid"] for line in events.read_text().splitlines())) == 1
    assert len(marker.read_text().splitlines()) == 2 and len(set(marker.read_text().splitlines())) == 1


def test_native_timeout_settings_bound_cache_identity(tmp_path):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    ordinary = ingest.ingest_pdf(source, document(), tmp_path / "private")
    longer = ingest.ingest_pdf(source, document(), tmp_path / "private", page_timeout_seconds=180)
    direct = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert len({item["cache_key"] for item in (ordinary, longer, direct)}) == 3
    assert ordinary["execution"]["mode"] == "subprocess" and direct["execution"]["page_timeout_seconds"] is None
    for invalid in (0, -1, float('inf'), float('nan'), True, 3601):
        with pytest.raises(ValueError, match="page_timeout_seconds"):
            ingest.ingest_pdf(source, document(), tmp_path / "private", page_timeout_seconds=invalid)


def test_source_change_rejects_cache_and_restored_bytes_reprocess(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original_bytes = source.read_bytes()
    changed = tmp_path / "changed.pdf"
    with pymupdf.open(source) as pdf:
        pdf[0].insert_text((40, 270), '99 horsepower changed-source sentinel')
        pdf.save(changed)
    changed_bytes = changed.read_bytes()
    original_open = ingest._open_pages
    def mutate_original(snapshot, *args):
        assert snapshot != source and snapshot.read_bytes() == original_bytes
        source.write_bytes(changed_bytes)
        return original_open(snapshot, *args)
    monkeypatch.setattr(ingest, "_open_pages", mutate_original)
    rejected = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert rejected["processing_status"] == "rejected" and rejected["assertions"] == []
    assert all(item["status"] == "failed" and not item["text"] for item in rejected["pages"])
    source.write_bytes(original_bytes)
    monkeypatch.setattr(ingest, "_open_pages", original_open)
    restored = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert restored["cache_key"] == rejected["cache_key"] and restored["processing_status"] == "complete"
    assert 'changed-source' not in restored["pages"][0]["text"] and restored["pages"][0]["attempts"] == 1


def test_verified_snapshot_protects_interrupted_checkpoint_from_source_mutation(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf", pages=2)
    original_bytes = source.read_bytes()
    original_read = ingest._read_page
    def mutate_and_interrupt(page, force):
        if page.number == 1:
            raise KeyboardInterrupt()
        source.write_bytes(b"source replaced while private snapshot is read")
        return original_read(page, force)
    monkeypatch.setattr(ingest, "_read_page", mutate_and_interrupt)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    saved = json.loads(next((tmp_path / "private").rglob("record.json")).read_text(encoding="utf-8"))
    assert saved["pages"][0]["status"] == "ok" and "230 V" in saved["pages"][0]["text"]
    source.write_bytes(original_bytes)
    reads = []
    monkeypatch.setattr(ingest, "_read_page", lambda page, force: (reads.append(page.number), original_read(page, force))[1])
    resumed = ingest.ingest_pdf(source, document(), tmp_path / "private", isolate_pages=False)
    assert resumed["processing_status"] == "complete" and reads == [1]
    assert all(item["attempts"] == 1 for item in resumed["pages"])


def test_source_snapshot_hash_mismatch_rejects_before_native_open(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original_hash = ingest._file_hash
    def change_after_hash(path):
        result = original_hash(path)
        if path == source:
            source.write_bytes(b"changed before snapshot copy")
        return result
    monkeypatch.setattr(ingest, "_file_hash", change_after_hash)
    monkeypatch.setattr(ingest, "_open_pages", lambda *args: pytest.fail("Unverified bytes cannot reach a native parser"))
    result = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert result["processing_status"] == "rejected" and "verified PDF snapshot" in result["errors"][0]


def test_transient_native_open_failure_preserves_successful_checkpoint(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    original = ingest.ingest_pdf(source, document(), tmp_path / "private")
    cache = next((tmp_path / "private").rglob("record.json"))
    before = cache.read_bytes()
    original_open = ingest._open_pages
    def fail_open(*args):
        raise extraction_worker.PageTimeoutError("controlled native open timeout")
    monkeypatch.setattr(ingest, "_open_pages", fail_open)
    rejected = ingest.ingest_pdf(source, document(), tmp_path / "private")
    assert rejected["processing_status"] == "rejected" and cache.read_bytes() == before
    monkeypatch.setattr(ingest, "_open_pages", original_open)
    monkeypatch.setattr(ingest.PageProcess, "read_page", lambda *args: pytest.fail("Successful checkpoint must survive failed open"))
    assert ingest.ingest_pdf(source, document(), tmp_path / "private") == original


def test_timeout_reaps_actual_native_pid_and_releases_pdf_lock(tmp_path, monkeypatch):
    source = pdf_fixture(tmp_path / "fixture.pdf")
    events, marker = instrumented_worker(tmp_path, monkeypatch, "time.sleep(60)\nreturn original(page, forced)")
    with extraction_worker.PageProcess(source, 2) as reader:
        native_pid = reader.native_pid
        assert native_pid == reader.pid
        process = reader._process
        handle = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x00100000, False, native_pid)  # SYNCHRONIZE
            assert handle
        try:
            with pytest.raises(extraction_worker.PageTimeoutError):
                reader.read_page(0, False)
            assert json.loads(events.read_text().splitlines()[0])["pid"] == native_pid
            assert process.poll() is not None
            if handle:
                assert kernel.WaitForSingleObject(handle, 0) == 0  # Actual native process signaled, not launcher.
            else:
                with pytest.raises(ProcessLookupError):
                    os.kill(native_pid, 0)
            source.unlink()  # Windows mapped PDF handle must already be released.
            assert not source.exists()
        finally:
            if handle:
                kernel.CloseHandle(handle)
