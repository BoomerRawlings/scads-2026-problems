"""Freeze independent real-corpus answers, then execute 40 x 3 real agent trials.

The SQLite oracle deliberately does not import the application's validator,
compiler, fixture executor or aggregation helpers. It evaluates the normalized
corpus; normalization, source completeness and NTA assignment need separate
qualification. Automatic checks never certify free-text interpretation or map
rendering. All failures remain in the denominator.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import statistics
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from tools.local_agent import (AgentFailure, LocalModel, canonical, endpoint_parts, metadata_prefix_request, prefix_warmup_policy,
                               run_trial, warm_metadata_prefix)


QUESTIONS = ROOT / "examples/evaluation/questions-v1.json"
NTA_RECEIPT = ROOT / "examples/evidence/official-nta2020-26b.json"
RUNTIME_SPEC = ROOT / "docs/local-model-runtime.json"
RUNTIME_RECEIPT = ROOT / "runs/runtime/agent-runtime-freeze.json"
TEXT_FIELDS = ("unique_key", "complaint_type", "descriptor", "agency", "agency_name", "status", "borough",
               "incident_zip", "nta2020", "ntaname", "community_board", "council_district", "police_precinct")
NUM_FIELDS = ("created_date", "closed_date", "closure_hours", "is_closed", "latitude", "longitude")
FIELDS = TEXT_FIELDS + NUM_FIELDS
NY = ZoneInfo("America/New_York")


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def epoch(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("oracle_dates_require_offsets")
    return parsed.timestamp()


def bucket(value, interval):
    if value is None:
        return None
    current = datetime.fromtimestamp(value, NY).replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "week":
        current -= timedelta(days=current.weekday())
    elif interval == "month":
        current = current.replace(day=1)
    elif interval != "day":
        raise ValueError("oracle_interval")
    return current.isoformat()


def distance(lat, lon, a, b):
    if lat is None or lon is None:
        return None
    x, y = math.radians(lat), math.radians(a)
    dl = math.radians(lon - b)
    # Independent central-angle form, same explicitly documented mean Earth radius.
    numerator = math.hypot(math.cos(x) * math.sin(dl),
                           math.cos(y) * math.sin(x) - math.sin(y) * math.cos(x) * math.cos(dl))
    denominator = math.sin(y) * math.sin(x) + math.cos(y) * math.cos(x) * math.cos(dl)
    return 6371008.7714 * math.atan2(numerator, denominator)


def inside(lat, lon, encoded):
    if lat is None or lon is None:
        return 0
    points = json.loads(encoded)
    winding = 0
    for a, b in zip(points, points[1:] + points[:1]):
        cross = (b["lon"] - a["lon"]) * (lat - a["lat"]) - (lon - a["lon"]) * (b["lat"] - a["lat"])
        if abs(cross) <= 1e-10 and min(a["lon"], b["lon"]) <= lon <= max(a["lon"], b["lon"]) and min(a["lat"], b["lat"]) <= lat <= max(a["lat"], b["lat"]):
            return 1
        if a["lat"] <= lat < b["lat"] and cross > 0:
            winding += 1
        elif b["lat"] <= lat < a["lat"] and cross < 0:
            winding -= 1
    return int(winding != 0)


def connect(path, *, readonly=True):
    path = Path(path).resolve()
    connection = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else ""), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA cache_size=-32768")
    connection.execute("PRAGMA temp_store=FILE")
    connection.create_function("ny_bucket", 2, bucket, deterministic=True)
    connection.create_function("distance_m", 4, distance, deterministic=True)
    connection.create_function("inside_polygon", 3, inside, deterministic=True)
    return connection


def build_database(source, database, *, min_free_bytes=256 * 1024 * 1024):
    """One disk-backed normalized corpus projection; exact primary-key uniqueness."""
    source, database = Path(source), Path(database)
    if database.exists():
        raise ValueError("oracle_database_exists")
    database.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(database.parent).free < min_free_bytes:
        raise ValueError("oracle_disk_budget")
    before = source.stat()
    db = connect(database, readonly=False)
    count, fingerprint = 0, hashlib.sha256()
    try:
        db.execute("CREATE TABLE requests (" + ",".join(
            f'"{field}" ' + ("TEXT PRIMARY KEY NOT NULL" if field == "unique_key" else "TEXT" if field in TEXT_FIELDS else "REAL")
            for field in FIELDS) + ") WITHOUT ROWID")
        insert = "INSERT INTO requests VALUES (" + ",".join("?" for _ in FIELDS) + ")"
        with source.open("rb") as stream:
            while True:
                line = stream.readline(10 * 1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 10 * 1024 * 1024:
                    raise ValueError("oracle_line_budget")
                fingerprint.update(line)
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get("unique_key"), str) or not row["unique_key"]:
                    raise ValueError("oracle_missing_unique_key")
                values = dict(row)
                for field in ("created_date", "closed_date"):
                    values[field] = epoch(row[field]) if row.get(field) else None
                values["is_closed"] = int(row["is_closed"]) if type(row.get("is_closed")) is bool else None
                point = row.get("location") or {}
                values.update(latitude=point.get("lat"), longitude=point.get("lon"))
                db.execute(insert, [values.get(field) for field in FIELDS])
                count += 1
                if count % 10000 == 0:
                    db.commit()
                    if shutil.disk_usage(database.parent).free < min_free_bytes:
                        raise ValueError("oracle_disk_budget")
        db.commit()
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("oracle_source_changed")
        db.execute("CREATE INDEX creation ON requests(created_date)")
        db.execute("CREATE INDEX complaint_creation ON requests(complaint_type,created_date)")
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        metadata = {"source_sha256": fingerprint.hexdigest(), "rows": count, "source_bytes": after.st_size}
        db.executemany("INSERT INTO metadata VALUES (?,?)", [(key, canonical(value)) for key, value in metadata.items()])
        db.commit()
    finally:
        db.close()
    return metadata


class Oracle:
    def __init__(self, database, catalog, residential_codes):
        self.db = connect(database)
        self.catalog, self.residential_codes, self.cache = catalog, residential_codes, {}

    def close(self):
        self.db.close()

    def expand(self, spec):
        def visit(node):
            if isinstance(node, list):
                return [visit(item) for item in node]
            if not isinstance(node, dict):
                return node
            if node.get("residential_nta") is True:
                return {"field": "nta2020", "op": "in", "value": self.residential_codes}
            if "category_family" in node:
                return {"field": "complaint_type", "op": "in", "value": self.catalog["families"][node["category_family"]]}
            return {key: visit(value) for key, value in node.items()}
        return visit(copy.deepcopy(spec))

    def where(self, spec):
        spec = self.expand(spec)
        args = []

        def bound(value, field=None):
            args.append(epoch(value) if field in {"created_date", "closed_date"} else value)
            return "?"

        def predicate(node):
            if not node:
                return "1"
            for op, join in (("all", " AND "), ("any", " OR ")):
                if op in node:
                    return "(" + join.join(predicate(child) for child in node[op]) + ")"
            if "not" in node:
                return "NOT (" + predicate(node["not"]) + ")"
            field, op, value = node["field"], node["op"], node["value"]
            if field == "location" and op == "exists":
                return "(latitude IS NOT NULL AND longitude IS NOT NULL)" if value else "(latitude IS NULL OR longitude IS NULL)"
            if field not in FIELDS:
                raise ValueError("oracle_unknown_field")
            quoted = '"' + field + '"'
            if op == "exists":
                return quoted + (" IS NOT NULL" if value else " IS NULL")
            if op == "eq":
                sql = quoted + "=" + bound(value, field)
            elif op == "in":
                sql = quoted + " IN (" + ",".join(bound(item, field) for item in value) + ")"
            elif op == "range":
                operators = {"gte": ">=", "gt": ">", "lt": "<", "lte": "<="}
                sql = " AND ".join(quoted + operators[key] + bound(item, field) for key, item in value.items())
            else:
                raise ValueError("oracle_unknown_operator")
            return "COALESCE((" + sql + "),0)"

        clauses = [predicate(spec.get("filters"))]
        spans = list(spec["periods"].values()) if "periods" in spec else [spec["time"]] if "time" in spec else []
        if spans:
            temporal = []
            for span in spans:
                field = span.get("field", "created_date")
                if field not in {"created_date", "closed_date"}:
                    raise ValueError("oracle_time_field")
                temporal.append(f'("{field}">={bound(span["gte"], field)} AND "{field}"<{bound(span["lt"], field)})')
            clauses.append("(" + " OR ".join(temporal) + ")")
        geometry = spec.get("geo")
        if geometry:
            if geometry["type"] == "radius":
                clauses.append("distance_m(latitude,longitude,?,?)<=?")
                args.extend((geometry["lat"], geometry["lon"], geometry["distance_m"]))
            elif geometry["type"] == "bbox":
                top, bottom = geometry["top_left"], geometry["bottom_right"]
                clauses.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
                args.extend((bottom["lat"], top["lat"], top["lon"], bottom["lon"]))
            elif geometry["type"] == "polygon":
                clauses.append("inside_polygon(latitude,longitude,?)=1")
                args.append(canonical(geometry["points"]))
            else:
                raise ValueError("oracle_geometry")
        return " AND ".join("(" + clause + ")" for clause in clauses), args

    def membership(self, spec):
        where, args = self.where(spec)
        count, located, hashed = 0, 0, hashlib.sha256()
        for row in self.db.execute("SELECT unique_key,latitude,longitude FROM requests WHERE " + where + " ORDER BY unique_key COLLATE BINARY", args):
            count += 1
            located += int(row["latitude"] is not None and row["longitude"] is not None)
            hashed.update(canonical(row["unique_key"]).encode() + b"\n")
        return {"count": count, "ids_sha256": hashed.hexdigest(), "geolocated_count": located}

    def preview_ids(self, spec):
        where, args = self.where(spec)
        limit = spec.get("preview_limit", 100)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("oracle_preview_budget")
        rows = self.db.execute("SELECT unique_key FROM requests WHERE " + where
                               + " ORDER BY created_date IS NULL,created_date,unique_key COLLATE BINARY LIMIT ?", args + [limit])
        return [row[0] for row in rows]

    def aggregate(self, spec):
        where, args = self.where(spec)
        groups = spec.get("group_by", [])
        expressions = []
        for dim in groups:
            field = dim["field"]
            if field not in FIELDS:
                raise ValueError("oracle_group_field")
            if "interval" in dim:
                if field not in {"created_date", "closed_date"} or dim["interval"] not in {"day", "week", "month"}:
                    raise ValueError("oracle_group_interval")
                expressions.append(f"ny_bucket(\"{field}\",'{dim['interval']}')")
            else:
                expressions.append('"' + field + '"')
        fields = [f"{expression} AS g{index}" for index, expression in enumerate(expressions)]
        fields += ["count(*) AS count", "coalesce(sum(is_closed=1),0) AS closed_count",
                   "coalesce(sum(is_closed=0),0) AS open_count",
                   "avg(CASE WHEN is_closed=1 AND closure_hours>=0 THEN closure_hours END) AS mean_closure_hours"]
        sql = "SELECT " + ",".join(fields) + " FROM requests WHERE " + where
        if expressions:
            sql += " GROUP BY " + ",".join(expressions)
        rows = []
        for found in self.db.execute(sql, args):
            if len(rows) >= 50000:
                raise ValueError("oracle_group_budget")
            group = {dim["field"]: found[f"g{index}"] for index, dim in enumerate(groups)}
            row = {"group": group, "count": found["count"]}
            for metric in spec.get("metrics", ["count"]):
                if metric in {"median_closure_hours", "p90_closure_hours"}:
                    terms, parameters = [where, "is_closed=1", "closure_hours>=0"], list(args)
                    for index, value in enumerate(group.values()):
                        terms.append(expressions[index] + " IS ?")
                        parameters.append(value)
                    chosen = " AND ".join("(" + term + ")" for term in terms)
                    number = self.db.execute("SELECT count(*) FROM requests WHERE " + chosen, parameters).fetchone()[0]
                    if not number:
                        row[metric] = None
                    else:
                        position = (number - 1) * (0.5 if metric == "median_closure_hours" else 0.9)
                        lo, hi = math.floor(position), math.ceil(position)
                        values = [item[0] for item in self.db.execute("SELECT closure_hours FROM requests WHERE " + chosen + " ORDER BY closure_hours LIMIT ? OFFSET ?", parameters + [hi - lo + 1, lo])]
                        row[metric] = values[0] + (values[-1] - values[0]) * (position - lo)
                elif metric in {"count", "closed_count", "open_count", "mean_closure_hours"}:
                    row[metric] = found[metric]
                else:
                    raise ValueError("oracle_metric")
            rows.append(row)
        date_dim = next((dim for dim in groups if "interval" in dim), None)
        if date_dim:
            field, interval = date_dim["field"], date_dim["interval"]
            others = [dim["field"] for dim in groups if dim is not date_dim]
            combos = {tuple(row["group"][key] for key in others) for row in rows} if others else {()}
            lookup = {(tuple(row["group"][key] for key in others), row["group"][field]): row for row in rows}
            current = datetime.fromisoformat(bucket(epoch(spec["time"]["gte"]), interval))
            current = current.astimezone(NY)
            dense = []
            while current.timestamp() < epoch(spec["time"]["lt"]):
                for combo in combos:
                    row = lookup.get((combo, current.isoformat()))
                    if row is None:
                        row = {"group": {**dict(zip(others, combo)), field: current.isoformat()}, "count": 0}
                        row.update({metric: 0 if metric in {"count", "closed_count", "open_count"} else None for metric in spec.get("metrics", [])})
                    dense.append(row)
                if interval == "month":
                    current = current.replace(year=current.year + (current.month == 12), month=current.month % 12 + 1, day=1)
                else:
                    current += timedelta(days=7 if interval == "week" else 1)
                if len(dense) > 50000:
                    raise ValueError("oracle_group_budget")
            rows = dense
        return rows

    def evaluate(self, spec):
        spec = self.expand(spec)
        key = digest(spec)
        if key in self.cache:
            return copy.deepcopy(self.cache[key])
        result = {"membership": self.membership(spec), "rows": []}
        if spec["operation"] == "compare_periods":
            periods, counts, days = {}, {}, {}
            for name in ("baseline", "current"):
                child = copy.deepcopy(spec)
                child.update(operation="aggregate", time={"field": "created_date", **child.pop("periods")[name]})
                periods[name] = {canonical(row["group"]): row for row in self.aggregate(child)}
                counts[name] = self.membership(child)
                a, b = [datetime.fromtimestamp(epoch(spec["periods"][name][key]), NY).replace(tzinfo=None) for key in ("gte", "lt")]
                days[name] = (b - a).total_seconds() / 86400
            result["period_membership"] = counts
            for group in sorted(set(periods["baseline"]) | set(periods["current"])):
                empty = {metric: 0 if metric in {"count", "closed_count", "open_count"} else None for metric in spec.get("metrics", ["count"])}
                empty["count"] = 0
                base = {key: value for key, value in periods["baseline"].get(group, empty).items() if key != "group"}
                now = {key: value for key, value in periods["current"].get(group, empty).items() if key != "group"}
                bv, cv = base["count"], now["count"]
                result["rows"].append({"group": json.loads(group), "count": cv, "baseline_count": bv, "current_count": cv,
                                       "baseline_days": days["baseline"], "current_days": days["current"],
                                       "baseline_daily_rate": bv / days["baseline"], "current_daily_rate": cv / days["current"],
                                       "absolute_change": cv - bv, "relative_change": (cv - bv) / bv if bv else None,
                                       "rate_change": cv / days["current"] - bv / days["baseline"],
                                       "baseline_metrics": base, "current_metrics": now})
        elif spec["operation"] == "aggregate":
            result["rows"] = self.aggregate(spec)
        elif spec["operation"] != "records":
            raise ValueError("oracle_operation")
        else:
            result["preview_ids"] = self.preview_ids(spec)
        minimum = spec.get("minimum_count", 0)
        result["rows"] = [row for row in result["rows"] if row["count"] + row.get("baseline_count", 0) >= minimum]
        rank = spec.get("rank_by", "absolute_change" if spec["operation"] == "compare_periods" else "count")
        ordered = sorted(result["rows"], key=lambda row: canonical(row["group"]))
        finite = [row for row in ordered if row.get(rank) is not None]
        finite.sort(key=lambda row: row[rank], reverse=spec.get("rank_order", "desc") == "desc")
        result["rows"] = finite + [row for row in ordered if row.get(rank) is None]
        self.cache[key] = copy.deepcopy(result)
        return result


def numeric_equal(actual, expected, key=""):
    if type(expected) in (float, int) and type(actual) in (float, int):
        if type(expected) is int and key not in {"mean_closure_hours", "median_closure_hours", "p90_closure_hours"}:
            return actual == expected
        tolerance = max(0.1, abs(expected) * 0.05) if key in {"median_closure_hours", "p90_closure_hours"} else max(1e-8, abs(expected) * 1e-7)
        return math.isfinite(actual) and abs(actual - expected) <= tolerance
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and numeric_equal(actual[key], value, key) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(numeric_equal(a, b, key) for a, b in zip(actual, expected))
    return actual == expected and type(actual) is type(expected)


def code_hashes():
    paths = sorted((ROOT / "analytics311").glob("*.py")) + [ROOT / "tools/agent_evaluation.py", ROOT / "tools/local_agent.py"]
    return {path.relative_to(ROOT).as_posix(): sha_file(path) for path in paths}


def runtime_definition(path, model):
    raw = Path(path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("runtime_definition_budget")
    definition = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(definition, dict) or not isinstance(definition.get("model"), dict):
        raise ValueError("invalid_runtime_definition")
    execution = definition.get("execution_runtime", {})
    if (not isinstance(execution, dict) or definition.get("model_alias") != model
            or not re.fullmatch(r"[0-9a-f]{64}", str(definition["model"].get("sha256", "")))
            or execution.get("kind") != "native_source_build"
            or not re.fullmatch(r"[0-9a-f]{40}", str(execution.get("source_commit", "")))
            or not isinstance(execution.get("cmake_flags"), list) or not execution["cmake_flags"]
            or not all(isinstance(flag, str) and flag.startswith("-D") for flag in execution["cmake_flags"])):
        raise ValueError("invalid_runtime_definition")
    try:
        prefix_warmup_policy(definition)
    except AgentFailure as exc:
        raise ValueError(exc.code) from None
    return {"sha256": hashlib.sha256(raw).hexdigest(), "definition": definition}


def check_owned_runtime_process(receipt, artifact_paths, library_paths, *, proc_root=Path("/proc")):
    """Linux execution receipt: bind the live PID, argv, executable and mapped SOs."""
    if sys.platform != "linux":
        raise ValueError("runtime_process_verification_requires_linux")
    process = proc_root / str(receipt["owned_server_pid"])
    argv = [os.fsdecode(part) for part in (process / "cmdline").read_bytes().split(b"\0") if part]
    if (argv != receipt["launch_argv"] or (process / "exe").resolve(strict=True) != artifact_paths["server"]):
        raise ValueError("runtime_process_changed")
    mapped = set()
    for line in (process / "maps").read_text().splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) == 6 and parts[5].startswith("/") and re.search(r"\.so(?:\.|$)", Path(parts[5]).name):
            mapped.add(Path(parts[5]).resolve(strict=True))
    if mapped != library_paths:
        raise ValueError("runtime_library_inventory_mismatch")


def verify_runtime_receipt(path, frozen, freeze_hash, *, endpoint, seconds, request_seconds):
    raw = Path(path).read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("runtime_receipt_budget")
    receipt = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(receipt, dict):
        raise ValueError("runtime_receipt_mismatch")
    spec = frozen["runtime_spec"]
    definition = spec["definition"]
    if (receipt.get("schema_version") != 1 or receipt.get("evidence_kind") != "pretrial_local_model_runtime"
            or receipt.get("freeze_sha256") != freeze_hash
            or receipt.get("runtime_spec_sha256") != spec["sha256"]
            or receipt.get("model_alias") != frozen["model"]
            or receipt.get("execution_runtime") != definition["execution_runtime"]
            or endpoint_parts(receipt.get("endpoint", "")) != endpoint_parts(endpoint)
            or receipt.get("budgets") != {"seconds": seconds, "request_seconds": request_seconds, "max_calls": 24}
            or type(receipt.get("owned_server_pid")) is not int or receipt["owned_server_pid"] <= 0
            or not isinstance(receipt.get("launch_argv"), list) or not receipt["launch_argv"]
            or not all(isinstance(arg, str) for arg in receipt["launch_argv"])):
        raise ValueError("runtime_receipt_mismatch")
    files = receipt.get("files")
    if (not isinstance(files, list) or not 3 <= len(files) <= 128
            or any(not isinstance(item, dict) for item in files)):
        raise ValueError("runtime_files_required")
    roles = [item.get("role") for item in files]
    if roles.count("model") != 1 or roles.count("server") != 1 or "build_configuration" not in roles:
        raise ValueError("runtime_files_required")
    paths, artifact_paths, library_paths = set(), {}, set()
    for item in files:
        file = Path(item.get("path", ""))
        if not file.is_absolute():
            file = Path(path).resolve().parent / file
        file = file.resolve(strict=True)
        if (file in paths or not file.is_file() or type(item.get("bytes")) is not int
                or file.stat().st_size != item["bytes"] or sha_file(file) != item.get("sha256")):
            raise ValueError("runtime_file_changed")
        paths.add(file)
        artifact_paths[item["role"]] = file
        if item["role"] == "runtime_library":
            library_paths.add(file)
        if item["role"] == "model" and (item.get("sha256") != definition["model"]["sha256"]
                                         or item.get("bytes") != definition["model"].get("size")):
            raise ValueError("runtime_model_changed")
    argv = receipt["launch_argv"]
    try:
        model_flag = "-m" if "-m" in argv else "--model"
        model_index = argv.index(model_flag) + 1
        if (Path(argv[0]).resolve() != artifact_paths["server"]
                or argv.count("-m") + argv.count("--model") != 1
                or Path(argv[model_index]).resolve() != artifact_paths["model"]):
            raise ValueError()
        inference = definition["inference"]
        host, port, _ = endpoint_parts(endpoint)
        expected_flags = {"--alias": frozen["model"], "--host": inference["bind"], "--port": inference["port"],
                          "--threads": inference["threads"], "--ctx-size": inference["context_tokens"],
                          "--parallel": inference["parallel_slots"], "--gpu-layers": inference["gpu_layers"]}
        if host != inference["bind"] or port != inference["port"]:
            raise ValueError()
        for flag, expected in expected_flags.items():
            if argv.count(flag) != 1 or argv[argv.index(flag) + 1] != str(expected):
                raise ValueError()
        if inference.get("context_shift") is False and (argv.count("--no-context-shift") != 1 or "--context-shift" in argv):
            raise ValueError()
    except (IndexError, ValueError):
        raise ValueError("runtime_launch_mismatch") from None
    check_owned_runtime_process(receipt, artifact_paths, library_paths)
    launch = list(argv)
    launch[0], launch[model_index] = "<server>", "<model>"
    identity = {"runtime_spec_sha256": spec["sha256"], "execution_runtime": definition["execution_runtime"],
                "model_alias": frozen["model"], "endpoint": [host, port, "/v1"],
                "budgets": receipt["budgets"], "launch_arguments": launch,
                "files": sorted(({key: item[key] for key in ("role", "bytes", "sha256")} for item in files), key=canonical)}
    return {"sha256": hashlib.sha256(raw).hexdigest(), "receipt": receipt,
            "receipt_json": raw.decode("utf-8"), "identity": identity}


def check_archived_runtime_launch(directory, receipt_hash, identity):
    if not isinstance(receipt_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_hash):
        raise ValueError("runtime_launch_receipt_missing")
    launch = load(Path(directory) / ("runtime-launch-" + receipt_hash + ".json"))
    text = launch.get("receipt_json")
    if (not isinstance(text, str) or hashlib.sha256(text.encode("utf-8")).hexdigest() != receipt_hash
            or launch.get("sha256") != receipt_hash or json.loads(text.lstrip("\ufeff")) != launch.get("receipt")
            or launch.get("identity") != identity):
        raise ValueError("runtime_launch_receipt_changed")


def check_archived_prefix_warmup(directory, warm_hash, launch_hash, frozen, execution_hash):
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (warm_hash, launch_hash)):
        raise ValueError("prefix_warmup_receipt_missing")
    path = Path(directory) / ("metadata-prefix-warmup-" + launch_hash + ".json")
    receipt = load(path)
    policy = prefix_warmup_policy(frozen["runtime_spec"]["definition"])
    usage = receipt.get("usage", {})
    if (sha_file(path) != warm_hash or receipt.get("passed") is not True
            or receipt.get("schema_version") != 1
            or receipt.get("evidence_kind") != "metadata_only_model_prefix_warmup"
            or receipt.get("runtime_receipt_sha256") != launch_hash
            or receipt.get("runtime_spec_sha256") != frozen["runtime_spec"]["sha256"]
            or receipt.get("execution_sha256") != execution_hash or receipt.get("model_alias") != frozen["model"]
            or receipt.get("question_supplied") is not False or receipt.get("analytical_tool_calls") != 0
            or receipt.get("generated_content_retained") is not False or not policy
            or not isinstance(usage, dict) or set(usage) != {"prompt_tokens", "completion_tokens", "total_tokens"}
            or any(type(value) is not int for value in usage.values())
            or usage.get("prompt_tokens", 0) <= 0 or usage.get("completion_tokens") not in (0, 1)
            or usage.get("total_tokens") != usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
            or any(not isinstance(receipt.get(key + "_sha256"), str)
                   or not re.fullmatch(r"[0-9a-f]{64}", receipt[key + "_sha256"])
                   or type(receipt.get(key + "_utf8_bytes")) is not int or receipt[key + "_utf8_bytes"] <= 0
                   for key in ("request", "prefix", "original_descriptor", "projected_descriptor"))
            or any(type(receipt.get(key)) is not type(value) or receipt.get(key) != value for key, value in policy.items())
            or type(receipt.get("elapsed_seconds")) not in (int, float)
            or not 0 <= receipt["elapsed_seconds"] <= policy["request_seconds"]):
        raise ValueError("prefix_warmup_receipt_changed")
    expected = frozen.get("prefix_warmup_request")
    identity_keys = {"context_projection"} | {name + suffix for name in
                    ("request", "prefix", "original_descriptor", "projected_descriptor") for suffix in ("_sha256", "_utf8_bytes")}
    if (not isinstance(expected, dict) or set(expected) != identity_keys
            or any(type(receipt.get(key)) is not type(value) or receipt.get(key) != value for key, value in expected.items())):
        raise ValueError("prefix_warmup_input_identity_mismatch")
    return receipt


def prefix_warmup_summary(directories):
    receipts = {}
    for directory in directories:
        for path in sorted(Path(directory).glob("metadata-prefix-warmup-*.json")):
            value = load(path)
            receipt_hash = sha_file(path)
            receipts[receipt_hash] = {"sha256": receipt_hash, "file": path.name,
                                     "passed": value.get("passed") is True,
                                     "runtime_receipt_sha256": value.get("runtime_receipt_sha256"),
                                     "elapsed_seconds": value["elapsed_seconds"]}
    return {"performed": bool(receipts), "receipt_count": len(receipts), "receipts": list(receipts.values()),
            "startup_seconds_total": sum(item["elapsed_seconds"] for item in receipts.values()),
            "excluded_from_trial_latency": True,
            "limitation": "Metadata-only startup is reported separately; completion does not itself prove cache reuse or cold-request latency."}


def runtime_memory_snapshot(pid, *, proc_root=Path("/proc")):
    """Bounded numeric kernel counters; VmHWM is process-lifetime, never trial peak."""
    result = {"source": "linux_proc_status", "available": False,
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "scope": "RSS at observation; HWM since this owned process started, not a trial-specific peak."}
    if sys.platform != "linux" or type(pid) is not int or pid <= 0:
        result["reason"] = "unsupported_platform_or_pid"
        return result
    try:
        with (proc_root / str(pid) / "status").open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError()
        text = raw.decode("ascii")
        values = {}
        for name, target in (("VmRSS", "rss_bytes"), ("VmHWM", "process_lifetime_hwm_bytes")):
            match = re.search(r"^" + name + r":\s*(\d+)\s+kB\s*$", text, re.MULTILINE)
            if not match:
                raise ValueError()
            values[target] = int(match.group(1)) * 1024
        result.update(available=True, **values)
    except (OSError, UnicodeError, ValueError):
        result["reason"] = "status_unavailable_or_invalid"
    return result


def prepare(config, source, database, output, *, model, questions=QUESTIONS, nta_receipt=NTA_RECEIPT,
            development=False, runtime_spec=RUNTIME_SPEC):
    from analytics311.service import AnalyticsService
    service = AnalyticsService(config)
    protocol, nta = load(questions), load(nta_receipt)
    if len(protocol["questions"]) != 40 or len({case["id"] for case in protocol["questions"]}) != 40 or protocol.get("repetitions") != 3:
        raise ValueError("expected_40_questions_three_repetitions")
    manifest = service.manifest
    if not development:
        from analytics311.qualification import comparison_qualification
        qualified = comparison_qualification(manifest)
        if (service.config["backend"] != "elastic" or manifest.get("immutable") is not True
                or manifest.get("row_count", 0) < 2000000
                or not qualified or qualified.get("stage") != "frozen_index"
                or manifest.get("geography", {}).get("nta_version") != nta["sha256"]):
            raise ValueError("real_million_corpus_qualification_required")
        if any(term in canonical(manifest).lower() for term in ('"synthetic_fixture"', '"generated_workload"')):
            raise ValueError("real_corpus_required")
    runtime = None if development else runtime_definition(runtime_spec, model)
    warmup_request = None
    if runtime and prefix_warmup_policy(runtime["definition"]):
        _, warmup_request = metadata_prefix_request(service.describe_dataset(), model)
    if Path(output).exists():
        raise ValueError("freeze_exists")
    if not Path(database).exists():
        source_info = build_database(source, database)
    else:
        with connect(database) as db:
            source_info = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM metadata")}
        if sha_file(source) != source_info["source_sha256"]:
            raise ValueError("oracle_source_mismatch")
    if source_info["rows"] != manifest["row_count"]:
        raise ValueError("oracle_index_count_mismatch")
    expected_source_hash = manifest.get("ingestion", {}).get("source_sha256") or manifest.get("source_sha256") or manifest.get("sha256")
    if not development and expected_source_hash != source_info["source_sha256"]:
        raise ValueError("oracle_index_source_hash_mismatch")
    residential = nta["residential_nta_codes"]
    if service.catalog.get("residential_nta2020") != residential:
        raise ValueError("catalog_residential_nta_codes_required")
    oracle = Oracle(database, service.catalog, residential)
    frozen = []
    try:
        for case in protocol["questions"]:
            item = copy.deepcopy(case)
            for step in item["steps"]:
                spec = oracle.expand(step["spec"])
                spec.update(schema_version="1", dataset_version=manifest["dataset_version"])
                if step.get("chain"):
                    chain = step["chain"]
                    previous = item["steps"][chain["step"]]["expected"]["rows"][:chain["take"]]
                    codes = [row["group"][chain["field"]] for row in previous]
                    if not codes:
                        raise ValueError("empty_chained_oracle_requires_new_benchmark_version")
                    spec["filters"] = {"all": [spec.get("filters", {}), {"field": chain["field"], "op": "in", "value": codes}]}
                step["spec"], step["expected"] = spec, oracle.evaluate(spec)
            frozen.append(item)
    finally:
        oracle.close()
    evidence = {"schema_version": 1, "evidence_kind": "prospective_ai_authored_agent_benchmark_freeze",
                "created_at": datetime.now(timezone.utc).isoformat(), "development_only": development,
                "questions_sha256": sha_file(questions), "code_sha256": code_hashes(), "model": model,
                "runtime_spec": runtime,
                "prefix_warmup_request": warmup_request,
                "model_settings": {"temperature": 0.2, "seeds": [101, 202, 303], "max_tokens": 2048},
                "manifest_sha256": digest(manifest), "catalog_sha256": digest(service.catalog),
                "database_sha256": sha_file(database), "source": source_info,
                "nta_sha256": nta["sha256"], "residential_nta_codes": residential,
                "cases": frozen, "repetitions": 3, "required_trials": 120, "pass_threshold": 0.9,
                "minimum_passes_per_question": 1,
                "semantic_review_required": True, "independent_human_labels": False,
                "limitations": ["Independent SQLite execution of the same normalized corpus; normalization and NTA assignment need separate qualification.",
                                "Prospective AI-authored questions are not human-held-out/generalization evidence.",
                                "Observed corpus comparison does not prove transactional source or population completeness.",
                                "Percentile tolerance fixed before execution: max(0.1 hour,5% of reference), exact metrics 1e-7 relative."]}
    write_new(output, evidence)
    return {"frozen": True, "cases": 40, "required_trials": 120, "rows": source_info["rows"], "development_only": development}


def pointer(value, path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("invalid_fact_pointer")
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _case_spec_matches(oracle, actual, expected, expected_result):
    if actual.get("operation") != expected["operation"] or actual.get("timezone", "America/New_York") != "America/New_York":
        return False
    if expected["operation"] != "records":
        if (actual.get("group_by", []) != expected.get("group_by", [])
                or not set(expected.get("metrics", ["count"])) <= set(actual.get("metrics", ["count"]))
                or actual.get("minimum_count", 0) != expected.get("minimum_count", 0)):
            return False
        for key, default in (("rank_by", "absolute_change" if expected["operation"] == "compare_periods" else "count"), ("rank_order", "desc")):
            if actual.get(key, default) != expected.get(key, default):
                return False
    def spans(value):
        periods = value.get("periods")
        if periods:
            return {name: (epoch(span["gte"]), epoch(span["lt"])) for name, span in periods.items()}
        span = value.get("time")
        return None if not span else (span.get("field", "created_date"), epoch(span["gte"]), epoch(span["lt"]))
    if spans(actual) != spans(expected):
        return False
    if expected_result["membership"]["count"] == 0:
        # Any two wrong empty queries have the same empty hash; do not grant an
        # intent pass merely because both returned zero.
        if canonical(oracle.expand(actual).get("filters")) != canonical(oracle.expand(expected).get("filters")):
            return False
    observed = oracle.evaluate(actual)
    if observed["membership"] != expected_result["membership"]:
        return False
    if expected["operation"] == "compare_periods" and observed.get("period_membership") != expected_result["period_membership"]:
        return False
    return numeric_equal(observed["rows"], expected_result["rows"])


def _csv_check(oracle, service, job, expected, kind):
    if job.get("status") != "complete" or job.get("complete") is not True:
        return False
    path = Path(job["file"]).resolve()
    if not path.is_relative_to(service.runs.resolve()) or path.name != job["job_id"] + ".csv":
        return False
    if sha_file(path) != job.get("sha256"):
        return False
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if kind == "records_csv":
            if reader.fieldnames != ["unique_key"]:
                return False
            oracle.db.execute("DROP TABLE IF EXISTS temp.export_ids")
            oracle.db.execute("CREATE TEMP TABLE export_ids(id TEXT PRIMARY KEY NOT NULL) WITHOUT ROWID")
            count = 0
            try:
                for row in reader:
                    if set(row) != {"unique_key"}:
                        return False
                    oracle.db.execute("INSERT INTO export_ids VALUES (?)", [row["unique_key"]])
                    count += 1
                    if count > expected["membership"]["count"]:
                        return False
            except sqlite3.IntegrityError:
                return False
            hashed = hashlib.sha256()
            for row in oracle.db.execute("SELECT id FROM export_ids ORDER BY id COLLATE BINARY"):
                hashed.update(canonical(row[0]).encode() + b"\n")
            return count == expected["membership"]["count"] == job.get("rows_written") and hashed.hexdigest() == expected["membership"]["ids_sha256"]
        rows = list(reader)
        expected_rows = expected["rows"]
        if len(rows) != len(expected_rows) or len(rows) != job.get("rows_written"):
            return False
        # CSV must include every oracle dimension and requested numeric metric;
        # an ID-only or count-only aggregate export is insufficient.
        for actual, wanted in zip(rows, expected_rows):
            flat = {**wanted["group"], **{key: value for key, value in wanted.items() if key != "group"}}
            for key, value in flat.items():
                if key not in actual:
                    return False
                text = actual[key]
                if value is None:
                    if text != "":
                        return False
                elif isinstance(value, (dict, list)):
                    if not numeric_equal(json.loads(text), value):
                        return False
                elif type(value) in (int, float):
                    if not numeric_equal(float(text), value, key):
                        return False
                elif text != str(value):
                    return False
    return True


def grade_trial(case, trace, service, oracle):
    checks, hard = {}, []
    final = trace.get("final") or {}
    events = [event for event in trace.get("events", []) if event.get("kind") == "tool"]
    analyses = [event for event in events if event.get("name") == "run_analysis" and "result_id" in event.get("output", {})]
    checks["finished"] = trace.get("status") == "finished"
    checks["status"] = final.get("status") == case["expected_status"]
    checks["answer_present"] = isinstance(final.get("answer"), str) and bool(final["answer"].strip())
    facts, matched, used = final.get("facts", []), [], set()
    if not isinstance(facts, list):
        hard.append("invalid_fact_schema")
        facts = []
    for fact in facts:
        try:
            outputs = [event["output"] for event in events if event["output"].get("result_id") == fact["result_id"]]
            if not outputs or not any(numeric_equal(pointer(output, fact["path"]), fact["value"]) for output in outputs):
                hard.append("fabricated_or_mismatched_numeric_evidence")
        except (KeyError, TypeError, ValueError, IndexError):
            hard.append("fabricated_or_mismatched_numeric_evidence")
    if case["expected_status"] != "answered":
        checks["no_unsupported_analysis"] = not analyses and not facts
        checks["no_unsupported_artifacts"] = not any(event["name"] in {"export_csv", "create_map_link"} for event in events)
    else:
        checks["numeric_evidence"] = any(type(fact.get("value")) in (int, float) for fact in facts if isinstance(fact, dict))
        checks["discover_first"] = bool(events) and events[0]["name"] == "describe_dataset"
        for number, step in enumerate(case["steps"]):
            found = None
            for index, event in enumerate(analyses):
                if index in used:
                    continue
                output = event["output"]
                actual = output.get("spec")
                if not actual or not _case_spec_matches(oracle, actual, step["spec"], step["expected"]):
                    continue
                saved = load(service.runs / (output["result_id"] + ".json"))
                if (saved.get("execution_complete") is not True or saved.get("evidence_level") != "elastic_execution"
                        or saved.get("total") != {"value": step["expected"]["membership"]["count"], "relation": "eq"}):
                    continue
                if step["spec"]["operation"] != "records" and not numeric_equal(saved.get("all_rows", []), step["expected"]["rows"]):
                    continue
                if step["spec"]["operation"] == "records":
                    if [row.get("unique_key") for row in output.get("rows", [])] != step["expected"]["preview_ids"]:
                        continue
                else:
                    requested = step["spec"].get("top_n", 20)
                    if not numeric_equal(output.get("rows", [])[:requested], step["expected"]["rows"][:requested]):
                        continue
                found = (event, saved, index)
                used.add(index)
                break
            checks[f"step_{number + 1}_query_and_numbers"] = found is not None
            matched.append(found)
        if any(step.get("chain") for step in case["steps"]):
            checks["chain_order"] = all(matched[index] is not None and matched[step["chain"]["step"]] is not None
                                         and matched[index][2] > matched[step["chain"]["step"]][2]
                                         for index, step in enumerate(case["steps"]) if step.get("chain"))
        citations = final.get("result_ids", [])
        checks["citations"] = (isinstance(citations, list) and all(isinstance(value, str) for value in citations)
                                and all(item is None or item[0]["output"]["result_id"] in citations for item in matched)
                                and set(citations) <= {event["output"]["result_id"] for event in analyses})
        checks["numeric_evidence_per_step"] = all(
            item is None or any(isinstance(fact, dict) and type(fact.get("value")) in (int, float)
                                and fact.get("result_id") == item[0]["output"]["result_id"] for fact in facts)
            for item in matched)
        for number, artifact in enumerate(case.get("artifacts", [])):
            found = matched[artifact["step"]]
            valid = False
            if found:
                result_id, saved = found[0]["output"]["result_id"], found[1]
                expectation = case["steps"][artifact["step"]]["expected"]
                selection = artifact.get("selected_top")
                expected_scope = "selected_groups" if selection else "all_matching"
                expected_group_ids = [row["group_id"] for row in saved["all_rows"][:selection]] if selection else None
                for event in events:
                    args, out = event.get("arguments", {}), event.get("output", {})
                    if args.get("result_id") != result_id or args.get("cohort_scope") != expected_scope:
                        continue
                    if selection and set(args.get("group_ids", [])) != set(expected_group_ids):
                        continue
                    if artifact["kind"].endswith("_csv") and event["name"] == "export_csv":
                        mode = "records" if artifact["kind"] == "records_csv" else "aggregates"
                        if args.get("mode") == mode and out.get("job_id"):
                            job = service.get_result(out["job_id"])
                            # Completion must also have been observed by the agent before its answer.
                            observed_complete = any(item.get("output", {}).get("job_id") == out["job_id"] and item["output"].get("status") == "complete" for item in events)
                            valid = observed_complete and _csv_check(oracle, service, job, expectation, artifact["kind"])
                    elif artifact["kind"].endswith("_map") and event["name"] == "create_map_link" and isinstance(out.get("url"), str):
                        mode = artifact["kind"].removesuffix("_map")
                        valid = args.get("mode") == mode
                        if mode == "requests":
                            valid = valid and out.get("source_count") == expectation["membership"]["count"] and out.get("mapped_count") == expectation["membership"]["geolocated_count"]
                        else:
                            wanted_groups = expectation["rows"][:selection] if selection else expectation["rows"]
                            valid = valid and out.get("published_group_count") == len(wanted_groups)
                    if valid:
                        break
            checks[f"artifact_{number + 1}_{artifact['kind']}"] = valid
    return {"automatic_pass": all(checks.values()) and not hard, "checks": checks, "hard_failures": sorted(set(hard)),
            "semantic_review": "pending", "end_to_end_pass": False, "visual_parity_verified": False}


def summarize(frozen, trials):
    expected = {(case["id"], repeat) for case in frozen["cases"] for repeat in (1, 2, 3)}
    observed, duplicates = {}, []
    for trial in trials:
        key = (trial["question_id"], trial["repeat"])
        if key not in expected or key in observed:
            duplicates.append(list(key))
        observed[key] = trial
    passes = sum(trial.get("grade", {}).get("automatic_pass") is True for key, trial in observed.items() if key in expected)
    elapsed = [trial["trace"]["elapsed_seconds"] for trial in observed.values() if "trace" in trial]
    hard = sorted({code for trial in observed.values() for code in trial.get("grade", {}).get("hard_failures", [])})
    missing = sorted(expected - observed.keys())
    by_question = {case["id"]: {"attempted": sum((case["id"], repeat) in observed for repeat in (1, 2, 3)),
                                "automatic_passes": sum(observed.get((case["id"], repeat), {}).get("grade", {}).get("automatic_pass") is True for repeat in (1, 2, 3))}
                   for case in frozen["cases"]}
    return {"required_trials": 120, "attempted_trials": len(observed), "automatic_passes": passes,
            "minimum_passes_per_question": frozen.get("minimum_passes_per_question", 1),
            "automatic_pass_rate": passes / 120, "missing_trials": [list(key) for key in missing],
            "invalid_or_duplicate_trials": duplicates, "hard_failures": hard, "by_question": by_question,
            "automatic_gate_passed": passes / 120 >= frozen["pass_threshold"] and not missing and not duplicates and not hard
                                     and all(value["automatic_passes"] >= frozen.get("minimum_passes_per_question", 1) for value in by_question.values()),
            "semantic_review": "pending", "end_to_end_pass_rate": None, "release_verified": False,
            "model_latency_seconds": {"samples": len(elapsed), "median": statistics.median(elapsed) if elapsed else None,
                                      "maximum": max(elapsed) if elapsed else None},
            "limitations": ["Automatic checks do not certify conversational prose, needed clarification wording or rendered map parity.",
                            "Three repetitions are not three independent questions; all missing/failing attempts remain in 120-denominator.",
                            "Independent second-client subset and semantic review remain separate evidence."]}


REVIEW_CHECKS = ("intent_correct", "narrative_grounded", "clarification_or_rejection_correct", "limitations_correct",
                 "artifacts_explained", "no_fabrication", "no_false_completion")


def review(freeze, runs, reviews, output):
    """Bind independent semantic judgments to exact immutable trial bytes.

    This imports real reviewer judgments, not model transcripts or invented
    adjudication. Declared reviewer identity needs external session evidence.
    """
    frozen, supplied = load(freeze), load(reviews)
    freeze_hash = sha_file(freeze)
    reviewer = supplied.get("reviewer", {})
    if (supplied.get("freeze_sha256") != freeze_hash or not isinstance(reviewer.get("id"), str) or not reviewer["id"]
            or reviewer.get("kind") not in {"independent_ai_session", "independent_human"}
            or reviewer.get("was_answering_agent") is not False):
        raise ValueError("independent_reviewer_provenance_required")
    actual, paths, execution_ids = [], {}, set()
    expected_keys = {(case["id"], repeat) for case in frozen["cases"] for repeat in (1, 2, 3)}
    for directory in runs:
        execution_hash = None
        if frozen.get("runtime_spec") is not None:
            identity = load(Path(directory) / "run-identity.json")
            runtime = identity.get("runtime", {})
            if (identity.get("freeze_sha256") != freeze_hash
                    or runtime.get("runtime_spec_sha256") != frozen["runtime_spec"]["sha256"]
                    or runtime.get("execution_runtime") != frozen["runtime_spec"]["definition"]["execution_runtime"]):
                raise ValueError("review_runtime_identity_mismatch")
            execution_hash = digest(identity)
            execution_ids.add(execution_hash)
        for path in sorted(Path(directory).glob("Q*-r*.json")):
            trial = load(path)
            key = (trial.get("question_id"), trial.get("repeat"))
            if (key not in expected_keys or key in paths or trial.get("freeze_sha256") != freeze_hash
                    or (execution_hash is not None and trial.get("execution_sha256") != execution_hash)):
                raise ValueError("duplicate_or_foreign_trial")
            if execution_hash is not None:
                check_archived_runtime_launch(directory, trial.get("runtime_receipt_sha256"), runtime)
                if prefix_warmup_policy(frozen["runtime_spec"]["definition"]):
                    check_archived_prefix_warmup(directory, trial.get("prefix_warmup_sha256"),
                                                  trial.get("runtime_receipt_sha256"), frozen, execution_hash)
            paths[key] = path
            actual.append(trial)
    if len(execution_ids) > 1:
        raise ValueError("mixed_runtime_or_budgets")
    report = summarize(frozen, actual)
    report["prefix_warmup"] = prefix_warmup_summary(runs)
    judgments = {}
    for item in supplied.get("reviews", []):
        key = (item.get("question_id"), item.get("repeat"))
        checks = item.get("checks", {})
        if (key not in paths or key in judgments or item.get("trial_sha256") != sha_file(paths[key])
                or set(checks) != set(REVIEW_CHECKS) or any(type(value) is not bool for value in checks.values())
                or not isinstance(item.get("notes"), str)):
            raise ValueError("review_does_not_match_exact_trial")
        judgments[key] = item
    end_to_end, fabrication = [], []
    by_question = {case["id"]: 0 for case in frozen["cases"]}
    for trial in actual:
        key = (trial["question_id"], trial["repeat"])
        judgment = judgments.get(key)
        if judgment and (not judgment["checks"]["no_fabrication"] or not judgment["checks"]["no_false_completion"]):
            fabrication.append(list(key))
        if judgment and all(judgment["checks"].values()) and trial.get("grade", {}).get("automatic_pass") is True:
            end_to_end.append(list(key))
            by_question[key[0]] += 1
    report.update(semantic_review="complete" if len(judgments) == 120 else "incomplete",
                  reviewed_trials=len(judgments), reviewer=reviewer, reviews_sha256=sha_file(reviews),
                  freeze_sha256=freeze_hash, end_to_end_passes=len(end_to_end), end_to_end_pass_rate=len(end_to_end) / 120,
                  end_to_end_by_question=by_question, semantic_fabrication_or_false_completion=fabrication,
                  agent_quality_gate_passed=(not frozen["development_only"] and frozen.get("runtime_spec") is not None
                                            and len(judgments) == 120
                                            and report["automatic_gate_passed"] and len(end_to_end) / 120 >= frozen["pass_threshold"]
                                            and all(value >= frozen.get("minimum_passes_per_question", 1) for value in by_question.values()) and not fabrication),
                  release_verified=False, second_agent_client_verified=False, visual_parity_verified=False)
    report["limitations"] += ["Reviewer identity/independence are declared provenance and require external review-session evidence.",
                              "This prospective AI-authored benchmark cannot establish questions were absent from model pretraining."]
    write_new(output, report)
    return report


def run(config, freeze, database, output, *, endpoint, seconds=300, request_seconds=90,
        questions=QUESTIONS, repetition=None, resume=False, runtime_spec=RUNTIME_SPEC, runtime_receipt=RUNTIME_RECEIPT):
    from analytics311.service import AnalyticsService
    frozen = load(freeze)
    service = AnalyticsService(config)
    output = Path(output)
    if output.exists() and not resume:
        raise ValueError("run_directory_exists")
    if resume and not output.is_dir():
        raise ValueError("resume_directory_missing")
    if repetition not in (None, 1, 2, 3) or type(seconds) is not int or not 1 <= seconds <= 1800:
        raise ValueError("invalid_trial_budget")
    if (frozen["code_sha256"] != code_hashes() or frozen["questions_sha256"] != sha_file(questions)
            or frozen["database_sha256"] != sha_file(database)
            or frozen["manifest_sha256"] != digest(service.manifest) or frozen["catalog_sha256"] != digest(service.catalog)):
        raise ValueError("frozen_inputs_changed")
    freeze_hash = sha_file(freeze)
    runtime = None
    warmup_policy = None
    if not frozen["development_only"]:
        if frozen.get("runtime_spec") != runtime_definition(runtime_spec, frozen["model"]):
            raise ValueError("frozen_runtime_changed")
        runtime = verify_runtime_receipt(runtime_receipt, frozen, freeze_hash,
                                         endpoint=endpoint, seconds=seconds, request_seconds=request_seconds)
        warmup_policy = prefix_warmup_policy(frozen["runtime_spec"]["definition"])
    output.mkdir(parents=True, exist_ok=resume)
    model = LocalModel(endpoint, frozen["model"], request_seconds=request_seconds)
    run_identity = {"freeze_sha256": freeze_hash, "model": frozen["model"], "seconds": seconds,
                    "request_seconds": request_seconds, "max_calls": 24}
    if runtime is not None:
        run_identity["runtime"] = runtime["identity"]
    execution_hash = digest(run_identity)
    if resume:
        if load(output / "run-identity.json") != run_identity:
            raise ValueError("resume_identity_changed")
    else:
        write_new(output / "run-identity.json", run_identity)
    if runtime is not None:
        launch_path = output / ("runtime-launch-" + runtime["sha256"] + ".json")
        if launch_path.exists():
            if load(launch_path) != runtime:
                raise ValueError("runtime_launch_receipt_changed")
        else:
            write_new(launch_path, runtime)
    trials = []
    all_cases = {case["id"]: case for case in frozen["cases"]}
    for path in sorted(output.glob("Q*-r*.json")):
        trial = load(path)
        qid, repeat = trial.get("question_id"), trial.get("repeat")
        if (qid not in all_cases or repeat not in (1, 2, 3) or path.name != f"{qid}-r{repeat}.json"
                or trial.get("freeze_sha256") != freeze_hash or trial["trace"]["question"] != all_cases[qid]["question"]
                or trial["trace"]["seed"] != frozen["model_settings"]["seeds"][repeat - 1]
                or trial.get("execution_sha256") != execution_hash):
            raise ValueError("resume_trial_mismatch")
        if runtime is not None:
            check_archived_runtime_launch(output, trial.get("runtime_receipt_sha256"), runtime["identity"])
            if warmup_policy:
                check_archived_prefix_warmup(output, trial.get("prefix_warmup_sha256"),
                                              trial.get("runtime_receipt_sha256"), frozen, execution_hash)
        trials.append(trial)
    completed = {(trial["question_id"], trial["repeat"]) for trial in trials}

    def save_summary(report):
        # Earlier summaries and every trial remain immutable. Only this convenient
        # latest pointer is replaced during explicit missing-only resumption.
        report["prefix_warmup"] = prefix_warmup_summary([output])
        snapshot = output / f"summary-{time.time_ns()}.json"
        write_new(snapshot, report)
        temporary = output / f"summary-{time.time_ns()}.tmp"
        write_new(temporary, report)
        os.replace(temporary, output / "summary.json")

    try:
        model_identity = model.identify()
    except AgentFailure as exc:
        report = summarize(frozen, trials)
        report.update(error={"code": exc.code}, freeze_sha256=freeze_hash, development_only=frozen["development_only"])
        save_summary(report)
        return report
    warmup_hash = None
    if warmup_policy:
        warmup_path = output / ("metadata-prefix-warmup-" + runtime["sha256"] + ".json")
        if not warmup_path.exists():
            warmup = warm_metadata_prefix(service, model, seconds=warmup_policy["request_seconds"])
            warmup.update(runtime_receipt_sha256=runtime["sha256"], execution_sha256=execution_hash,
                          runtime_spec_sha256=frozen["runtime_spec"]["sha256"],
                          runtime_memory=runtime_memory_snapshot(runtime["receipt"]["owned_server_pid"]))
            write_new(warmup_path, warmup)
        warmup = load(warmup_path)
        if warmup.get("passed") is not True:
            report = summarize(frozen, trials)
            report.update(error={"code": "prefix_warmup_failed"}, freeze_sha256=freeze_hash,
                          development_only=frozen["development_only"], execution_complete=False)
            save_summary(report)
            return report
        warmup_hash = sha_file(warmup_path)
        check_archived_prefix_warmup(output, warmup_hash, runtime["sha256"], frozen, execution_hash)
    oracle = Oracle(database, service.catalog, frozen["residential_nta_codes"])
    try:
        for repeat, seed in enumerate(frozen["model_settings"]["seeds"], 1):
            if repetition is not None and repeat != repetition:
                continue
            for case in frozen["cases"]:
                if (case["id"], repeat) in completed:
                    continue
                # Only the question and discovery/tool responses reach the model.
                # Hidden specifications, expected values and other sessions never do.
                trace = run_trial(service, model, case["question"], seed=seed, seconds=seconds,
                                  untrusted_note=case.get("untrusted_note"))
                memory = runtime_memory_snapshot(runtime["receipt"]["owned_server_pid"]) if runtime else None
                try:
                    grade = grade_trial(case, trace, service, oracle)
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, csv.Error) as exc:
                    grade = {"automatic_pass": False, "checks": {}, "hard_failures": [], "error": "grader_failed",
                             "semantic_review": "pending", "end_to_end_pass": False}
                trial = {"question_id": case["id"], "repeat": repeat, "freeze_sha256": freeze_hash,
                         "execution_sha256": execution_hash,
                         "prefix_warmup_sha256": warmup_hash,
                         "runtime_memory": memory,
                         "runtime_receipt_sha256": runtime["sha256"] if runtime else None, "trace": trace, "grade": grade}
                write_new(output / f"{case['id']}-r{repeat}.json", trial)
                trials.append(trial)
    finally:
        oracle.close()
        report = summarize(frozen, trials)
        requested = {(case["id"], repeat) for case in frozen["cases"] for repeat in (1, 2, 3) if repetition is None or repeat == repetition}
        observed = {(trial["question_id"], trial["repeat"]) for trial in trials}
        report.update(freeze_sha256=freeze_hash, model_identity=model_identity,
                      execution_sha256=execution_hash, runtime_receipt_sha256=runtime["sha256"] if runtime else None,
                      requested_repetitions=[1, 2, 3] if repetition is None else [repetition],
                      requested_trials=len(requested), execution_complete=requested <= observed,
                      development_only=frozen["development_only"], finished_at=datetime.now(timezone.utc).isoformat())
        save_summary(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("prepare")
    freeze.add_argument("--config", required=True)
    freeze.add_argument("--source", required=True)
    freeze.add_argument("--database", required=True)
    freeze.add_argument("--output", required=True)
    freeze.add_argument("--model", required=True)
    freeze.add_argument("--questions", default=str(QUESTIONS))
    freeze.add_argument("--nta-receipt", default=str(NTA_RECEIPT))
    freeze.add_argument("--development", action="store_true")
    freeze.add_argument("--runtime-spec", default=str(RUNTIME_SPEC))
    execute = sub.add_parser("run")
    execute.add_argument("--config", required=True)
    execute.add_argument("--freeze", required=True)
    execute.add_argument("--database", required=True)
    execute.add_argument("--output", required=True)
    execute.add_argument("--endpoint", required=True)
    execute.add_argument("--seconds", type=int, default=300)
    execute.add_argument("--request-seconds", type=int, default=90)
    execute.add_argument("--repetition", type=int, choices=(1, 2, 3))
    execute.add_argument("--resume", action="store_true", help="Run only missing trials; preserve completed failures and earlier summaries")
    execute.add_argument("--questions", default=str(QUESTIONS))
    execute.add_argument("--runtime-spec", default=str(RUNTIME_SPEC))
    execute.add_argument("--runtime-receipt", default=str(RUNTIME_RECEIPT))
    adjudicate = sub.add_parser("review")
    adjudicate.add_argument("--freeze", required=True)
    adjudicate.add_argument("--runs", nargs="+", required=True)
    adjudicate.add_argument("--reviews", required=True)
    adjudicate.add_argument("--output", required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        result = prepare(**args) if command == "prepare" else run(**args) if command == "run" else review(**args)
    except (ValueError, OSError, sqlite3.Error, AgentFailure) as exc:
        print(canonical({"error": {"code": getattr(exc, "code", str(exc)) if isinstance(exc, (ValueError, AgentFailure)) else "evaluation_failed"}}))
        return 2
    print(canonical({key: result[key] for key in ("frozen", "cases", "rows", "required_trials", "attempted_trials", "automatic_passes", "automatic_gate_passed", "agent_quality_gate_passed", "end_to_end_pass_rate", "release_verified", "development_only") if key in result}))
    return 0 if result.get("frozen") or (result.get("agent_quality_gate_passed") if command == "review" else result.get("automatic_gate_passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
