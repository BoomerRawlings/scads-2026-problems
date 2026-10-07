"""Capture a fixed, small ROR/Wikidata source collection without importing it.

Default: print the plan. --capture fetches missing sources; --verify is offline.
Existing source bodies are immutable. No media, linked pages, or credentials.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request


PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT / "datasets" / "public-research"
USER_AGENT = "SCADS-Sensemaking-PublicCapture/0.1 (https://boomerrawlings.com)"
ROR_IDS = ("040gcmg81", "05bjen692", "03v6m3209", "05n6zrm60", "00vkwep27", "01cwqze88", "00w52vt71", "02qyzaf42")
WIKIDATA_REVISIONS = {"Q664846": 2550610368, "Q390551": 2543960225, "Q42944": 2541849285, "Q6973636": 2216204992}
SOURCES = [
    {"id": "ror-" + rid, "provider": "ror", "entity_id": rid, "url": "https://api.ror.org/v2/organizations/" + rid}
    for rid in ROR_IDS
] + [
    {"id": "wikidata-" + qid, "provider": "wikidata", "entity_id": qid, "revision": revision,
     "url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json?revision={revision}"}
    for qid, revision in WIKIDATA_REVISIONS.items()
]
POLICY = {
    "minimum_request_interval_seconds": 1,
    "maximum_attempts_per_source": 3,
    "socket_timeout_seconds": 20,
    "run_budget_seconds": 180,
    "maximum_retry_wait_seconds": 30,
    "maximum_source_bytes": 2 * 1024 * 1024,
    "maximum_received_bytes_per_run": 8 * 1024 * 1024,
    "redirects": "rejected",
}


class CaptureError(ValueError):
    """Stable diagnostic code; no raw HTTP/session logs are persisted."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CaptureError("redirect_rejected")


class BoundedClient:
    def __init__(self, opener=None, clock=time.monotonic, sleep=time.sleep):
        self.open = opener or urllib.request.build_opener(NoRedirect()).open
        self.clock, self.sleep = clock, sleep
        self.deadline = clock() + POLICY["run_budget_seconds"]
        self.next_request = clock()
        self.requests = 0
        self.bytes_received = 0

    def _wait(self, seconds: float) -> None:
        seconds = max(0.0, seconds)
        if self.clock() + seconds >= self.deadline:
            raise CaptureError("run_budget_exhausted")
        if seconds:
            self.sleep(seconds)

    def _retry_wait(self, value: str | None, attempt: int) -> float:
        if value:
            try:
                wait = float(value)
            except ValueError:
                try:
                    when = parsedate_to_datetime(value)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    wait = (when - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    raise CaptureError("invalid_retry_after") from None
            if not 0 <= wait <= POLICY["maximum_retry_wait_seconds"]:
                raise CaptureError("retry_after_outside_budget")
            return wait
        return min(5 * (2 ** (attempt - 1)), POLICY["maximum_retry_wait_seconds"])

    def fetch(self, spec: dict) -> tuple[bytes, int]:
        if spec not in SOURCES:
            raise CaptureError("source_outside_fixed_plan")
        for attempt in range(1, POLICY["maximum_attempts_per_source"] + 1):
            self._wait(self.next_request - self.clock())
            self.requests += 1
            self.next_request = self.clock() + POLICY["minimum_request_interval_seconds"]
            request = urllib.request.Request(spec["url"], headers={
                "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "identity",
            })
            try:
                timeout = min(POLICY["socket_timeout_seconds"], self.deadline - self.clock())
                with self.open(request, timeout=timeout) as response:
                    if response.geturl() != spec["url"]:
                        raise CaptureError("unexpected_response_url")
                    if response.headers.get_content_type() != "application/json":
                        raise CaptureError("unexpected_content_type")
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > POLICY["maximum_source_bytes"]:
                        raise CaptureError("source_byte_limit")
                    body = bytearray()
                    while True:
                        if self.clock() >= self.deadline:
                            raise CaptureError("run_budget_exhausted")
                        block = response.read1(min(65536, POLICY["maximum_source_bytes"] - len(body) + 1))
                        if not block:
                            return bytes(body), attempt
                        body.extend(block)
                        self.bytes_received += len(block)
                        if len(body) > POLICY["maximum_source_bytes"]:
                            raise CaptureError("source_byte_limit")
                        if self.bytes_received > POLICY["maximum_received_bytes_per_run"]:
                            raise CaptureError("run_byte_limit")
            except urllib.error.HTTPError as exc:
                code, retry_after = exc.code, exc.headers.get("Retry-After")
                exc.close()
                if code not in {429, 500, 502, 503, 504}:
                    raise CaptureError(f"http_{code}") from None
                error = f"http_{code}"
            except (urllib.error.URLError, TimeoutError, OSError):
                retry_after, error = None, "network_error"
            if attempt == POLICY["maximum_attempts_per_source"]:
                raise CaptureError(error + "_attempts_exhausted")
            self._wait(self._retry_wait(retry_after, attempt))
        raise CaptureError("attempts_exhausted")


def validate_response(spec: dict, raw: bytes) -> dict:
    if len(raw) > POLICY["maximum_source_bytes"]:
        raise CaptureError("source_byte_limit")
    try:
        data = json.loads(raw)
        if spec["provider"] == "ror":
            if data["id"] != "https://ror.org/" + spec["entity_id"]:
                raise CaptureError("ror_identity_mismatch")
            modified = data["admin"]["last_modified"]
            datetime.strptime(modified["date"], "%Y-%m-%d")
            if not isinstance(modified["schema_version"], str):
                raise CaptureError("ror_schema_missing")
            return {"record_modified": modified["date"], "schema_version": modified["schema_version"]}
        entities = data["entities"]
        if set(entities) != {spec["entity_id"]}:
            raise CaptureError("wikidata_identity_mismatch")
        entity = entities[spec["entity_id"]]
        if entity["id"] != spec["entity_id"] or entity["lastrevid"] != spec["revision"]:
            raise CaptureError("wikidata_pinned_revision_mismatch")
        return {"lastrevid": entity["lastrevid"], "modified": entity["modified"]}
    except CaptureError:
        raise
    except (KeyError, TypeError, ValueError):
        raise CaptureError("invalid_source_json_or_metadata") from None


def raw_path(spec: dict) -> str:
    return "raw/" + spec["id"] + ".json"


def verify_entry(output: Path, spec: dict, entry: dict) -> None:
    if entry.get("url") != spec["url"] or entry.get("path") != raw_path(spec) or entry.get("id") != spec["id"]:
        raise CaptureError("saved_provenance_mismatch")
    path = output / raw_path(spec)
    if not path.is_file() or path.stat().st_size > POLICY["maximum_source_bytes"]:
        raise CaptureError("saved_source_missing_or_oversized")
    raw = path.read_bytes()
    if len(raw) != entry.get("size_bytes") or digest(raw) != entry.get("sha256"):
        raise CaptureError("saved_source_hash_mismatch")
    if validate_response(spec, raw) != entry.get("revision"):
        raise CaptureError("saved_revision_mismatch")
    try:
        retrieved = datetime.fromisoformat(entry["retrieved_at_utc"].replace("Z", "+00:00"))
        if retrieved.utcoffset().total_seconds() != 0:
            raise ValueError
    except (KeyError, AttributeError, TypeError, ValueError):
        raise CaptureError("saved_retrieval_time_invalid") from None


def save_manifest(output: Path, manifest: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output, prefix=".capture-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        temporary.replace(output / "capture-manifest.json")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def load_manifest(output: Path, specs: list[dict]) -> dict:
    path = output / "capture-manifest.json"
    if not path.exists():
        return {"schema_version": 1, "scope": "bounded public source acquisition; not an imported analysis corpus", "plan": specs,
                "policy": POLICY, "user_agent": USER_AGENT, "license": "CC0 structured data; linked media excluded",
                "status": "partial", "sources": [], "totals": {"source_count": 0, "raw_bytes": 0}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("plan") != specs:
        raise CaptureError("existing_capture_plan_mismatch")
    ids = [entry["id"] for entry in manifest["sources"]]
    if len(set(ids)) != len(ids) or set(ids) - {spec["id"] for spec in specs}:
        raise CaptureError("existing_capture_entries_invalid")
    return manifest


def capture(output: Path, specs=None, client=None) -> dict:
    specs = SOURCES if specs is None else specs
    if any(spec not in SOURCES for spec in specs):
        raise CaptureError("source_outside_fixed_plan")
    output = output.resolve()
    manifest = load_manifest(output, specs)
    existing = {entry["id"]: entry for entry in manifest["sources"]}
    # Verify every saved source before fetching anything new.
    for spec in specs:
        if spec["id"] in existing:
            verify_entry(output, spec, existing[spec["id"]])
        elif (output / raw_path(spec)).exists():
            raise CaptureError("orphan_source_exists_refusing_overwrite")
    if len(existing) == len(specs):
        return manifest
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    client = client or BoundedClient()
    for spec in specs:
        if spec["id"] in existing:
            continue
        try:
            raw, attempts = client.fetch(spec)
            revision = validate_response(spec, raw)
            entry = {"id": spec["id"], "provider": spec["provider"], "entity_id": spec["entity_id"], "url": spec["url"],
                     "path": raw_path(spec), "retrieved_at_utc": utc_now(), "revision": revision,
                     "sha256": digest(raw), "size_bytes": len(raw), "request_attempts": attempts}
            # Exclusive creation: a rerun never changes an existing response body.
            with (output / raw_path(spec)).open("xb") as stream:
                stream.write(raw)
            manifest["sources"].append(entry)
            manifest["totals"] = {"source_count": len(manifest["sources"]), "raw_bytes": sum(item["size_bytes"] for item in manifest["sources"])}
            manifest.pop("failure", None)
            manifest["status"] = "complete" if len(manifest["sources"]) == len(specs) else "partial"
            save_manifest(output, manifest)
        except (CaptureError, OSError) as exc:
            manifest["status"] = "partial"
            manifest["failure"] = {"source_id": spec["id"], "code": str(exc) if isinstance(exc, CaptureError) else "local_write_error", "at_utc": utc_now()}
            save_manifest(output, manifest)
            raise
    return manifest


def verify_capture(output: Path, specs=None) -> dict:
    specs = SOURCES if specs is None else specs
    manifest = load_manifest(output, specs)
    by_id = {entry["id"]: entry for entry in manifest["sources"]}
    if manifest["status"] != "complete" or set(by_id) != {spec["id"] for spec in specs}:
        raise CaptureError("capture_incomplete")
    for spec in specs:
        verify_entry(output, spec, by_id[spec["id"]])
    expected = {"source_count": len(by_id), "raw_bytes": sum(entry["size_bytes"] for entry in by_id.values())}
    if manifest.get("totals") != expected:
        raise CaptureError("capture_totals_mismatch")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--capture", action="store_true", help="Fetch missing fixed sources; verify and retain existing ones")
    actions.add_argument("--verify", action="store_true", help="Verify all captured files offline")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        if args.capture:
            capture(args.output_dir)
            result = verify_capture(args.output_dir)
        elif args.verify:
            result = verify_capture(args.output_dir)
        else:
            result = {"source_count": len(SOURCES), "ror_records": len(ROR_IDS), "pinned_wikidata_records": len(WIKIDATA_REVISIONS),
                      "policy": POLICY, "next": "Use --capture for the fixed acquisition; no files changed."}
    except (CaptureError, OSError, KeyError, TypeError, ValueError):
        # Manifest has bounded diagnostic codes where a partial capture exists.
        print("Capture failed; existing source files preserved. Inspect capture-manifest.json or run --verify.")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
