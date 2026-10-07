"""One analytical service shared by CLI, MCP, and local export workers."""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .errors import AnalyticsError
from .metadata_io import retry_metadata_io
from .contracts import FIELDS, normalize_spec
from .compiler import compile_query, compile_search
from .resources import default_config_path, load_profile
from .settings import effective_budgets, validate_manifest
from . import __version__


DEFAULT_CONFIG = default_config_path()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    try:
        # Close the reader before parsing; retries never include JSON decoding.
        content = retry_metadata_io(lambda: Path(path).read_text(encoding="utf-8-sig"))
        return json.loads(content)
    except (OSError, ValueError) as exc:
        raise AnalyticsError("invalid_configuration", f"Cannot read JSON file: {Path(path).name}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(canonical(value), encoding="utf-8")
        retry_metadata_io(lambda: os.replace(temporary, path))
    finally:
        temporary.unlink(missing_ok=True)


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bucket_start(value, interval, zone):
    dt = instant(value).astimezone(zone)
    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "week":
        dt -= timedelta(days=dt.weekday())
    elif interval == "month":
        dt = dt.replace(day=1)
    return dt


def _next_bucket(dt, interval):
    if interval == "month":
        return dt.replace(year=dt.year + (dt.month == 12), month=dt.month % 12 + 1, day=1)
    return dt + timedelta(days=7 if interval == "week" else 1)


def group_id(group):
    return fingerprint(group)[:24]


class _CsvBudgetWriter:
    def __init__(self, stream, maximum):
        self.stream, self.maximum, self.bytes_written = stream, maximum, 3  # UTF-8 BOM
        self.digest = hashlib.sha256(b"\xef\xbb\xbf")

    def write(self, value):
        encoded = value.encode("utf-8")
        size = len(encoded)
        if self.bytes_written + size > self.maximum:
            raise AnalyticsError("budget_exceeded", "Export byte budget exceeded; no partial CSV published")
        result = self.stream.write(value)
        self.digest.update(encoded)
        self.bytes_written += size
        return result


class AnalyticsService:
    def __init__(self, config_path=None):
        self.config_path, self.config = load_profile(config_path)
        for required in ("backend", "manifest_path", "catalog_path", "runs_dir"):
            if required not in self.config:
                raise AnalyticsError("invalid_configuration", f"Missing {required}")
        self.catalog = read_json(self.config["catalog_path"])
        self.manifest = read_json(self.config["manifest_path"])
        validate_manifest(self.manifest)
        if not isinstance(self.catalog, dict):
            raise AnalyticsError("invalid_configuration", "Catalog must be an object")
        self.budgets = effective_budgets(self.config.get("budgets", {}))
        self.config["budgets"] = self.budgets
        self.runs = Path(self.config["runs_dir"])
        self.runs.mkdir(parents=True, exist_ok=True)
        if self.config["backend"] == "fixture":
            from .fixture import FixtureBackend
            self.backend = FixtureBackend(self.config, self.catalog, self.manifest)
        elif self.config["backend"] == "elastic":
            from .elastic import ElasticBackend
            self.backend = ElasticBackend(self.config, self.catalog, self.manifest)
        else:
            raise AnalyticsError("invalid_configuration", "backend must be fixture or elastic")

    def _identity(self):
        value = {"engine_version": __version__, "manifest": self.manifest, "catalog": self.catalog, "backend": self.config["backend"],
                 "index": self.config.get("index"), "elastic_url": self.config.get("elastic_url")}
        if self.config["backend"] == "fixture":
            value["fixture_sha256"] = file_hash(self.config["fixture_path"])
        return fingerprint(value)

    def _path(self, result_id):
        if not isinstance(result_id, str) or not re.fullmatch(r"[0-9a-f]{32}", result_id):
            raise AnalyticsError("invalid_spec", "Invalid result/job ID")
        return self.runs / f"{result_id}.json"

    def _load(self, result_id, check_identity=True):
        path = self._path(result_id)
        if not path.is_file():
            raise AnalyticsError("result_expired", "Result/job not found in this configured store")
        result = read_json(path)
        if check_identity and result.get("dataset_identity") != self._identity():
            raise AnalyticsError("result_expired", "Dataset, catalog or engine version changed; rerun the analysis")
        return result

    def describe_dataset(self, field=None):
        from .guide import analysis_guide
        if field is not None and field not in FIELDS:
            raise AnalyticsError("invalid_spec", "Unknown field")
        return {"dataset": self.manifest, "backend": self.config["backend"],
                "fields": {field: FIELDS[field]} if field else FIELDS,
                "catalog": self.catalog, "limits": self.budgets,
                "evidence_level": "fixture_only" if self.config["backend"] == "fixture" else "elastic_execution",
                "operations": ["records", "aggregate", "compare_periods"],
                "analysis_guide": analysis_guide(self.manifest["dataset_version"])}

    def _normalized(self, spec):
        spec = normalize_spec(spec, self.catalog, self.budgets)
        if spec["dataset_version"] != self.manifest.get("dataset_version"):
            raise AnalyticsError("invalid_spec", "Unknown dataset version; use describe_dataset")
        return spec

    def _coverage(self, spec):
        from .qualification import comparison_qualification
        coverage = self.manifest.get("coverage", {})
        qualified = comparison_qualification(self.manifest)
        spans = list(spec["periods"].values()) if spec["operation"] == "compare_periods" else [spec.get("time")]
        complete = coverage.get("complete") is True
        within_observation = qualified is not None
        def date_predicate(node):
            if not isinstance(node, dict):
                return False
            if node.get("field") in ("created_date", "closed_date"):
                return True
            return any(date_predicate(child) for key in ("all", "any") for child in node.get(key, [])) or date_predicate(node.get("not"))
        if spec["operation"] != "compare_periods" and not spec.get("time") and date_predicate(spec.get("filters")):
            # Date filters can select beyond the captured population, including
            # through OR/NOT. Require an explicit enclosing creation window.
            complete = False
            within_observation = False
        for span in spans:
            if not span:
                continue
            # Dataset coverage is creation-date coverage, not closure-date coverage.
            if span.get("field", "created_date") != "created_date":
                complete = False
                within_observation = False
                continue
            if not coverage.get("gte") or not coverage.get("lt"):
                complete = False
            elif instant(span["gte"]) < instant(coverage["gte"]) or instant(span["lt"]) > instant(coverage["lt"]):
                complete = False
            if qualified and (instant(span["gte"]) < instant(qualified["gte"]) or instant(span["lt"]) > instant(qualified["lt"])):
                within_observation = False
        if not (complete or within_observation) and (spec["operation"] == "compare_periods" or any("interval" in dim for dim in spec.get("group_by", []))):
            raise AnalyticsError("coverage_gap", "Comparisons and calendar buckets require complete creation-date coverage or a reconciled observed-corpus qualification; unobserved dates cannot become zeros")
        return complete, qualified if within_observation else None

    def validate_analysis(self, spec):
        spec = self._normalized(spec)
        covered, qualified = self._coverage(spec)
        from .qualification import WARNING
        queries = []
        if spec["operation"] == "compare_periods":
            for name in ("baseline", "current"):
                queries.append({"period": name, "body": compile_search(self._period_spec(spec, name))})
        else:
            queries.append({"body": compile_search(spec)})
        return {"normalized_spec": spec, "compiled_queries": queries, "coverage_complete": covered,
                "comparison_scope": qualified["scope"] if qualified else ("complete_declared_corpus" if covered else "unqualified_snapshot"),
                "warnings": ([WARNING] if qualified else []) + ([] if covered else ["Results cover only the available snapshot, not the full requested population."])}

    @staticmethod
    def _period_spec(spec, name):
        result = copy.deepcopy(spec)
        result["operation"] = "aggregate"
        result["time"] = {"field": "created_date", **result.pop("periods")[name]}
        result["rank_by"] = "count"
        return result

    def _dense_time(self, rows, spec):
        dims = spec.get("group_by", [])
        date_dim = next((dim for dim in dims if "interval" in dim), None)
        if not date_dim:
            return rows, []
        date_field = date_dim["field"]
        other = [dim["field"] for dim in dims if dim["field"] != date_field]
        combinations = {tuple(row["group"].get(f) for f in other) for row in rows}
        if not other:
            combinations = {()}
        zone = ZoneInfo(spec["timezone"])
        start = _bucket_start(spec["time"]["gte"], date_dim["interval"], zone)
        end = instant(spec["time"]["lt"])
        buckets = []
        while start < end:
            buckets.append(start.isoformat())
            if len(buckets) > self.budgets.get("max_groups", 50000):
                raise AnalyticsError("budget_exceeded", "Too many calendar buckets")
            start = _next_bucket(start, date_dim["interval"])
        if len(buckets) * len(combinations) > self.budgets.get("max_groups", 50000):
            raise AnalyticsError("budget_exceeded", "Dense calendar result exceeds group budget")
        lookup = {}
        for row in rows:
            group = row["group"]
            key = (tuple(group.get(f) for f in other), instant(group[date_field]).timestamp())
            lookup[key] = row
        dense = []
        for combo, date in itertools.product(sorted(combinations, key=canonical), buckets):
            row = lookup.get((combo, instant(date).timestamp()))
            if row is None:
                row = {"group": {**dict(zip(other, combo)), date_field: date}, "count": 0}
                for metric in spec["metrics"]:
                    row[metric] = 0 if metric in ("count", "closed_count", "open_count") else None
            else:
                row["group"][date_field] = date
            dense.append(row)
        return dense, ["Calendar buckets are zero-filled for observed categorical combinations; unobserved combinations are not inferred."] if other else []

    def _compare(self, spec, *, deadline=None):
        baseline = self.backend.execute(self._period_spec(spec, "baseline"), deadline=deadline)
        current = self.backend.execute(self._period_spec(spec, "current"), deadline=deadline)
        pairs = {}
        for name, result in (("baseline", baseline), ("current", current)):
            for row in result["rows"]:
                key = canonical(row["group"])
                if key not in pairs and len(pairs) >= self.budgets.get("max_groups", 50000):
                    raise AnalyticsError("budget_exceeded", "Comparison group budget exceeded")
                pairs.setdefault(key, {"group": row["group"]})[name] = row
        zone = ZoneInfo(spec["timezone"])
        days = {}
        for name, span in spec["periods"].items():
            # Calendar-day exposure; offset changes at DST do not create fractional calendar days.
            a = instant(span["gte"]).astimezone(zone).replace(tzinfo=None)
            b = instant(span["lt"]).astimezone(zone).replace(tzinfo=None)
            days[name] = (b - a).total_seconds() / 86400
            if days[name] <= 0:
                raise AnalyticsError("invalid_spec", "Comparison needs positive calendar exposure")
        rows = []
        empty = {metric: 0 if metric in ("count", "closed_count", "open_count") else None for metric in spec["metrics"]}
        empty["count"] = 0
        for pair in pairs.values():
            b = pair.get("baseline", empty)
            c = pair.get("current", empty)
            bv, cv = b["count"], c["count"]
            rows.append({"group": pair["group"], "count": cv, "baseline_count": bv, "current_count": cv,
                         "baseline_days": days["baseline"], "current_days": days["current"],
                         "baseline_daily_rate": bv / days["baseline"], "current_daily_rate": cv / days["current"],
                         "absolute_change": cv - bv, "relative_change": (cv - bv) / bv if bv else None,
                         "rate_change": cv / days["current"] - bv / days["baseline"],
                         "baseline_metrics": {k: v for k, v in b.items() if k != "group"},
                         "current_metrics": {k: v for k, v in c.items() if k != "group"}})
        return {"rows": rows, "total": baseline["total"] + current["total"],
                "approximate": baseline.get("approximate", False) or current.get("approximate", False),
                "warnings": list(dict.fromkeys(baseline.get("warnings", []) + current.get("warnings", [])))}

    def run_analysis(self, spec):
        started = time.monotonic()
        deadline = started + self.budgets["deadline_seconds"]
        validated = self.validate_analysis(spec)
        spec = validated["normalized_spec"]
        identity = self._identity()
        result = self._compare(spec, deadline=deadline) if spec["operation"] == "compare_periods" else self.backend.execute(spec, deadline=deadline)
        rows = result["rows"]
        warnings = validated["warnings"] + self.manifest.get("warnings", []) + result.get("warnings", [])
        if spec["operation"] != "records":
            rows, extra = self._dense_time(rows, spec)
            warnings += extra
            before_threshold = len(rows)
            minimum = spec.get("minimum_count", 0)
            rows = [row for row in rows if (row.get("baseline_count", 0) + row["count"]) >= minimum]
            if minimum:
                warnings.append(f"Minimum count {minimum} excluded {before_threshold - len(rows)} groups; comparisons use combined baseline/current count.")
            for row in rows:
                row["group_id"] = group_id(row["group"])
            rank = spec["rank_by"]
            finite = [row for row in rows if row.get(rank) is not None]
            missing = [row for row in rows if row.get(rank) is None]
            finite.sort(key=lambda row: canonical(row["group"]))
            finite.sort(key=lambda row: row.get(rank, 0), reverse=spec["rank_order"] == "desc")
            rows = finite + sorted(missing, key=lambda row: canonical(row["group"]))
        if self._identity() != identity:
            raise AnalyticsError("partial_execution", "Dataset changed during analysis")
        if time.monotonic() - started > self.budgets.get("deadline_seconds", 30):
            raise AnalyticsError("budget_exceeded", "Analytical deadline exceeded")
        result_id = uuid.uuid4().hex
        saved = {"kind": "analysis", "result_id": result_id, "dataset_identity": identity,
                 "created_at": datetime.now(timezone.utc).isoformat(), "spec": spec,
                 "compiled_queries": validated["compiled_queries"], "all_rows": rows,
                 "total": {"value": result["total"], "relation": "eq"},
                 "group_count": len(rows) if spec["operation"] != "records" else None,
                 "execution_complete": True, "coverage_complete": validated["coverage_complete"],
                 "comparison_scope": validated["comparison_scope"],
                 "approximate": result.get("approximate", False), "warnings": list(dict.fromkeys(warnings)),
                 "evidence_level": "fixture_only" if self.config["backend"] == "fixture" else "elastic_execution",
                 "dataset": self.manifest, "catalog_sha256": fingerprint(self.catalog),
                 "elapsed_seconds": round(time.monotonic() - started, 6)}
        if self.config["backend"] == "fixture":
            saved["warnings"].append("Development reference backend execution does not validate Elasticsearch, Kibana, or citywide findings. Inspect dataset.kind for source provenance.")
        atomic_json(self._path(result_id), saved)
        return self.get_result(result_id)

    def get_result(self, result_id, cursor=None, page_size=None):
        saved = self._load(result_id, check_identity=False)
        if saved["kind"] != "analysis":
            return {k: v for k, v in saved.items() if k not in ("dataset_identity", "request")}
        if saved.get("dataset_identity") != self._identity():
            raise AnalyticsError("result_expired", "Dataset, catalog or engine version changed; rerun the analysis")
        size = page_size if page_size is not None else (saved["spec"]["preview_limit"] if saved["spec"]["operation"] == "records" else saved["spec"]["top_n"])
        if type(size) is not int or not 1 <= size <= 100:
            raise AnalyticsError("invalid_spec", "page_size must be 1..100")
        offset = 0
        if cursor is not None:
            if not isinstance(cursor, str) or len(cursor) > 8192:
                raise AnalyticsError("invalid_spec", "Invalid result cursor")
            try:
                data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if data["result_id"] != result_id or type(data["offset"]) is not int or data["offset"] < 0:
                    raise ValueError()
                offset = data["offset"]
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                raise AnalyticsError("invalid_spec", "Invalid result cursor") from exc
        rows = saved["all_rows"]
        # Record previews stay bounded; export_csv is the full-cohort path.
        page = rows[offset:offset + size]
        next_cursor = None
        if offset + size < len(rows):
            next_cursor = base64.urlsafe_b64encode(canonical({"result_id": result_id, "offset": offset + size}).encode()).decode()
        result = {k: v for k, v in saved.items() if k not in ("all_rows", "dataset_identity")}
        result.update(rows=page, next_cursor=next_cursor,
                      preview_truncated=(len(rows) > len(page) or (saved["spec"]["operation"] == "records" and saved["total"]["value"] > len(page))))
        return result

    def _selection(self, saved, cohort_scope, group_ids):
        if cohort_scope not in ("all_matching", "selected_groups"):
            raise AnalyticsError("invalid_spec", "cohort_scope must explicitly be all_matching or selected_groups")
        if cohort_scope == "all_matching":
            if group_ids:
                raise AnalyticsError("invalid_spec", "group_ids only valid for selected_groups")
            return None
        if not isinstance(group_ids, list) or not group_ids or len(group_ids) > 100:
            raise AnalyticsError("invalid_spec", "Select 1..100 saved group IDs")
        available = {row["group_id"]: row for row in saved["all_rows"] if "group_id" in row}
        if any(not isinstance(key, str) or key not in available for key in group_ids):
            raise AnalyticsError("invalid_spec", "Unknown saved group ID")
        return [available[key] for key in dict.fromkeys(group_ids)]

    def _record_specs(self, saved, selected=None):
        source = copy.deepcopy(saved["spec"])
        specs = [self._period_spec(source, name) for name in ("baseline", "current")] if source["operation"] == "compare_periods" else [source]
        for spec in specs:
            spec["operation"] = "records"
            if selected is not None:
                alternatives = []
                for row in selected:
                    clauses = []
                    for dim in spec.get("group_by", []):
                        field, value = dim["field"], row["group"].get(dim["field"])
                        if "interval" in dim:
                            end = _next_bucket(instant(value).astimezone(ZoneInfo(spec["timezone"])), dim["interval"]).isoformat()
                            clauses.append({"field": field, "op": "range", "value": {"gte": value, "lt": end}})
                        elif value is None:
                            clauses.append({"not": {"field": field, "op": "exists", "value": True}})
                        else:
                            clauses.append({"field": field, "op": "eq", "value": value})
                    alternatives.append({"all": clauses})
                spec["filters"] = {"all": [spec.get("filters", {"all": []}), {"any": alternatives}]}
            spec["group_by"] = []
            yield spec

    @staticmethod
    def _export_row_count(saved, mode, selected):
        """Use exact saved counts to reject impossible exports before admission."""
        def invalid():
            raise AnalyticsError("invalid_spec", "Saved result lacks consistent exact export counts; rerun the analysis")

        def count(value):
            if type(value) is not int or value < 0:
                invalid()
            return value

        total = saved.get("total")
        if (saved.get("execution_complete") is not True or not isinstance(total, dict)
                or total.get("relation") != "eq"):
            invalid()
        total = count(total.get("value"))
        rows = saved.get("all_rows") if selected is None else selected
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            invalid()
        if mode == "aggregates":
            return len(rows)
        if selected is None:
            return total
        comparison = saved["spec"]["operation"] == "compare_periods"
        projected = 0
        for row in rows:
            current = count(row.get("count"))
            if comparison:
                if count(row.get("current_count")) != current:
                    invalid()
                projected += count(row.get("baseline_count"))
            projected += current
        if projected > total:
            invalid()
        return projected

    def export_csv(self, result_id, mode, cohort_scope, columns=None, group_ids=None):
        saved = self._load(result_id)
        if saved["kind"] != "analysis":
            raise AnalyticsError("invalid_spec", "Export requires an analysis result")
        selected = self._selection(saved, cohort_scope, group_ids)
        if mode not in ("records", "aggregates") or (mode == "aggregates" and saved["spec"]["operation"] == "records"):
            raise AnalyticsError("invalid_spec", "Choose records, or aggregates for an aggregate result")
        if columns is not None and (not isinstance(columns, list) or not columns or any(not isinstance(c, str) for c in columns) or len(set(columns)) != len(columns)):
            raise AnalyticsError("invalid_spec", "columns must be a nonempty list of unique field names")
        if mode == "records" and columns and any(c not in FIELDS for c in columns):
            raise AnalyticsError("invalid_spec", "Unknown export column")
        planned_rows = self._export_row_count(saved, mode, selected)
        if planned_rows > self.budgets["max_export_rows"]:
            raise AnalyticsError("budget_exceeded", "Matching export rows exceed max_export_rows; narrow the cohort or configure a larger explicit budget")
        job_id = uuid.uuid4().hex
        queued_at = datetime.now(timezone.utc).isoformat()
        job = {"kind": "export", "job_id": job_id, "status": "queued", "dataset_identity": saved["dataset_identity"],
               "queued_at": queued_at, "stage": "queued", "stage_started_at": queued_at,
               "last_progress_at": queued_at, "elapsed_seconds": 0,
               "result_id": result_id, "planned_rows": planned_rows, "rows_written": 0, "bytes_written": 0, "complete": False,
               "request": {"mode": mode, "cohort_scope": cohort_scope, "columns": columns, "group_ids": group_ids}}
        from .jobs import reserve_export
        with reserve_export(self.runs, job_id, self.budgets["max_concurrent_exports"]):
            self._start_export(job)
        return self.get_result(job_id)

    def _start_export(self, job):
        job_id = job["job_id"]
        atomic_json(self._path(job_id), job)
        if self.config.get("export_inline", False):
            self.run_export_job(job_id)
        else:
            kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            # The detached worker must use this package's code and bundled asset
            # identity, even when a different wheel is installed in the interpreter.
            environment = os.environ.copy()
            import_root = str(Path(__file__).resolve().parents[1])
            environment["PYTHONPATH"] = os.pathsep.join(
                [import_root, environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else [import_root])
            kwargs["env"] = environment
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            try:
                subprocess.Popen([sys.executable, "-P", "-m", "analytics311.cli", "--config", str(self.config_path), "_export-job", job_id], cwd=str(self.runs.parent), **kwargs)
            except OSError as exc:
                finished = datetime.now(timezone.utc).isoformat()
                job.update(status="failed", stage="failed", stopped_stage="queued", finished_at=finished,
                           stage_started_at=finished, last_progress_at=finished,
                           error={"code": "backend_unavailable", "message": "Could not start export worker"})
                atomic_json(self._path(job_id), job)
                raise AnalyticsError("backend_unavailable", "Could not start export worker") from exc

    def cancel_export(self, job_id):
        job = self._load(job_id, check_identity=False)
        if job["kind"] != "export":
            raise AnalyticsError("invalid_spec", "ID is not an export job")
        if job["status"] in ("queued", "running"):
            self._path(job_id).with_suffix(".cancel").touch()
            return {"job_id": job_id, "status": "cancellation_requested"}
        return {"job_id": job_id, "status": job["status"]}

    @staticmethod
    def _csv_value(value):
        if isinstance(value, (dict, list)):
            value = canonical(value)
        if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n"))):
            return "'" + value
        return value

    def run_export_job(self, job_id):
        from .jobs import acquire_job
        with acquire_job(self.runs, job_id):
            return self._run_export_job_locked(job_id)

    def _run_export_job_locked(self, job_id):
        job = self._load(job_id, check_identity=False)
        if job["kind"] != "export" or job["status"] != "queued":
            raise AnalyticsError("invalid_spec", "Job is not queued")
        partial = self.runs / f"{job_id}.csv.part"
        final = self.runs / f"{job_id}.csv"
        cancel = self._path(job_id).with_suffix(".cancel")
        iterator = None
        started = time.monotonic()
        deadline = started + self.budgets.get("export_deadline_seconds", 300)
        last_checkpoint = started

        def progress(stage=None, *, now=None, force=False):
            nonlocal last_checkpoint
            now = time.monotonic() if now is None else now
            changed = stage is not None and stage != job.get("stage")
            # Persist one current snapshot, at most once per second during a scan.
            # A blocked call produces no heartbeat and must not imply liveness.
            if not (changed or force or now - last_checkpoint >= 1):
                return
            timestamp = datetime.now(timezone.utc).isoformat()
            if changed:
                job.update(stage=stage, stage_started_at=timestamp)
            job.update(last_progress_at=timestamp, elapsed_seconds=round(now - started, 6))
            atomic_json(self._path(job_id), job)
            last_checkpoint = now

        def close_source(source):
            # No CSV is published until its source has closed successfully.
            try:
                progress("closing_source")
            finally:
                if hasattr(source, "close"):
                    try:
                        source.close()
                    except Exception as exc:
                        raise AnalyticsError("export_cleanup_failed", "Could not close export source; no complete artifact published") from exc

        def fail(error):
            job.update(status="cancelled" if error["code"] == "cancelled" else "failed",
                       stopped_stage=job.get("stopped_stage", job.get("stage", "queued")), error=error, complete=False)

        try:
            job.update(status="running", started_at=datetime.now(timezone.utc).isoformat(),
                       deadline_at=(datetime.now(timezone.utc) + timedelta(seconds=self.budgets.get("export_deadline_seconds", 300))).isoformat())
            progress("validating")
            if cancel.exists():
                raise AnalyticsError("cancelled", "Export cancelled")
            self._load(job_id)
            saved = self._load(job["result_id"])
            request = job["request"]
            selected = self._selection(saved, request["cohort_scope"], request["group_ids"])
            if request["mode"] == "aggregates":
                rows = selected if selected is not None else saved["all_rows"]
                allowed = sorted({key for row in rows for key in (*row.get("group", {}), *row) if key != "group"}) if rows else [d["field"] for d in saved["spec"].get("group_by", [])] + ["count"]
                columns = request["columns"] or allowed
                if any(c not in allowed for c in columns):
                    raise AnalyticsError("invalid_spec", "Unknown aggregate export column")
                iterator = ({**row.get("group", {}), **{k: v for k, v in row.items() if k != "group"}} for row in rows)
            else:
                columns = request["columns"] or ["unique_key", "created_date", "closed_date", "complaint_type", "borough", "agency", "status", "closure_hours", "nta2020", "location"]
                def records():
                    for spec in self._record_specs(saved, selected):
                        progress("streaming")
                        source = self.backend.iter_records(spec, deadline=deadline, source_fields=columns)
                        try:
                            for row in source:
                                yield row
                        finally:
                            active_error = sys.exc_info()[0] is not None
                            if active_error:
                                job.setdefault("stopped_stage", job.get("stage", "streaming"))
                            try:
                                close_source(source)
                            except Exception:
                                if not active_error:
                                    raise
                                job["cleanup_error"] = {"code": "export_cleanup_failed", "message": "Could not close export source"}
                iterator = records()
            progress("streaming")
            with partial.open("w", encoding="utf-8-sig", newline="") as stream:
                bounded = _CsvBudgetWriter(stream, self.budgets.get("max_export_bytes", 268435456))
                writer = csv.DictWriter(bounded, fieldnames=columns)
                writer.writeheader()
                job["bytes_written"] = bounded.bytes_written
                for row in iterator:
                    if cancel.exists():
                        raise AnalyticsError("cancelled", "Export cancelled")
                    if job["rows_written"] >= self.budgets.get("max_export_rows", 1000000):
                        raise AnalyticsError("budget_exceeded", "Export row budget exceeded; no partial CSV published")
                    now = time.monotonic()
                    if now > deadline:
                        raise AnalyticsError("budget_exceeded", "Export deadline exceeded; no partial CSV published")
                    writer.writerow({c: self._csv_value(row.get(c)) for c in columns})
                    job["rows_written"] += 1
                    job["bytes_written"] = bounded.bytes_written
                    progress(now=now)
            closing, iterator = iterator, None
            close_source(closing)
            progress("verifying")
            if cancel.exists():
                raise AnalyticsError("cancelled", "Export cancelled")
            if self._identity() != saved["dataset_identity"]:
                raise AnalyticsError("partial_execution", "Dataset changed during export")
            if time.monotonic() > deadline:
                raise AnalyticsError("budget_exceeded", "Export deadline exceeded; no partial CSV published")
            if cancel.exists():
                raise AnalyticsError("cancelled", "Export cancelled")
            digest = bounded.digest.hexdigest()
            progress("publishing")
            if time.monotonic() > deadline:
                raise AnalyticsError("budget_exceeded", "Export deadline exceeded; no partial CSV published")
            if cancel.exists():
                raise AnalyticsError("cancelled", "Export cancelled")
            os.replace(partial, final)
            job.update(status="complete", complete=True, file=str(final), sha256=digest, columns=columns,
                       bytes_written=bounded.bytes_written,
                       cohort_scope=request["cohort_scope"], group_ids=request["group_ids"],
                       formula_escape="Formula-like text prefixed with apostrophe; numeric values unchanged.")
        except AnalyticsError as exc:
            fail(exc.as_dict())
        except Exception:
            fail({"code": "export_failed", "message": "Export failed; no complete artifact published"})
        finally:
            try:
                if iterator is not None:
                    close_source(iterator)
            except Exception:
                # Preserve an earlier cancellation/budget/source error; a close
                # failure must never strand its terminal status or reservation.
                cleanup = {"code": "export_cleanup_failed", "message": "Could not close export source"}
                if job["status"] in ("queued", "running", "complete"):
                    fail(cleanup)
                else:
                    job["cleanup_error"] = cleanup
            if job["status"] != "complete":
                try:
                    partial.unlink(missing_ok=True)
                except OSError:
                    job["cleanup_error"] = {"code": "io_error", "message": "Could not remove incomplete export file"}
            job["finished_at"] = datetime.now(timezone.utc).isoformat()
            try:
                progress(job["status"], force=True)
            finally:
                try:
                    cancel.unlink(missing_ok=True)
                finally:
                    from .jobs import release_export
                    release_export(self.runs, job_id)
        return self.get_result(job_id)

    def create_map_link(self, result_id, mode, cohort_scope, group_ids=None):
        from .maps import create_map_link
        saved = self._load(result_id)
        if saved["kind"] != "analysis":
            raise AnalyticsError("invalid_spec", "Map requires an analysis result")
        selected = self._selection(saved, cohort_scope, group_ids)
        return create_map_link(self, saved, mode, cohort_scope, selected)
