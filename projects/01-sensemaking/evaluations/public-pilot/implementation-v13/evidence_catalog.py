"""Unwired, metadata-only paging over the existing in-memory Workspace.

No catalog response grants evidence-retrieval, citation, or graph-proof credit.
Only canonical JSON response bytes are bounded; corpus loading/storage are not.
"""
from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path
import re

from sensemaking import DATA, Workspace

POLICY = "exact-metadata-catalog-v1"
DEFAULT_MAX_ITEMS = 20
DEFAULT_MAX_BYTES = 8192
MAX_ITEMS = 100
MAX_BYTES = 65536
_CURSOR = re.compile(r"v1\.([0-9a-f]{64})\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.([0-9a-f]{64})")


class CatalogError(ValueError):
    """A catalog request or actual-response chain cannot be accepted."""


class StaleCatalogError(CatalogError):
    """Reopen the catalog after any indexed input or declared media change."""


class MetadataItemTooLarge(CatalogError):
    """An exact metadata item cannot fit; nothing was shortened or omitted."""


def catalog_json_bytes(value) -> bytes:
    """Wire representation covered by max_bytes; no added whitespace/newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _snapshot(data_dir: Path) -> str:
    # Stream source/media hashes. This is mutation detection, not scalable indexing
    # or an atomic filesystem transaction. No machine paths enter the digest.
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    required = {"graph.json", "records.csv", "manifest.json"}
    optional = {"dataset.json"}
    for item in manifest:
        required.add(item["path"])
        if item.get("media_path"):
            optional.add(item["media_path"])
    hashes = {}
    for relative in sorted(required | optional):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise CatalogError("Dataset source paths must be relative")
        path = (data_dir / relative).resolve()
        if not path.is_relative_to(data_dir):
            raise CatalogError("Dataset source path escapes its root")
        if not path.is_file():
            if relative in required:
                raise CatalogError("Required dataset source is missing: " + relative)
            hashes[relative] = None
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        hashes[relative] = digest.hexdigest()
    return _sha(catalog_json_bytes(hashes))


def _metadata(record: dict) -> dict:
    fields = ("id", "title", "kind", "date", "source")
    if any(not isinstance(record.get(key), str) for key in (*fields, "text")):
        raise CatalogError("Catalog metadata and text must be strings")
    ids = record.get("entity_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
        raise CatalogError("Catalog entity_ids must be a nonempty string list")
    raw = record["text"].encode("utf-8")
    return {**{key: record[key] for key in fields}, "entity_ids": list(ids),
            "text_sha256": _sha(raw), "text_bytes": len(raw)}


class EvidenceCatalog:
    """Own one read-only Workspace snapshot; close it or use a context manager."""

    def __init__(self, data_dir: Path = DATA):
        self.data_dir = Path(data_dir).resolve()
        self.snapshot_sha256 = _snapshot(self.data_dir)
        self._workspace = Workspace(self.data_dir)
        self._closed = False
        try:
            # Workspace accepts a manifest kind="record" but its public search
            # only exposes CSV records of that kind. Refuse an incomplete view
            # instead of granting catalog inventory credit for a silent omission.
            manifest = json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8"))
            declared = {item["id"] for item in manifest}
            with (self.data_dir / "records.csv").open(encoding="utf-8", newline="") as stream:
                declared.update(row["id"] for row in csv.DictReader(stream))
            visible = {record["id"] for record in self._workspace.search()}
            if visible != declared:
                raise CatalogError("Workspace search cannot expose the complete declared inventory")
            self._check_snapshot()
        except Exception:
            self.close()
            raise

    def close(self):
        if not self._closed:
            self._workspace.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _check_snapshot(self):
        if self._closed:
            raise CatalogError("Catalog is closed")
        try:
            current = _snapshot(self.data_dir)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise StaleCatalogError("Dataset changed or became unreadable; reopen catalog") from error
        if current != self.snapshot_sha256:
            raise StaleCatalogError("Dataset changed; reopen catalog")

    def _request(self, query, entity_ids, max_items, max_bytes):
        if not isinstance(query, str):
            raise CatalogError("query must be a string")
        for name, value, lower, upper in (("max_items", max_items, 1, MAX_ITEMS),
                                          ("max_bytes", max_bytes, 1024, MAX_BYTES)):
            if type(value) is not int or not lower <= value <= upper:
                raise CatalogError(f"{name} must be an integer from {lower} through {upper}")
        if entity_ids is not None:
            if not isinstance(entity_ids, list) or any(not isinstance(value, str) for value in entity_ids):
                raise CatalogError("entity_ids must be a string list or null")
            entity_ids = sorted(set(entity_ids))
            known = {node["id"] for node in self._workspace.entities()}
            if set(entity_ids) - known:
                raise CatalogError("Unknown entity ID in catalog scope")
        request = {"policy": POLICY, "snapshot_sha256": self.snapshot_sha256,
                   "query": query, "entity_ids": entity_ids,
                   "max_items": max_items, "max_bytes": max_bytes}
        return request, _sha(catalog_json_bytes(request))

    def _make_page(self, items, request, binding, start, index, previous):
        def response(selected):
            end = start + len(selected)
            body = {"policy": POLICY, "metadata_only": True, "evidence_content_returned": False,
                    "snapshot_sha256": self.snapshot_sha256, "binding_sha256": binding,
                    "page_index": index, "start": start, "total_items": len(items),
                    "previous_page_sha256": previous, "items": selected}
            page_hash = _sha(catalog_json_bytes(body))
            cursor = None if end == len(items) else f"v1.{binding}.{index + 1}.{end}.{page_hash}"
            return {**body, "page_sha256": page_hash, "next_cursor": cursor}

        if start == len(items):
            page = response([])
            if len(catalog_json_bytes(page)) > request["max_bytes"]:
                raise CatalogError("Empty catalog envelope exceeds max_bytes")
            return page
        accepted = None
        for end in range(start + 1, min(len(items), start + request["max_items"]) + 1):
            candidate = response(items[start:end])
            if len(catalog_json_bytes(candidate)) <= request["max_bytes"]:
                accepted = candidate
            # A terminal page loses its cursor overhead, so keep testing through
            # max_items instead of assuming serialized size is monotonic.
        if accepted is None:
            raise MetadataItemTooLarge("Exact metadata item cannot fit max_bytes: " + items[start]["id"])
        return accepted

    def page(self, query: str = "", entity_ids: list[str] | None = None, *,
             max_items: int = DEFAULT_MAX_ITEMS, max_bytes: int = DEFAULT_MAX_BYTES,
             cursor: str | None = None) -> dict:
        self._check_snapshot()
        request, binding = self._request(query, entity_ids, max_items, max_bytes)
        if cursor is not None:
            match = _CURSOR.fullmatch(cursor) if isinstance(cursor, str) and len(cursor) <= 512 else None
            if match is None or match[1] != binding:
                raise CatalogError("Cursor does not match dataset, query, scope and options")
        items = [_metadata(record) for record in self._workspace.search(query, request["entity_ids"])]
        start, index, previous, expected_cursor = 0, 0, None, None
        while True:
            page = self._make_page(items, request, binding, start, index, previous)
            if cursor == expected_cursor:
                self._check_snapshot()
                return page
            if page["next_cursor"] is None:
                raise CatalogError("Cursor is not a deterministic page boundary in this catalog")
            # Reconstruct the prefix: a made-up offset or previous-page hash is
            # not a valid cursor. Reading a valid later page still earns no
            # complete-inventory credit without its actual preceding responses.
            expected_cursor = page["next_cursor"]
            start += len(page["items"])
            index += 1
            previous = page["page_sha256"]


def validate_catalog_chain(catalog: EvidenceCatalog, exchanges, query: str = "",
                           entity_ids: list[str] | None = None, *,
                           max_items: int = DEFAULT_MAX_ITEMS,
                           max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Validate host-recorded actual request/response pairs, from first to last.

    Each exchange is {"cursor": requested_cursor, "response": actual_response}.
    Never accept these records from an agent as proof that a call occurred.
    Cursors/hashes are deterministic consistency checks, not authentication.
    """
    expected_cursor, finished, pages, count, last = None, False, 0, 0, None
    for exchange in exchanges:
        if (finished or not isinstance(exchange, dict) or set(exchange) != {"cursor", "response"}
                or exchange["cursor"] != expected_cursor):
            raise CatalogError("Catalog chain is replayed, skipped, reordered or malformed")
        expected = catalog.page(query, entity_ids, max_items=max_items,
                                max_bytes=max_bytes, cursor=expected_cursor)
        try:
            matches = catalog_json_bytes(exchange["response"]) == catalog_json_bytes(expected)
        except (ValueError, TypeError, UnicodeError) as error:
            raise CatalogError("Catalog response is not canonical JSON data") from error
        if not matches:
            raise CatalogError("Actual catalog response differs from the bound snapshot/page")
        last = expected
        count += len(expected["items"])
        pages += 1
        expected_cursor = expected["next_cursor"]
        finished = expected_cursor is None
    if not finished:
        raise CatalogError("Catalog chain is absent or shortened before its terminal response")
    catalog._check_snapshot()
    return {"policy": POLICY, "metadata_only": True, "evidence_content_returned": False,
            "snapshot_sha256": last["snapshot_sha256"], "binding_sha256": last["binding_sha256"],
            "pages": pages, "item_count": count, "result_set_complete": True,
            "scope_inventory_complete": not bool(query.split())}
