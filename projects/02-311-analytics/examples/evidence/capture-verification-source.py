"""Read-only streaming source verification; writes only small evidence receipts."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "data/real-capture-2025"
OUTPUT = ROOT / "examples/evidence/captured-local-verification.json"
CANONICAL = ROOT / "examples/evidence/captured-manifest.json"
EXPECTED = (2133268, 1306911416, "91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7")
BEGIN = time.monotonic()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded():
    require(time.monotonic() - BEGIN < 900, "verification exceeded 900-second bound")
    require(shutil.disk_usage(DIRECTORY).free >= 2_000_000_000, "2 GB free reserve exhausted")


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            bounded()
            digest.update(block)
    return digest.hexdigest()


require(not OUTPUT.exists() and not CANONICAL.exists(), "receipt already exists; refusing overwrite")
bounded()
gzip_paths = list(DIRECTORY.rglob("*.jsonl.gz"))
manifest_paths = list(DIRECTORY.rglob("*.manifest.json"))
require(len(gzip_paths) == len(manifest_paths) == 1, "expected exactly one gzip and manifest")
compressed, manifest_path = gzip_paths[0], manifest_paths[0]
require(manifest_path.stat().st_size < 65536, "oversized manifest")
manifest = json.loads(manifest_path.read_bytes())
bootstrap = json.loads((ROOT / "runs/real-bootstrap37700939902/capture.manifest.json").read_bytes())
require(manifest == bootstrap, "capture and acceptance manifests disagree")
require(manifest["kind"] == "reconciled_public_capture" and manifest["source_kind"] == "real_public_records", "wrong provenance")
require(manifest["source_dataset"] == "erm2-nwe9" and manifest["source"] == "https://data.cityofnewyork.us/resource/erm2-nwe9.json", "wrong source")
require((manifest["row_count"], manifest["bytes"], manifest["sha256"]) == EXPECTED, "manifest differs from pinned capture")
require(manifest["unique_key_count"] == EXPECTED[0], "unique count differs")
require(manifest["observed_complete"] is True and manifest["extraction_complete"] is True, "capture incomplete")
require(manifest["coverage"]["complete"] is False and manifest["transactional_source_snapshot"] is False, "coverage overstated")
reconciliation = manifest["reconciliation"]
require(reconciliation["initial_count"] == reconciliation["final_count"], "source counts/revisions changed")
require(reconciliation["initial_metadata"] == reconciliation["final_metadata"], "source metadata changed")
require(reconciliation["final_count"]["row_count"] == reconciliation["final_count"]["unique_count"] == EXPECTED[0], "source count mismatch")
revisions = reconciliation["final_count"]["revision_headers"]
require(revisions["x-soda2-secondary-last-modified"] == revisions["x-soda2-truth-last-modified"], "replica/truth revisions differ")
start, end = (datetime.fromisoformat(manifest["source_date_bounds"][key]) for key in ("gte", "lt"))
raw_hash, count, size, previous = hashlib.sha256(), 0, 0, None
minimum_created, maximum_created, maximum_updated = None, None, None
before_stat = compressed.stat()
compressed_sha = hash_file(compressed)
with gzip.open(compressed, "rb") as stream:
    while True:
        line = stream.readline(1024 * 1024 + 1)
        if not line:
            break
        require(len(line) <= 1024 * 1024 and line.endswith(b"\n"), "oversized or partial record")
        row = json.loads(line)
        require(isinstance(row, dict), "record is not an object")
        key = row.get("unique_key")
        require(isinstance(key, str) and re.fullmatch(r"[0-9]{1,512}", key), "invalid unique key")
        require(previous is None or key > previous, "duplicate/out-of-order key")
        previous = key
        created = datetime.fromisoformat(row["created_date"])
        require(created.tzinfo is None and start <= created < end, "record outside captured window")
        updated = datetime.fromisoformat(row["source_updated_at"].replace("Z", "+00:00"))
        require(updated.tzinfo is not None, "row update has no timezone")
        updated = updated.astimezone(timezone.utc)
        minimum_created = min(minimum_created, created) if minimum_created else created
        maximum_created = max(maximum_created, created) if maximum_created else created
        maximum_updated = max(maximum_updated, updated) if maximum_updated else updated
        raw_hash.update(line)
        count += 1
        size += len(line)
        require(count <= EXPECTED[0] and size <= EXPECTED[1], "raw capture exceeds bounds")
        if count % 100000 == 0:
            bounded()
            print(json.dumps({"verified_rows": count, "elapsed_seconds": round(time.monotonic()-BEGIN, 3)}), flush=True)
after_stat = compressed.stat()
require((before_stat.st_size, before_stat.st_mtime_ns) == (after_stat.st_size, after_stat.st_mtime_ns), "gzip changed")
require(hash_file(compressed) == compressed_sha, "gzip bytes changed")
require((count, size, raw_hash.hexdigest()) == EXPECTED, "raw count/bytes/hash mismatch")
require(maximum_updated.isoformat(timespec="microseconds") == reconciliation["captured_max_updated_at"], "maximum row update mismatch")
canonical = (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
receipt = {
    "evidence_kind": "executed_streaming_verification_of_actual_public_capture",
    "verified_at": datetime.now(timezone.utc).isoformat(),
    "github_run": 37700939902,
    "github_run_url": "https://github.com/BoomerRawlings/scads-2026-problems/actions/runs/37700939902",
    "capture_artifact": {"id": 11518891296, "name": "analytics311-real-capture", "reported_archive_bytes": 163699736,
        "reported_archive_sha256": "6ba89218d3f7217add43bbc1b31455074afe472ec88cc1646d7e523de3e5861c", "archive_digest_locally_recomputed": False},
    "acceptance_artifact": {"id": 11517909664, "name": "analytics311-real-acceptance", "reported_archive_bytes": 96594},
    "dataset_version": manifest["dataset_version"],
    "compressed": {"path": compressed.relative_to(ROOT).as_posix(), "bytes": before_stat.st_size, "sha256": compressed_sha},
    "raw": {"bytes": size, "sha256": raw_hash.hexdigest(), "row_count": count, "unique_key_count": count,
        "strict_unique_key_order_verified": True, "uniqueness_method": "strict ascending decimal-text unique_key; one previous key, no full set"},
    "created_date_bounds_verified": manifest["source_date_bounds"],
    "observed_min_created_date": minimum_created.isoformat(), "observed_max_created_date": maximum_created.isoformat(),
    "observed_max_updated_at": maximum_updated.isoformat(timespec="microseconds"), "capture_pages": reconciliation["pages"],
    "source_reconciliation_checked_against_capture_manifest": True, "source_requeried_during_local_verification": False,
    "manifest": {"downloaded_path": manifest_path.relative_to(ROOT).as_posix(), "downloaded_sha256": hash_file(manifest_path),
        "canonical_path": CANONICAL.relative_to(ROOT).as_posix(), "canonical_sha256": hashlib.sha256(canonical).hexdigest(), "matches_acceptance_artifact": True},
    "local_verification": {"elapsed_seconds": round(time.monotonic()-BEGIN, 3), "raw_file_materialized": False,
        "maximum_record_buffer_bytes": 1048577, "full_id_set_materialized": False, "minimum_free_disk_bytes_required": 2000000000,
        "free_disk_bytes_at_completion": shutil.disk_usage(DIRECTORY).free,
        "script": Path(__file__).relative_to(ROOT).as_posix(), "script_sha256": hash_file(Path(__file__))},
    "observed_complete": True, "transactional_source_snapshot": False, "population_complete": False,
    "acceptance": {"actual_capture_at_least_two_million": True, "normalized_count_reconciled": False,
        "frozen_index_count_reconciled": False, "actual_agent_120_trials_verified": False, "live_real_maps_verified": False, "real_data_performance_verified": False}
}
bounded()
with CANONICAL.open("xb") as stream:
    stream.write(canonical)
with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
    stream.write("\n")
print(json.dumps(receipt, indent=2), flush=True)
