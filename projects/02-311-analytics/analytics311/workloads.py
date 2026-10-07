"""Bounded public samples and reproducible generated workloads, never scale claims."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from .errors import AnalyticsError
from .service import AnalyticsService, atomic_json, file_hash, read_json


_NORMALIZATION_DISK_CHECK_BYTES = 1024 * 1024


def source_manifest(source, *, sha256=None):
    """Trust adjacent provenance only when it describes these exact bytes."""
    source = Path(source)
    sidecar = source.with_suffix(".manifest.json")
    if not sidecar.exists():
        return {}
    staged = read_json(sidecar)
    if not isinstance(staged, dict) or staged.get("sha256") != (sha256 or file_hash(source)):
        raise AnalyticsError("source_changed", "Source manifest hash does not match input; reconcile before proceeding")
    return staged


def _new_output(value):
    path = Path(value).resolve()
    if (path.exists() or path.with_suffix(path.suffix + ".part").exists()
            or path.with_suffix(".manifest.json").exists()):
        raise AnalyticsError("invalid_spec", "Output already exists; choose a new filename")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_sample(start, end, output, max_records=1000):
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise AnalyticsError("invalid_spec", "Use YYYY-MM-DD source date bounds") from None
    if a >= b or type(max_records) is not int or not 1 <= max_records <= 100000:
        raise AnalyticsError("invalid_spec", "Require start < end and 1..100000 sample records")
    path = _new_output(output)
    partial = path.with_suffix(path.suffix + ".part")
    fields = "unique_key,created_date,closed_date,complaint_type,descriptor,agency,agency_name,status,borough,incident_zip,community_board,council_district,police_precinct,latitude,longitude,location"
    base_where = f"created_date >= '{a.isoformat()}T00:00:00' AND created_date < '{b.isoformat()}T00:00:00'"
    count, cursor = 0, None
    try:
        with partial.open("w", encoding="utf-8") as stream:
            while count < max_records:
                where = base_where
                if cursor:
                    created, key = [v.replace("'", "''") for v in cursor]
                    where += f" AND (created_date > '{created}' OR (created_date = '{created}' AND unique_key > '{key}'))"
                parameters = {"$select": fields, "$where": where, "$order": "created_date ASC, unique_key ASC", "$limit": min(1000, max_records - count)}
                url = "https://data.cityofnewyork.us/resource/erm2-nwe9.json?" + urlencode(parameters)
                request = Request(url, headers={"Accept": "application/json", "User-Agent": "analytics311-research/0.1"})
                with urlopen(request, timeout=30) as response:
                    raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise AnalyticsError("budget_exceeded", "Source page too large")
                rows = json.loads(raw)
                if not isinstance(rows, list):
                    raise AnalyticsError("backend_unavailable", "Source returned an unexpected response")
                if len(rows) > parameters["$limit"]:
                    raise AnalyticsError("budget_exceeded", "Source exceeded the requested sample page/record limit")
                if not rows:
                    break
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("created_date"), str) or not isinstance(row.get("unique_key"), str):
                        raise AnalyticsError("partial_execution", "Source omitted paging keys")
                    try:
                        created_date = datetime.fromisoformat(row["created_date"])
                        if (created_date.tzinfo is not None
                                or not a <= created_date.date() < b or not row["unique_key"]):
                            raise ValueError()
                    except ValueError:
                        raise AnalyticsError("partial_execution", "Source returned a sample row outside the requested date window") from None
                    next_cursor = (row["created_date"], row["unique_key"])
                    if cursor is not None and next_cursor <= cursor:
                        raise AnalyticsError("partial_execution", "Source sample keys are duplicated or not in strict paging order")
                    stream.write(json.dumps(row, allow_nan=False) + "\n")
                    count += 1
                    cursor = next_cursor
        partial.replace(path)
    except (URLError, OSError, ValueError):
        raise AnalyticsError("backend_unavailable", "Sample capture failed; partial file retained for inspection, not marked complete") from None
    output_digest = file_hash(path)
    manifest = {"dataset_version": "sample-" + output_digest[:12], "kind": "public_sample", "source_dataset": "erm2-nwe9",
                "source": "https://data.cityofnewyork.us/resource/erm2-nwe9.json", "row_count": count,
                "sha256": output_digest, "captured_at": datetime.now(timezone.utc).isoformat(),
                "source_date_bounds": {"gte": start, "lt": end}, "coverage": {"complete": False},
                "warnings": ["Bounded mutable-source sample; not a random sample, complete snapshot, or citywide trend baseline."]}
    atomic_json(path.with_suffix(".manifest.json"), manifest)
    return {"file": str(path), "manifest": str(path.with_suffix(".manifest.json")), **manifest}


def generate(output, records=10000, seed=7):
    if type(records) is not int or not 1 <= records <= 1000000000 or type(seed) is not int:
        raise AnalyticsError("invalid_spec", "records must be 1..1000000000; seed must be an integer")
    path = _new_output(output)
    # Reserve conservatively before writing; still report actual bytes afterward.
    if records * 1200 > shutil.disk_usage(path.parent).free * 0.8:
        raise AnalyticsError("budget_exceeded", "Estimated corpus exceeds available disk budget; use smaller workload or larger storage")
    rng = random.Random(seed)
    partial = path.with_suffix(path.suffix + ".part")
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    counts = Counter()
    begin = time.perf_counter()
    with partial.open("w", encoding="utf-8") as stream:
        for number in range(records):
            borough = rng.choices(["BROOKLYN", "MANHATTAN", "QUEENS", "BRONX", "STATEN ISLAND"], [35, 25, 20, 15, 5])[0]
            problem = rng.choices(["Noise - Residential", "Rodent", "Dirty Conditions"], [60, 25, 15])[0]
            created = start + timedelta(seconds=rng.randrange(365 * 86400))
            closed = rng.random() < .8
            hours = round(rng.expovariate(1 / 30), 4) if closed else None
            record = {"unique_key": f"SIM-{seed}-{number:012d}", "created_date": created.isoformat(),
                      "complaint_type": problem, "borough": borough, "agency": "SYNTHETIC-" + str(rng.randrange(4)),
                      "status": "Closed" if closed else "Open", "is_closed": closed,
                      "nta2020": "SIM-NTA-" + str(rng.randrange(100)), "source_kind": "generated"}
            if closed:
                record.update(closed_date=(created + timedelta(hours=hours)).isoformat(), closure_hours=hours)
            if rng.random() > .03:
                record["location"] = {"lat": round(40.72 + rng.gauss(0, .045), 6), "lon": round(-73.95 + rng.gauss(0, .04), 6)}
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            counts[problem] += 1
    partial.replace(path)
    manifest = {"dataset_version": f"generated-{seed}-{records}", "kind": "generated_workload", "source": "seeded synthetic generator; not NYC findings",
                "seed": seed, "row_count": records, "sha256": file_hash(path), "bytes": path.stat().st_size,
                "coverage": {"gte": "2025-01-01T00:00:00+00:00", "lt": "2026-01-01T00:00:00+00:00", "complete": True},
                "generation_seconds": round(time.perf_counter() - begin, 6), "category_counts": dict(counts),
                "warnings": ["Complete coverage refers to this generated corpus only.", "Synthetic NTA labels are not geographic enrichment.", "Generation is not an Elasticsearch throughput or scale benchmark."]}
    atomic_json(path.with_suffix(".manifest.json"), manifest)
    return {"file": str(path), "manifest": str(path.with_suffix(".manifest.json")), **manifest}


def normalize_file(source, output, boundaries=None, *, max_output_bytes=8 * 1024 ** 3,
                   min_free_bytes=1_000_000_000):
    from .ingest import normalize_record
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 10 ** 15:
        raise AnalyticsError("invalid_spec", "Normalization max_output_bytes must be an integer in 1..1000000000000000")
    if type(min_free_bytes) is not int or not 0 <= min_free_bytes <= 10 ** 15:
        raise AnalyticsError("invalid_spec", "Normalization min_free_bytes must be an integer in 0..1000000000000000")
    path = _new_output(output)
    partial = path.with_suffix(path.suffix + ".part")
    free_bytes = shutil.disk_usage(path.parent).free
    if free_bytes < min_free_bytes:
        raise AnalyticsError("budget_exceeded", "Normalization cannot preserve min_free_bytes; choose suitable storage before retrying")
    source_digest = file_hash(source)
    staged = source_manifest(source, sha256=source_digest)
    if staged and staged["sha256"] != source_digest:
        raise AnalyticsError("source_changed", "Source changed after provenance validation; normalization not started")
    enricher = None
    if boundaries:
        from .geography import NtaEnricher
        enricher = NtaEnricher(boundaries)
    counts = Counter()
    read_digest = hashlib.sha256()
    output_bytes, disk_checked_at = 0, 0
    with open(source, "rb") as source_stream, partial.open("xb") as target:
        while True:
            line = source_stream.readline(10 * 1024 * 1024 + 1)
            if not line:
                break
            if len(line) > 10 * 1024 * 1024:
                raise AnalyticsError("budget_exceeded", "Source JSONL line exceeds the 10 MiB normalization limit")
            read_digest.update(line)
            if not line.strip():
                continue
            try:
                row = normalize_record(json.loads(line.decode("utf-8-sig")))
                if enricher:
                    row = enricher.enrich(row)
                encoded = (json.dumps(row, allow_nan=False) + "\n").encode("utf-8")
                if output_bytes + len(encoded) > max_output_bytes:
                    raise AnalyticsError("budget_exceeded", "Normalization exceeds max_output_bytes; partial retained. Resolve the budget and choose a new output; normalization does not resume partial files")
                # Refresh before a row crosses the 1 MiB observation interval,
                # including rows larger than that interval. Deduct unobserved
                # writes; other processes can still consume disk concurrently.
                unobserved = output_bytes - disk_checked_at
                if (unobserved + len(encoded) > _NORMALIZATION_DISK_CHECK_BYTES
                        or free_bytes - unobserved - len(encoded) < min_free_bytes):
                    target.flush()
                    free_bytes = shutil.disk_usage(path.parent).free
                    disk_checked_at = output_bytes
                    unobserved = 0
                if free_bytes - unobserved - len(encoded) < min_free_bytes:
                    raise AnalyticsError("budget_exceeded", "Normalization cannot preserve min_free_bytes; partial retained. Resolve storage and choose a new output; normalization does not resume partial files")
                for flag in row.get("quality_flags", []):
                    counts[flag] += 1
                target.write(encoded)
                output_bytes += len(encoded)
                counts["written"] += 1
            except AnalyticsError as exc:
                if exc.code != "invalid_record":
                    raise
                counts["rejected"] += 1
            except ValueError:
                counts["invalid_json"] += 1
        target.flush()
    if read_digest.hexdigest() != source_digest or file_hash(source) != source_digest:
        raise AnalyticsError("source_changed", "Input changed during normalization; partial output is not publishable")
    if shutil.disk_usage(path.parent).free < min_free_bytes:
        raise AnalyticsError("budget_exceeded", "Normalization storage reserve exhausted before publication; partial retained. Resolve storage and choose a new output; normalization does not resume partial files")
    partial.replace(path)
    output_digest = file_hash(path)
    manifest = {"dataset_version": "normalized-" + output_digest[:12], "kind": "normalized_sample", "source": Path(source).name,
                "source_sha256": source_digest, "sha256": output_digest, "row_count": counts["written"], "bytes": output_bytes,
                "normalization_limits": {"max_output_bytes": max_output_bytes, "min_free_bytes": min_free_bytes},
                "quality_counts": dict(counts), "coverage": {"complete": False},
                "warnings": ["Normalization does not establish complete source coverage."]}
    if staged:
        manifest["provenance"] = staged
        manifest["kind"] = staged.get("kind", "normalized_sample")
        unmapped_creation = sum(counts.get(f"{flag}_created_date", 0) for flag in ("missing", "invalid", "ambiguous", "nonexistent"))
        if staged.get("coverage", {}).get("complete") is True and not counts["rejected"] and not counts["invalid_json"] and not unmapped_creation and staged.get("row_count") == counts["written"]:
            manifest["coverage"] = staged["coverage"]
        if unmapped_creation:
            manifest["warnings"].append(f"{unmapped_creation} requests have no usable creation timestamp; complete temporal coverage cannot be certified.")
        manifest["warnings"] += staged.get("warnings", [])
    if enricher:
        manifest["geography"] = {"nta_version": enricher.boundary_sha256}
    atomic_json(path.with_suffix(".manifest.json"), manifest)
    return {"file": str(path), "manifest": str(path.with_suffix(".manifest.json")), **manifest}


def benchmark(config_path, spec, repeats=3):
    if type(repeats) is not int or not 1 <= repeats <= 100:
        raise AnalyticsError("invalid_spec", "repeats must be 1..100")
    service = AnalyticsService(config_path)
    results, elapsed = [], []
    for _ in range(repeats):
        begin = time.perf_counter()
        result = service.run_analysis(spec)
        elapsed.append(time.perf_counter() - begin)
        results.append({"result_id": result["result_id"], "total": result["total"], "group_count": result["group_count"]})
    ordered = sorted(elapsed)
    return {"backend": service.config["backend"], "dataset_version": service.manifest["dataset_version"],
            "dataset_rows": service.manifest.get("row_count"), "runs": results, "seconds": elapsed,
            "median_seconds": statistics.median(elapsed), "max_seconds": max(elapsed),
            "evidence_level": "fixture_only" if service.config["backend"] == "fixture" else "measured_elasticsearch_queries",
            "warnings": ["Tool execution only; no LLM latency or accuracy measured.", "No billion-record extrapolation. Cache states were not controlled.", "A small run count cannot characterize tail latency reliably."]}
