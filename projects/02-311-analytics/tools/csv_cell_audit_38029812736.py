"""Frozen, independent raw-to-CSV audit of one actual captured export cohort.

No application/evaluator/normalizer imports. This is a source-contract-aware
independent implementation, not a blinded human or independent GIS-library test.
Outputs only aggregate evidence; original source and exported bytes are read-only.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.metadata
import json
import math
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import shapely
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/real-capture-2025/april-october-2025.jsonl.gz"
BOUNDARIES = ROOT / "data/nta2020-26b.geojson"
RUNS = ROOT / "runs/agent-campaign-38029812736/corpus/real-v1/measurement-work/runs"
OUTPUT = ROOT / "examples/evidence/csv-cell-audit-38029812736.json"
RAW_SHA = "91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7"
GZIP_SHA = "a0a602baadb06df0ece450ab7b2398e52387bbc436c228ca7c653c497e7f0aba"
BOUNDARY_SHA = "5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e"
CSV_SHA = "edb145176437c7d5eeb59c99a90553af2631deaf19662e4f55ed32596b40284c"
EXPECTED_RAW_ROWS = 2_133_268
EXPECTED_RAW_BYTES = 1_306_911_416
EXPECTED_COHORT = 9_728
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_COHORT_ROWS = 20_000
MAX_SECONDS = 240
FIELDS = ("unique_key", "created_date", "complaint_type", "descriptor", "borough",
          "agency", "status", "nta2020", "closure_hours")
TEXT_FIELDS = ("complaint_type", "descriptor", "borough", "agency", "status")
NYC = ZoneInfo("America/New_York")
START = datetime(2025, 10, 1, 4, tzinfo=timezone.utc)
END = datetime(2025, 11, 1, 4, tzinfo=timezone.utc)
started_clock = time.monotonic()


def bounded():
    if time.monotonic() - started_clock > MAX_SECONDS:
        raise RuntimeError("Independent audit exceeded its fixed 240-second limit")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            bounded()
            digest.update(block)
    return digest.hexdigest()


def signature(path):
    info = path.stat()
    return (info.st_size, info.st_mtime_ns)


def keyword(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    text = str(value)
    return text.strip() if len(text.encode("utf-8")) <= 32_766 else ""


def instant(value):
    """Return UTC instant and an explicit reason, rejecting NYC folds/gaps."""
    if value is None or value == "":
        return None, "missing"
    if not isinstance(value, str) or not ("T" in value or " " in value):
        return None, "invalid"
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc), "aware"
        early = parsed.replace(tzinfo=NYC, fold=0).astimezone(timezone.utc)
        late = parsed.replace(tzinfo=NYC, fold=1).astimezone(timezone.utc)
        early_valid = early.astimezone(NYC).replace(tzinfo=None) == parsed
        late_valid = late.astimezone(NYC).replace(tzinfo=None) == parsed
        if early_valid and late_valid and early != late:
            return None, "ambiguous"
        if not early_valid and not late_valid:
            return None, "nonexistent"
        return early if early_valid else late, "local_unambiguous"
    except (ValueError, TypeError, OverflowError):
        return None, "invalid"


def csv_cell(value):
    if value is None:
        return ""
    text = str(value)
    if isinstance(value, str) and (
        text.lstrip().startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
    ):
        return "'" + text
    return text


def point_from_raw(row):
    lat, lon = row.get("latitude"), row.get("longitude")
    source = "latitude_longitude"
    if lat in (None, "") and lon in (None, ""):
        location = row.get("location")
        if isinstance(location, dict):
            coords = location.get("coordinates")
            if isinstance(coords, (list, tuple)) and len(coords) == 2:
                lon, lat = coords
                source = "location_coordinates"
            else:
                lat = location.get("lat", location.get("latitude"))
                lon = location.get("lon", location.get("longitude"))
                source = "location_latitude_longitude"
    if lat in (None, "") and lon in (None, ""):
        return None, "missing_geometry", source
    try:
        if isinstance(lat, bool) or isinstance(lon, bool):
            raise ValueError()
        y, x = float(lat), float(lon)
        if not math.isfinite(y) or not math.isfinite(x) or abs(y) > 90 or abs(x) > 180:
            raise ValueError()
        return Point(x, y), "valid", source
    except (ValueError, TypeError, OverflowError):
        return None, "invalid_geometry", source


def self_checks():
    checks = {
        "nyc_fall_fold_rejected": instant("2025-11-02T01:30:00")[1] == "ambiguous",
        "nyc_spring_gap_rejected": instant("2025-03-09T02:30:00")[1] == "nonexistent",
        "aware_fold_is_resolvable": instant("2025-11-02T01:30:00-04:00")[0]
        == datetime(2025, 11, 2, 5, 30, tzinfo=timezone.utc),
        "nyc_october_to_utc": instant("2025-10-01T00:00:00.000")[0] == START,
        "date_only_rejected": instant("2025-10-01")[1] == "invalid",
        "missing_date": instant(None) == (None, "missing"),
        "formula_escape": csv_cell("  =1+1") == "'  =1+1",
        "null_csv_empty": csv_cell(None) == "",
        "boolean_keyword_rejected": keyword(True) == "",
    }
    if not all(checks.values()):
        raise RuntimeError("Independent method self-check failed")
    return checks


def main():
    if OUTPUT.exists():
        raise FileExistsError("Audit output already exists; never overwrite prior evidence")
    csv_paths = sorted(RUNS.glob("*.csv"))
    if len(csv_paths) != 4:
        raise RuntimeError("Expected the four original completed/recovered export CSV files")
    files = [RAW, BOUNDARIES, *csv_paths]
    before = {path: signature(path) for path in files}
    checks = self_checks()
    input_hashes = {path: sha(path) for path in files}
    if input_hashes[RAW] != GZIP_SHA or input_hashes[BOUNDARIES] != BOUNDARY_SHA:
        raise RuntimeError("Original capture or official boundary hash mismatch")
    if any(input_hashes[path] != CSV_SHA for path in csv_paths):
        raise RuntimeError("Original retained CSV hash mismatch")

    document = json.loads(BOUNDARIES.read_bytes())
    features = document["features"]
    polygons = []
    residential_count = 0
    for feature in features:
        properties = feature["properties"]
        code = str(properties["nta2020"])
        geom = shape(feature["geometry"])
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise RuntimeError("Invalid official geometry")
        polygons.append((code, geom.bounds, geom))
        residential_count += str(properties["ntatype"]) == "0"
    if len(polygons) != 262 or len({item[0] for item in polygons}) != 262 or residential_count != 197:
        raise RuntimeError("Official boundary inventory mismatch")

    expected = {}
    raw_digest = hashlib.sha256()
    raw_rows = raw_bytes = 0
    previous = ""
    category_dates = Counter()
    created_states, closed_states, closure_states = Counter(), Counter(), Counter()
    geo_states, coordinate_sources, selected_nta = Counter(), Counter(), Counter()
    string_escapes = Counter()
    boundary_touches = 0
    raw_scan_started = time.monotonic()
    with gzip.open(RAW, "rb") as source:
        while line := source.readline(MAX_LINE_BYTES + 1):
            bounded()
            if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                raise RuntimeError("Source line exceeds bound or lacks canonical line ending")
            raw_digest.update(line)
            raw_bytes += len(line)
            raw_rows += 1
            if raw_rows > EXPECTED_RAW_ROWS or raw_bytes > EXPECTED_RAW_BYTES:
                raise RuntimeError("Source capture exceeds pinned count/byte bounds")
            row = json.loads(line)
            key = row["unique_key"]
            if isinstance(key, bool) or not isinstance(key, (str, int)):
                raise RuntimeError("Invalid raw record identifier")
            key = str(key).strip()
            if not key or key <= previous:
                raise RuntimeError("Raw identifiers not strictly ascending and unique")
            previous = key
            if keyword(row.get("borough")) != "BROOKLYN" or keyword(row.get("complaint_type")) != "Noise - Residential":
                continue
            created, created_state = instant(row.get("created_date"))
            category_dates[created_state] += 1
            if created is None or not START <= created < END:
                continue
            if len(expected) >= MAX_COHORT_ROWS:
                raise RuntimeError("Independent selected cohort exceeds memory bound")
            created_states[created_state] += 1
            closed, closed_state = instant(row.get("closed_date"))
            closed_states[closed_state] += 1
            status = keyword(row.get("status"))
            duration = None
            if closed is None:
                closure_states["closed_date_" + closed_state] += 1
            else:
                elapsed = (closed - created).total_seconds() / 3600.0
                if elapsed < 0:
                    closure_states["negative_elapsed"] += 1
                elif status.casefold() != "closed":
                    closure_states["status_not_closed"] += 1
                else:
                    duration = elapsed
                    closure_states["numeric_nonnegative_closed"] += 1

            point, geo_state, coordinate_source = point_from_raw(row)
            coordinate_sources[coordinate_source] += 1
            code = ""
            if point is not None:
                # Independent explicit bbox loop; no app/STRtree join helper.
                hits = []
                x, y = point.x, point.y
                for candidate, bbox, polygon in polygons:
                    if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3] and polygon.covers(point):
                        hits.append((candidate, polygon))
                if len(hits) == 1:
                    code = hits[0][0]
                    geo_state = "matched"
                    boundary_touches += not hits[0][1].contains(point)
                else:
                    geo_state = "unmatched" if not hits else "ambiguous"
            geo_states[geo_state] += 1
            selected_nta[code if code else "<empty>"] += 1
            values = {"unique_key": key, "created_date": created.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                      **{field: keyword(row.get(field)) for field in TEXT_FIELDS},
                      "nta2020": code, "closure_hours": duration}
            expected[key] = {field: csv_cell(values[field]) for field in FIELDS}
            for field in FIELDS:
                string_escapes[field] += isinstance(values[field], str) and expected[key][field] != values[field]
    raw_scan_seconds = time.monotonic() - raw_scan_started
    if raw_rows != EXPECTED_RAW_ROWS or raw_bytes != EXPECTED_RAW_BYTES or raw_digest.hexdigest() != RAW_SHA:
        raise RuntimeError("Whole decompressed capture does not match its published record/byte/hash receipt")
    if len(expected) != EXPECTED_COHORT:
        raise RuntimeError("Independent raw source cohort count differs from the 9728-row expected export")

    comparisons = []
    all_mismatches = Counter()
    for path in csv_paths:
        seen = set()
        mismatches = Counter()
        unknown_rows = duplicate_rows = cells = rows = 0
        numeric_max_abs = 0.0
        invalid_numeric_cells = 0
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != list(FIELDS):
                raise RuntimeError("CSV does not have exactly the nine declared columns in declared order")
            for actual in reader:
                bounded()
                if set(actual) != set(FIELDS) or any(value is None for value in actual.values()):
                    raise RuntimeError("CSV row does not contain exactly nine cells")
                rows += 1
                if rows > MAX_COHORT_ROWS:
                    raise RuntimeError("CSV rows exceed audit memory bound")
                key = actual["unique_key"]
                duplicate_rows += key in seen
                seen.add(key)
                reference = expected.get(key)
                if reference is None:
                    unknown_rows += 1
                    continue
                for field in FIELDS:
                    cells += 1
                    if actual[field] != reference[field]:
                        mismatches[field] += 1
                    if field == "closure_hours" and reference[field] and actual[field]:
                        try:
                            observed = float(actual[field])
                            if not math.isfinite(observed):
                                raise ValueError()
                            numeric_max_abs = max(numeric_max_abs, abs(observed - float(reference[field])))
                        except (ValueError, TypeError, OverflowError):
                            invalid_numeric_cells += 1
        missing_rows = len(set(expected) - seen)
        passed = rows == EXPECTED_COHORT and not (mismatches or unknown_rows or duplicate_rows or missing_rows)
        all_mismatches.update(mismatches)
        comparisons.append({"path": path.relative_to(ROOT).as_posix(), "bytes": before[path][0],
                            "sha256": input_hashes[path], "rows": rows, "cells_compared": cells,
                            "unknown_rows": unknown_rows, "duplicate_rows": duplicate_rows, "missing_rows": missing_rows,
                            "mismatches_by_column": dict(mismatches), "maximum_closure_numeric_absolute_error_hours": numeric_max_abs,
                            "invalid_numeric_cells": invalid_numeric_cells,
                            "passed": passed})
    unchanged = all(signature(path) == before[path] for path in files)
    passed = unchanged and all(item["passed"] for item in comparisons)
    receipt = {
        "schema_version": "1", "kind": "independent_raw_capture_csv_cell_audit", "passed": passed,
        "created_at": datetime.now(timezone.utc).isoformat(), "run_id": "38029812736",
        "source_head": "663a5b16fa8ddeec08970bc5cf71f0eb2e71582e",
        "method": {"script": Path(__file__).relative_to(ROOT).as_posix(), "script_sha256": sha(Path(__file__)),
                   "imports_application_modules": False,
                   "description": "Stream raw capture; select cohort without consulting exported IDs; independently derive text, UTC milliseconds, administrative closure and original official polygon covers; exact compare every cell of all four actual CSV files.",
                   "cohort": {"created_gte": START.isoformat(), "created_lt": END.isoformat(), "source_timezone": "America/New_York",
                              "borough": "BROOKLYN", "complaint_type": "Noise - Residential", "nta_filter": None},
                   "columns": list(FIELDS), "comparison": "exact decoded CSV cell strings; no numeric tolerance; UTF-8 BOM decoded; CSV formula escaping independently applied",
                   "maximum_raw_line_bytes": MAX_LINE_BYTES, "maximum_stored_cohort_rows": MAX_COHORT_ROWS,
                   "maximum_seconds": MAX_SECONDS, "self_checks": checks,
                   "python": platform.python_version(), "implementation": platform.python_implementation(),
                   "shapely": shapely.__version__, "geos": shapely.geos_version_string,
                   "tzdata": importlib.metadata.version("tzdata")},
        "capture": {"path": RAW.relative_to(ROOT).as_posix(), "compressed_bytes": before[RAW][0], "compressed_sha256": input_hashes[RAW],
                    "raw_bytes": raw_bytes, "raw_sha256": raw_digest.hexdigest(), "raw_records": raw_rows,
                    "strict_ascending_unique_identifiers": True, "scan_seconds": raw_scan_seconds},
        "boundaries": {"path": BOUNDARIES.relative_to(ROOT).as_posix(), "bytes": before[BOUNDARIES][0], "sha256": input_hashes[BOUNDARIES],
                       "features": len(polygons), "residential_features": residential_count, "all_features_valid_nonempty": True,
                       "all_262_used_for_point_assignment": True, "predicate": "original polygon.covers(original source point), including boundary; reject multiple hits"},
        "cohort": {"rows": len(expected), "unique_logical_cells": len(expected) * len(FIELDS),
                   "category_created_date_states_all_capture_periods": dict(category_dates),
                   "created_date_states": dict(created_states), "closed_date_states": dict(closed_states),
                   "closure_states": dict(closure_states), "coordinate_sources": dict(coordinate_sources),
                   "geometry_states": dict(geo_states), "distinct_nonempty_nta_codes": len(set(selected_nta) - {"<empty>"}),
                   "assigned_points_exactly_on_polygon_boundary": boundary_touches,
                   "escaped_formula_cells_by_column": dict(string_escapes)},
        "csv_files": comparisons, "csv_file_count": len(comparisons),
        "total_cells_compared": sum(item["cells_compared"] for item in comparisons),
        "mismatches_by_column": dict(all_mismatches), "inputs_unchanged_by_size_mtime_ns": unchanged,
        "elapsed_seconds": time.monotonic() - started_clock,
        "limitations": [
            "Only this 9728-row October Brooklyn Noise - Residential cohort and four retained CSVs receive cell-level qualification; other exports and the remaining captured records do not.",
            "Source contract/source implementation were read before constructing this independent code. No analytics311, query compiler, normalizer, exporter or agent oracle module is imported; not a blinded audit.",
            "Point-in-polygon implementation is separate but shares Shapely/GEOS and Python timezone data with the product. This is not an independent GIS-library or human boundary-ground-truth validation.",
            "Closure is elapsed time to administrative closed_date when status is Closed, observed at capture; not first response and not historical closure status at the analysis as_of.",
            "Any absent DST, invalid-date, negative-duration, formula or boundary-edge examples remain unqualified by this actual cohort; self-checks are method checks, not observed real-data cases.",
            "All four CSV files have identical bytes. This checks four actual export/recovery artifacts but does not imply four independent data samples or broader load qualification.",
        ],
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(receipt, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(), "passed": passed, "raw_rows": raw_rows,
                      "cohort_rows": len(expected), "csv_files": len(comparisons), "cells": receipt["total_cells_compared"],
                      "mismatches": dict(all_mismatches), "cohort": receipt["cohort"],
                      "elapsed_seconds": receipt["elapsed_seconds"]}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
