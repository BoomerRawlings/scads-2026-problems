"""Explicit live API/CSV checks; never a full-project or visual acceptance claim.

Run only against a provisioned Elasticsearch profile. No service is installed or
started by this runner. Tests replace all service/transport calls with fakes.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time
from urllib.parse import urlsplit

from analytics311.errors import AnalyticsError
from analytics311.service import AnalyticsService, atomic_json, canonical, read_json


def _manifest_summary(manifest, depth=0):
    """Retain numerical/source identity evidence, not filenames or endpoint URLs."""
    fields = ("dataset_version", "kind", "source_kind", "source_dataset", "index", "index_uuid", "row_count",
              "immutable", "sha256", "source_sha256", "seed", "coverage", "geography", "quality_counts")
    summary = {key: manifest[key] for key in fields if key in manifest}
    if isinstance(manifest.get("ingestion"), dict):
        keys = ("source_sha256", "index_uuid", "processed_rows", "source_lines", "quality_counts", "complete", "normalized_input")
        summary["ingestion"] = {key: manifest["ingestion"][key] for key in keys if key in manifest["ingestion"]}
    if depth < 4 and isinstance(manifest.get("provenance"), dict):
        summary["provenance"] = _manifest_summary(manifest["provenance"], depth + 1)
    return summary


def _inspect_csv(job):
    """Count parsed records independently and hash bytes with bounded memory."""
    filename = job.get("file")
    if not isinstance(filename, str):
        raise AnalyticsError("acceptance_failed", "Completed export omitted its artifact file.")
    path = Path(filename)
    before = path.stat()
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if not reader.fieldnames or reader.fieldnames != job.get("columns"):
            raise AnalyticsError("acceptance_failed", "CSV headers differ from the export's declared columns.")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise AnalyticsError("acceptance_failed", "CSV has inconsistent column counts.")
            count += 1
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise AnalyticsError("acceptance_failed", "Export file changed during independent verification.")
    return {"row_count": count, "sha256": digest.hexdigest(), "bytes": after.st_size,
            "columns": reader.fieldnames}


def run_acceptance(config_path, spec_path, output_path, *, map_mode=None, timeout_seconds=120, poll_interval=0.25):
    """Return and save one bounded evidence report. Only Elastic profiles allowed."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise AnalyticsError("invalid_spec", "Export polling timeout must be 1..120 seconds.")
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or not 0 < poll_interval <= 5:
        raise AnalyticsError("invalid_spec", "Polling interval must be positive and at most five seconds.")
    if map_mode not in {None, "requests", "neighborhood_trends"}:
        raise AnalyticsError("invalid_spec", "Map mode must be requests or neighborhood_trends.")
    config = read_json(config_path)
    if not isinstance(config, dict) or config.get("backend") != "elastic":
        raise AnalyticsError("unsupported_operation", "Live acceptance requires an Elasticsearch profile; fixtures are not live evidence.")
    output_path = Path(output_path)
    if output_path.exists():
        raise AnalyticsError("invalid_spec", "Evidence output already exists; choose a new filename.")
    spec = read_json(spec_path)
    begin = time.monotonic()
    evidence = {
        "runner_version": "1", "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Elasticsearch API execution and CSV count/checksum checks only",
        "passed": False, "overall_release_verified": False, "visual_parity_verified": False,
        "checks": {}, "runner_environment": {"python": platform.python_version(), "os": platform.system(),
                                             "architecture": platform.machine(), "logical_cpus": os.cpu_count()},
        "limitations": ["Counts/checksums do not establish independent query semantics or exact record membership.",
                        "Map rendering, boundary joins and visual parity remain unverified.",
                        "No agent evaluation, throughput, hardware capacity, or overall release claim.",
                        "Runner environment describes this client; server hardware/topology is not inferred."],
    }
    stage = "service_initialization"
    service = None
    job = None
    try:
        service = AnalyticsService(config_path)
        evidence["manifest"] = _manifest_summary(service.manifest)
        evidence["manifest_sha256"] = hashlib.sha256(canonical(service.manifest).encode("utf-8")).hexdigest()
        stage = "server_version"
        server = service.backend.client.request("GET", "/")
        version = server.get("version", {})
        if not isinstance(version, dict) or not isinstance(version.get("number"), str) or not version["number"]:
            raise AnalyticsError("acceptance_failed", "Elasticsearch root API omitted its version.")
        evidence["elasticsearch"] = {key: version[key] for key in ("number", "build_flavor", "build_type", "lucene_version") if key in version}
        stage = "validation"
        validated = service.validate_analysis(spec)
        evidence["normalized_spec"] = validated["normalized_spec"]
        evidence["coverage_complete"] = validated.get("coverage_complete", False)
        evidence["checks"]["validation_passed"] = True
        stage = "analysis"
        result = service.run_analysis(spec)
        total = result.get("total", {})
        if (result.get("execution_complete") is not True or total.get("relation") != "eq"
                or type(total.get("value")) is not int or total["value"] < 0
                or result.get("evidence_level") != "elastic_execution"):
            raise AnalyticsError("acceptance_failed", "Analysis did not provide complete, exact Elasticsearch evidence.")
        evidence["analysis"] = {"result_id": result["result_id"], "total": total, "group_count": result.get("group_count"),
                                "approximate": result.get("approximate", False), "elapsed_seconds": result.get("elapsed_seconds")}
        evidence["checks"]["api_execution_complete"] = True
        evidence["checks"]["source_cohort_count_exact"] = True
        stage = "export"
        job = service.export_csv(result["result_id"], "records", "all_matching")
        evidence["export_job"] = {key: job[key] for key in ("job_id", "status", "complete", "rows_written", "cohort_scope") if key in job}
        deadline = time.monotonic() + timeout_seconds
        while job.get("status") in {"queued", "running"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    service.cancel_export(job["job_id"])
                    evidence["export_cancellation_requested"] = True
                except Exception:
                    evidence["export_cancellation_requested"] = False
                raise AnalyticsError("acceptance_timeout", "Export did not finish within the polling budget; cancellation requested where possible.")
            time.sleep(min(poll_interval, remaining))
            job = service.get_result(job["job_id"])
            evidence["export_job"] = {key: job[key] for key in ("job_id", "status", "complete", "rows_written", "cohort_scope") if key in job}
        evidence["export_job"] = {key: job[key] for key in ("job_id", "status", "complete", "rows_written", "cohort_scope") if key in job}
        if job.get("status") != "complete" or job.get("complete") is not True or job.get("cohort_scope") != "all_matching":
            raise AnalyticsError("acceptance_failed", "The all-matching record export did not complete.")
        evidence["checks"]["export_job_complete"] = True
        stage = "csv_verification"
        observed = _inspect_csv(job)
        evidence["csv"] = observed
        evidence["csv"]["cohort_scope"] = "all_matching"
        evidence["csv"]["count_semantics"] = "Original source cohort before displayed group thresholds; comparisons include both nonoverlapping periods."
        evidence["checks"]["csv_count_matches_job"] = observed["row_count"] == job.get("rows_written")
        evidence["checks"]["csv_count_matches_source_cohort"] = observed["row_count"] == total["value"]
        evidence["checks"]["csv_sha256_matches_job"] = observed["sha256"] == job.get("sha256")
        if not all(evidence["checks"].values()):
            raise AnalyticsError("acceptance_failed", "Independent CSV count or checksum differs from recorded execution evidence.")
        if map_mode is not None:
            stage = "map_link"
            mapped = service.create_map_link(result["result_id"], map_mode, "all_matching")
            url = mapped.get("url", "")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
                raise AnalyticsError("acceptance_failed", "Map API did not return a usable credential-free link.")
            evidence["map"] = {"mode": map_mode, "url": url, "visual_parity_verified": False,
                               **{key: mapped[key] for key in ("source_count", "mapped_count", "missing_location_count",
                                  "published_group_count", "excluded_group_count", "nta_version") if key in mapped}}
            evidence["checks"]["map_link_created"] = True
        evidence["passed"] = True
    except AnalyticsError as exc:
        # Do not persist endpoint details, filenames, arbitrary source text, or
        # server error bodies. The failing stage and stable code are sufficient.
        evidence["error"] = {"stage": stage, "code": exc.code}
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        evidence["error"] = {"stage": stage, "code": "acceptance_failed"}
    finally:
        evidence["elapsed_seconds"] = round(time.monotonic() - begin, 6)
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(output_path, evidence)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Provisioned Elasticsearch profile")
    parser.add_argument("--spec", required=True, help="AnalysisSpec JSON")
    parser.add_argument("--output", required=True, help="New evidence JSON file")
    parser.add_argument("--map", choices=("requests", "neighborhood_trends"), dest="map_mode")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="Export polling limit, 1..120 seconds")
    args = parser.parse_args(argv)
    try:
        evidence = run_acceptance(args.config, args.spec, args.output, map_mode=args.map_mode, timeout_seconds=args.timeout_seconds)
    except AnalyticsError as exc:
        print(json.dumps({"error": exc.as_dict()}))
        return 2
    print(json.dumps({"passed": evidence["passed"], "scope": evidence["scope"],
                      "overall_release_verified": False, "visual_parity_verified": False,
                      "checks": evidence["checks"], "error": evidence.get("error")}, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
