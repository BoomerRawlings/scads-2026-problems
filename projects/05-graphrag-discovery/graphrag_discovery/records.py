"""Strict, dependency-free contracts for the authored-fixture prototype.

Offsets are Unicode code points. Hashes cover exact UTF-8 text; this first
adapter deliberately supports only lossless plain text, not a real extractor.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any


MAX_REQUEST_BYTES = 1_048_576
MAX_TEXT_CHARS = 250_000
MAX_CONTEXT_BYTES = 65_536
ID_PATTERN = r"[A-Za-z0-9_.:-]{1,128}"
_ID = re.compile(ID_PATTERN)
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)
_JSON_FIELDS = {"metadata", "context", "qualifiers", "provenance_map"}
_COMMON_FIELDS = {
    "schema_version", "corpus_id", "event_id", "document_id", "version_id",
    "operation", "source_uri", "source_version_ref", "source_available_at",
    "source_event_at", "language", "rights_ref", "access_scope",
    "source_timezone", "reference_time", "time_precision", *_JSON_FIELDS,
}
_UPSERT_FIELDS = {
    *_COMMON_FIELDS, "processing_version", "text", "content_sha256",
    "source_sha256", "supersedes_version_id",
}
_WITHDRAW_FIELDS = {*_COMMON_FIELDS, "reason"}
_ASSERTION_FIELDS = {
    "schema_version", "corpus_id", "assertion_id", "document_id", "version_id",
    "processing_version", "subject_id", "subject_label", "object_id",
    "object_label", "text", "start", "end", "modality", "valid_from",
    "valid_to", "temporal_status", "supersedes", "method", "relation_group",
    "metadata", "context", "qualifiers",
}


class DomainError(ValueError):
    """A stable machine-readable failure, without including source text."""

    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def utc(value: str) -> str:
    """Normalize an explicit ISO instant to UTC, preserving microseconds.

    Accept seconds, optional 1–6 fractional digits, and Z or ±HH:MM. Reject
    naive/date-only values, excess precision, and RFC3339's unknown -00:00.
    """
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise DomainError("invalid_timestamp", "Expected a timezone-aware ISO timestamp.")
    if value.endswith("-00:00"):
        raise DomainError("invalid_timestamp", "Unknown timezone offset is not an instant.")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError) as exc:
        raise DomainError("invalid_timestamp", "Invalid calendar date or timezone offset.") from exc


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_check(value: Any, depth: int = 0, *, bounded: bool = False) -> None:
    if depth > (8 if bounded else 32):
        raise DomainError("invalid_json", "JSON nesting limit exceeded.")
    if value is None or type(value) in (bool, int):
        return
    if isinstance(value, str):
        if bounded and len(value) > 16_384:
            raise DomainError("invalid_json", "JSON string limit exceeded.")
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        if bounded and len(value) > 128:
            raise DomainError("invalid_json", "JSON array limit exceeded.")
        for item in value:
            _json_check(item, depth + 1, bounded=bounded)
        return
    if type(value) is dict:
        if bounded and len(value) > 64:
            raise DomainError("invalid_json", "JSON object limit exceeded.")
        for key, item in value.items():
            if not isinstance(key, str) or (bounded and len(key) > 128):
                raise DomainError("invalid_json", "JSON object keys must be bounded strings.")
            _json_check(item, depth + 1, bounded=bounded)
        return
    raise DomainError("invalid_json", "Expected finite JSON values.")


def _json_bytes(value: Any) -> bytes:
    _json_check(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DomainError("invalid_json", "Value cannot be serialized as UTF-8 JSON.") from exc


def canonical_hash(value: Any) -> str:
    """SHA-256 of sorted, compact, UTF-8 JSON (not an RFC8785 implementation)."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def text_hash(value: str) -> str:
    if not isinstance(value, str):
        raise DomainError("invalid_text", "Expected text.")
    try:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise DomainError("invalid_text", "Text must encode as UTF-8.") from exc


def _fail(code: str, field: str, message: str) -> None:
    raise DomainError(code, message, {"field": field})


def _object(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code, "record", "Expected a JSON object.")
    if len(_json_bytes(value)) > MAX_REQUEST_BYTES:
        raise DomainError("request_too_large", "Record exceeds the 1 MiB request limit.")
    return dict(value)


def _fields(value: dict[str, Any], allowed: set[str], code: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise DomainError(code, "Unknown fields.", {"fields": unknown})


def _string(value: Any, field: str, code: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail(code, field, f"Expected nonblank text of at most {limit} characters.")
    return value


def _identifier(value: Any, field: str, code: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail(code, field, "Expected a 1–128 character ASCII identifier.")
    return value


def _date(value: Any, field: str, code: str) -> str | None:
    if value is None:
        return None
    try:
        return utc(value)
    except DomainError as exc:
        _fail(code, field, exc.message)


def _bounded_json(value: Any, field: str, code: str) -> Any:
    if field == "qualifiers":
        if type(value) is not dict:
            _fail(code, field, "Qualifiers must be a JSON object.")
        if "exclusive" in value and type(value["exclusive"]) is not bool:
            _fail(code, field, "The exclusive qualifier must be a boolean.")
    try:
        _json_check(value, bounded=True)
        encoded = _json_bytes(value)
        if len(encoded) > MAX_CONTEXT_BYTES:
            _fail(code, field, "Context exceeds the 64 KiB limit.")
        return json.loads(encoded)
    except DomainError as exc:
        _fail(code, field, exc.message)


def validate_record(record: dict[str, Any], corpus_id: str) -> dict[str, Any]:
    """Validate input; return an independent normalized record, never mutate it."""
    code = "invalid_record"
    result = _object(record, code)
    _identifier(corpus_id, "corpus_id", code)
    if result.get("corpus_id", corpus_id) != corpus_id:
        _fail(code, "corpus_id", "Corpus identity does not match the request.")
    result["corpus_id"] = corpus_id
    if result.get("schema_version") != "1":
        _fail(code, "schema_version", "Only schema version '1' is supported.")
    for field in ("event_id", "document_id", "version_id"):
        _identifier(result.get(field), field, code)
    operation = result.get("operation")
    if operation not in ("upsert", "withdraw"):
        _fail(code, "operation", "Expected upsert or withdraw.")
    _fields(result, _UPSERT_FIELDS if operation == "upsert" else _WITHDRAW_FIELDS, code)
    if result.get("access_scope") != "public":
        _fail(code, "access_scope", "Only the public scope is supported.")
    if "language" in result and result["language"] != "en":
        _fail(code, "language", "Only English is supported by the fixture adapter.")
    result["source_available_at"] = _date(result.get("source_available_at"), "source_available_at", code)
    for field in ("source_event_at", "reference_time"):
        if field in result:
            result[field] = _date(result[field], field, code)
    for field in ("source_uri", "source_version_ref", "rights_ref", "source_timezone", "time_precision"):
        if field in result:
            _string(result[field], field, code, 2048 if field == "source_uri" else 512)
    for field in _JSON_FIELDS & result.keys():
        result[field] = _bounded_json(result[field], field, code)

    if operation == "withdraw":
        _string(result.get("reason"), "reason", code, 4096)
        return result

    if result.get("processing_version") != "plain-text-v1":
        _fail(code, "processing_version", "Only lossless plain-text-v1 is supported.")
    for field in ("source_uri", "source_version_ref", "rights_ref"):
        _string(result.get(field), field, code, 2048 if field == "source_uri" else 512)
    if result.get("language") != "en":
        _fail(code, "language", "Upserts require language='en'.")
    source = _string(result.get("text"), "text", code, MAX_TEXT_CHARS)
    digest = text_hash(source)
    for field in ("content_sha256", "source_sha256"):
        if result.get(field) != digest:
            _fail(code, field, "Hash must equal SHA-256 of the exact UTF-8 text.")
    predecessor = result.get("supersedes_version_id")
    if predecessor is not None:
        _identifier(predecessor, "supersedes_version_id", code)
        if predecessor == result["version_id"]:
            _fail(code, "supersedes_version_id", "A source version cannot supersede itself.")
    result["supersedes_version_id"] = predecessor
    return result


def validate_assertion(assertion: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Validate an authored source assertion, not its real-world truth."""
    code = "invalid_assertion"
    result = _object(assertion, code)
    _fields(result, _ASSERTION_FIELDS, code)
    if type(record) is not dict or record.get("operation") != "upsert" or not isinstance(record.get("text"), str):
        _fail(code, "record", "Assertions require an upsert source record.")
    if result.get("schema_version", "1") != "1":
        _fail(code, "schema_version", "Only schema version '1' is supported.")
    result["schema_version"] = "1"
    if result.get("corpus_id", record.get("corpus_id")) != record.get("corpus_id"):
        _fail(code, "corpus_id", "Assertion corpus does not match its source.")
    result["corpus_id"] = record.get("corpus_id")
    for field in ("assertion_id", "subject_id", "object_id"):
        _identifier(result.get(field), field, code)
    for field in ("document_id", "version_id", "processing_version"):
        if result.get(field) != record.get(field) or not isinstance(result.get(field), str):
            _fail(code, field, "Assertion source/processing version does not match.")
    if result.get("method") not in {"authored-fixture", "local-model-v1"}:
        _fail(code, "method", "Expected authored-fixture or local-model-v1.")
    if result.get("modality") not in ("reported", "planned", "negated"):
        _fail(code, "modality", "Expected reported, planned, or negated.")
    start, end = result.get("start"), result.get("end")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(record["text"]):
        _fail(code, "start/end", "Expected nonempty half-open Unicode offsets inside the source.")
    span = record["text"][start:end]
    if result.get("text") != span:
        _fail(code, "text", "Assertion text must exactly equal its cited source span.")
    for field in ("subject_label", "object_label"):
        label = _string(result.get(field), field, code)
        if label not in span:
            _fail(code, field, "Endpoint label must occur literally in the cited span.")
    status = result.get("temporal_status")
    if type(status) is not dict or set(status) != {"from", "to"}:
        _fail(code, "temporal_status", "Expected exactly the from and to bound statuses.")
    result["temporal_status"] = dict(status)
    for bound, allowed in (("from", {"known", "unknown"}), ("to", {"known", "open", "unknown"})):
        field = f"valid_{bound}"
        if not isinstance(status[bound], str) or status[bound] not in allowed:
            _fail(code, "temporal_status", "Invalid temporal bound status.")
        result[field] = _date(result.get(field), field, code)
        if (status[bound] == "known") != (result[field] is not None):
            _fail(code, field, "Known bounds require a date; unknown/open bounds require null.")
    if result["valid_from"] is not None and result["valid_to"] is not None:
        if result["valid_to"] <= result["valid_from"]:
            _fail(code, "valid_to", "Validity end must be strictly after its start.")
    supersedes = result.get("supersedes", [])
    if type(supersedes) is not list or len(supersedes) > 128:
        _fail(code, "supersedes", "Expected at most 128 assertion IDs.")
    for item in supersedes:
        _identifier(item, "supersedes", code)
    if len(set(supersedes)) != len(supersedes) or result["assertion_id"] in supersedes:
        _fail(code, "supersedes", "Supersession IDs must be distinct and exclude this assertion.")
    result["supersedes"] = list(supersedes)
    if "relation_group" in result:
        _identifier(result["relation_group"], "relation_group", code)
    for field in {"metadata", "context", "qualifiers"} & result.keys():
        result[field] = _bounded_json(result[field], field, code)
    return result


def cache_key(
    record: dict[str, Any], model_config: dict[str, Any], *,
    prompt_version: str = "1", schema_version: str = "1", context: Any = None,
    identity_map_version: str | None = None,
) -> str:
    """Include all source/context/configuration inputs, not text alone."""
    if type(model_config) is not dict:
        _fail("invalid_cache_input", "model_config", "Expected a configuration object.")
    return canonical_hash({
        "record": record,
        "model_config": _bounded_json(model_config, "model_config", "invalid_cache_input"),
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "context": _bounded_json(context, "context", "invalid_cache_input"),
        "identity_map_version": identity_map_version,
    })
