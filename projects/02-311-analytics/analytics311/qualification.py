"""Qualify comparisons inside a reconciled observed corpus, never city coverage.

These functions validate provenance after callers verify the actual artifact bytes.
Certificates are reproducible integrity records, not signatures or provider promises.
"""

from datetime import datetime
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from .errors import AnalyticsError


SCOPE = "reconciled_observed_snapshot"
WARNING = ("Comparisons describe the reconciled observed public-data snapshot only; "
           "provider transaction isolation and complete citywide reporting are not established. "
           "Complaint growth is reporting growth, not proof that underlying conditions worsened.")
_CREATION_FLAGS = tuple(f"{flag}_created_date" for flag in ("missing", "invalid", "ambiguous", "nonexistent"))


def _fail(message):
    raise AnalyticsError("qualification_failed", message)


def _hash(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        _fail("Qualification evidence must be finite JSON data.")
    return hashlib.sha256(raw.encode()).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _count(value):
    return type(value) is int and value >= 0


def _bounds(value):
    try:
        dates = [datetime.fromisoformat(value[key].replace("Z", "+00:00")) for key in ("gte", "lt")]
        if any(date.tzinfo is None or date.utcoffset() is None for date in dates) or dates[0] >= dates[1]:
            raise ValueError()
        return dates
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        _fail("Comparison bounds must be ordered, offset-aware timestamps.")


def _quality(quality, rows, *, normalization=False):
    if not isinstance(quality, dict) or any(not _count(value) for value in quality.values()):
        _fail("Quality counters must be nonnegative integers.")
    if any(quality.get(flag, 0) for flag in _CREATION_FLAGS + ("rejected", "invalid_json")):
        _fail("Dropped records or unusable creation timestamps prevent observed-window qualification.")
    if normalization and quality.get("written") != rows:
        _fail("Normalization's written count must equal the captured count.")


def _seal(certificate):
    return {**certificate, "qualification_sha256": _hash(certificate)}


def qualify_normalized_capture(capture_manifest, normalized_manifest):
    """Return a certificate only for a lossless, hash-linked complete observation.

    The normalization caller must first hash/recheck its input and published output.
    Samples, hand-written coverage flags and incomplete/DST-ambiguous cohorts fail.
    """
    capture, normalized = capture_manifest, normalized_manifest
    if not isinstance(capture, dict) or not isinstance(normalized, dict):
        _fail("Qualification needs capture and normalization manifests.")
    if (capture.get("kind") != "reconciled_public_capture" or capture.get("source_kind") != "real_public_records"
            or capture.get("source_dataset") != "erm2-nwe9"
            or capture.get("source") != "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
            or capture.get("observed_complete") is not True or capture.get("extraction_complete") is not True
            or capture.get("transactional_source_snapshot") is not False):
        _fail("Only the reconciled official capture adapter can qualify an observed corpus.")
    if (not _sha(capture.get("sha256")) or not _sha(normalized.get("sha256"))
            or normalized.get("source_sha256") != capture["sha256"] or normalized.get("provenance") != capture):
        _fail("Raw and normalized artifact hashes/provenance must form one exact chain.")
    rows = capture.get("row_count")
    if (not all(_count(value) for value in (rows, capture.get("unique_key_count"), normalized.get("row_count")))
            or capture.get("unique_key_count") != rows or normalized.get("row_count") != rows):
        _fail("Captured, distinct and normalized counts must reconcile.")
    for value in (capture.get("bytes"), normalized.get("bytes")):
        if not _count(value):
            _fail("Artifact byte counts must be recorded.")
    coverage = capture.get("coverage", {})
    if not isinstance(coverage, dict) or coverage.get("complete") is not False or coverage.get("observed_complete") is not True:
        _fail("Observed corpus qualification must not assert complete source coverage.")
    start, end = _bounds(coverage)
    try:
        source_bounds = capture["source_date_bounds"]
        local_dates = [datetime.fromisoformat(source_bounds[key]) for key in ("gte", "lt")]
        if any(value.tzinfo is not None or value.time().isoformat() != "00:00:00" for value in local_dates):
            raise ValueError()
        expected = [value.replace(tzinfo=ZoneInfo("America/New_York")) for value in local_dates]
        if [start, end] != expected:
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        _fail("Capture bounds must match the complete NYC-local calendar window.")
    reconciliation = capture.get("reconciliation", {})
    if not isinstance(reconciliation, dict):
        _fail("Source reconciliation is missing.")
    initial, final = reconciliation.get("initial_count"), reconciliation.get("final_count")
    initial_metadata, final_metadata = reconciliation.get("initial_metadata"), reconciliation.get("final_metadata")
    if (not isinstance(initial, dict) or initial != final
            or not all(_count(initial.get(key)) for key in ("row_count", "unique_count"))
            or initial.get("row_count") != rows or initial.get("unique_count") != rows
            or not isinstance(initial_metadata, dict) or initial_metadata != final_metadata
            or initial_metadata.get("id") != "erm2-nwe9"
            or not _sha(initial_metadata.get("schema_sha256"))
            or initial.get("max_updated_at") != reconciliation.get("captured_max_updated_at")):
        _fail("Source before/after metadata, counts and captured update observations must reconcile.")
    revisions = initial.get("revision_headers")
    if (not isinstance(revisions, dict) or set(revisions) != {"x-soda2-truth-last-modified", "x-soda2-secondary-last-modified"}
            or not all(isinstance(value, str) and value for value in revisions.values()) or len(set(revisions.values())) != 1):
        _fail("Capture needs matching source revision observations; these are not snapshot tokens.")
    _quality(normalized.get("quality_counts"), rows, normalization=True)
    if not isinstance(normalized.get("coverage"), dict) or normalized["coverage"].get("complete") is not False:
        _fail("Normalized observed corpus must preserve coverage.complete=false.")
    return _seal({"version": 1, "stage": "normalized", "scope": SCOPE,
                  "gte": coverage["gte"], "lt": coverage["lt"], "row_count": rows,
                  "capture_sha256": capture["sha256"], "capture_manifest_sha256": _hash(capture),
                  "normalized_sha256": normalized["sha256"], "transactional_source_snapshot": False,
                  "population_complete": False, "warning": WARNING})


def qualify_frozen_index(staged_manifest, ingestion, snapshot, bounds):
    """Bind normalized qualification to completed ingestion and exact frozen count.

    The caller must use freeze_index(expected_count=staged_manifest['row_count'])
    before publication. A requested subwindow must remain inside the capture.
    """
    if not all(isinstance(value, dict) for value in (staged_manifest, ingestion, snapshot, bounds)):
        _fail("Frozen qualification needs staged, ingestion, snapshot and bounds records.")
    certificate = qualify_normalized_capture(staged_manifest.get("provenance"), staged_manifest)
    if staged_manifest.get("comparison_qualification") != certificate:
        _fail("Staged comparison qualification is absent or changed.")
    rows = certificate["row_count"]
    if (ingestion.get("complete") is not True or ingestion.get("normalized_input") is not True
            or ingestion.get("quarantined") is not False
            or ingestion.get("source_sha256") != certificate["normalized_sha256"]
            or not _count(ingestion.get("processed_rows")) or not _count(snapshot.get("row_count"))
            or ingestion.get("processed_rows") != rows or snapshot.get("row_count") != rows
            or snapshot.get("immutable") is not True
            or not isinstance(snapshot.get("index"), str) or not snapshot["index"]
            or not isinstance(snapshot.get("index_uuid"), str) or not snapshot["index_uuid"]
            or ingestion.get("index") != snapshot["index"] or ingestion.get("index_uuid") != snapshot["index_uuid"]):
        _fail("Completed ingestion and immutable index must match qualified bytes, identity and exact counts.")
    _quality(ingestion.get("quality_counts"), rows)
    start, end = _bounds(bounds)
    first, last = _bounds(certificate)
    if not first <= start < end <= last or bounds.get("complete") is not False:
        _fail("Frozen observed scope must stay inside the captured window and keep complete=false.")
    certificate.pop("qualification_sha256")
    certificate.update(stage="frozen_index", gte=bounds["gte"], lt=bounds["lt"],
                       index=snapshot["index"], index_uuid=snapshot["index_uuid"])
    return _seal(certificate)


def comparison_qualification(manifest):
    """Validate attached qualification; absent certificates remain unqualified."""
    if not isinstance(manifest, dict):
        _fail("Expected a manifest object.")
    attached = manifest.get("comparison_qualification")
    if attached is None:
        return None
    if not isinstance(attached, dict):
        _fail("Comparison qualification must be an object.")
    if attached.get("stage") == "normalized":
        expected = qualify_normalized_capture(manifest.get("provenance"), manifest)
    elif attached.get("stage") == "frozen_index":
        expected = qualify_frozen_index(manifest.get("provenance"), manifest.get("ingestion"),
                                        manifest, manifest.get("coverage"))
    else:
        _fail("Unsupported comparison qualification stage.")
    if attached != expected:
        _fail("Comparison qualification no longer matches its artifact/index provenance.")
    return attached.copy()
