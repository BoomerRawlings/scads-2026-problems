"""Bounded Elasticsearch transport and snapshot-only analytical execution.

No agent-provided index, URL, credentials, or raw DSL enters this module.
"""

import ipaddress
from datetime import datetime, timezone
import json
import math
import os
import re
import sys
import time
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import AnalyticsError
from .contracts import validate_source_fields


def validate_index(index):
    """Accept one concrete, visibly versioned index name, never selectors."""
    if (not isinstance(index, str) or len(index) > 255
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", index)
            or not re.search(r"(?:-v[0-9]+|-[0-9]{6,})(?:[._-][a-z0-9]+)*$", index)):
        raise AnalyticsError("invalid_config", "Use a concrete versioned index, for example nyc311-demo-v1.")
    return index


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AnalyticsError("backend_unavailable", "Elasticsearch redirects are disabled; configure the final endpoint.")


class ElasticClient:
    """Small stdlib client; default TLS verification and no credential redirects."""

    def __init__(self, url, *, allow_insecure_local=False, timeout=30, opener=None, api_key_env="ELASTIC_API_KEY"):
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except (TypeError, ValueError):
            raise AnalyticsError("invalid_config", "Invalid Elasticsearch endpoint.") from None
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or port == 0):
            raise AnalyticsError("invalid_config", "Elasticsearch endpoint must be an HTTP(S) origin without credentials or query parameters.")
        try:
            local = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = parsed.hostname.lower() == "localhost"
        if parsed.scheme == "http" and not (local and allow_insecure_local is True):
            raise AnalyticsError("invalid_config", "HTTP is allowed only for explicitly enabled loopback development.")
        if api_key_env not in {"ELASTIC_API_KEY", "ELASTIC_ARTIFACT_API_KEY"}:
            raise AnalyticsError("invalid_config", "Unsupported Elasticsearch credential environment variable.")
        self._api_key = os.environ.get(api_key_env)
        if not self._api_key and not (local and allow_insecure_local is True):
            raise AnalyticsError("invalid_config", f"Set {api_key_env}, or explicitly enable unauthenticated loopback development.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 3600:
            raise AnalyticsError("invalid_config", "Elasticsearch timeout must be positive and at most 3600 seconds.")
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or build_opener(_NoRedirect())

    def request(self, method, path, body=None):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise AnalyticsError("invalid_config", "Elasticsearch API path must be relative to the configured origin.")
        if isinstance(body, bytes):
            encoded, content_type = body, "application/x-ndjson"
        elif isinstance(body, str):
            encoded, content_type = body.encode("utf-8"), "application/x-ndjson"
        else:
            encoded = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
            content_type = "application/json"
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if self._api_key:
            headers["Authorization"] = "ApiKey " + self._api_key
        request = Request(self.url + path, data=encoded, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise AnalyticsError("budget_exceeded", "Elasticsearch response exceeded 64 MiB; reduce page size.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("unexpected response")
            return result
        except HTTPError as exc:
            raise AnalyticsError("backend_unavailable", f"Elasticsearch returned HTTP {exc.code}; check endpoint, privileges and request limits.") from None
        except (URLError, TimeoutError, OSError):
            raise AnalyticsError("backend_unavailable", "Elasticsearch connection failed; check endpoint, TLS and service availability.") from None
        except (ValueError, UnicodeError):
            raise AnalyticsError("backend_unavailable", "Elasticsearch returned an invalid JSON response.") from None


def _complete(response, *, search=True):
    if search and response.get("timed_out") is not False:
        raise AnalyticsError("partial_execution", "Elasticsearch search timed out or omitted completion metadata.")
    shards = response.get("_shards")
    if not isinstance(shards, dict) or shards.get("failed") != 0 or shards.get("failures"):
        raise AnalyticsError("partial_execution", "Elasticsearch reported incomplete shard execution.")
    if response.get("terminated_early") is True:
        raise AnalyticsError("partial_execution", "Elasticsearch terminated the query before completion.")


def _total(response):
    hits = response.get("hits")
    total = hits.get("total") if isinstance(hits, dict) else None
    if not isinstance(total, dict) or total.get("relation") != "eq" or type(total.get("value")) is not int or total["value"] < 0:
        raise AnalyticsError("partial_execution", "An exact Elasticsearch match count is required.")
    return total["value"]


def _metrics(container, count, names):
    if not isinstance(container, dict):
        raise AnalyticsError("partial_execution", "Elasticsearch omitted aggregate metrics.")
    row = {"count": count}
    for name in names:
        if name == "count":
            continue
        value = container.get(name)
        if not isinstance(value, dict):
            raise AnalyticsError("partial_execution", f"Elasticsearch omitted metric {name}.")
        if name in {"closed_count", "open_count"}:
            row[name] = value.get("doc_count")
        elif name in {"median_closure_hours", "p90_closure_hours"}:
            percentile = "50.0" if name == "median_closure_hours" else "90.0"
            values = value.get("values", {})
            if percentile not in values:
                raise AnalyticsError("partial_execution", f"Elasticsearch omitted metric {name}.")
            row[name] = values[percentile]
        else:
            if "value" not in value:
                raise AnalyticsError("partial_execution", f"Elasticsearch omitted metric {name}.")
            row[name] = value["value"]
        if row[name] is not None and (isinstance(row[name], bool) or not isinstance(row[name], (int, float)) or not math.isfinite(row[name])):
            raise AnalyticsError("partial_execution", f"Elasticsearch returned an invalid value for {name}.")
        if name in {"closed_count", "open_count"} and (type(row[name]) is not int or not 0 <= row[name] <= count):
            raise AnalyticsError("partial_execution", f"Elasticsearch returned an invalid count for {name}.")
    return row


class ElasticBackend:
    def __init__(self, config, catalog, manifest, *, client=None):
        self.config, self.catalog, self.manifest = config, catalog, manifest
        self.index = validate_index(config.get("index"))
        budgets = config.get("budgets", {})
        self.page_size = self._budget(budgets, "page_size", 500, 1, 5000)
        self.max_groups = self._budget(budgets, "max_groups", 50000, 1, 1000000)
        self.deadline_seconds = self._budget(budgets, "deadline_seconds", 30, 1, 3600)
        self.max_export_rows = self._budget(budgets, "max_export_rows", 1000000, 1, 1000000000000)
        self.client = client or ElasticClient(config.get("elastic_url", "https://localhost:9200"),
                                              allow_insecure_local=config.get("allow_insecure_local", False),
                                              timeout=self.deadline_seconds)

    @staticmethod
    def _budget(budgets, key, default, minimum, maximum):
        value = budgets.get(key, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise AnalyticsError("invalid_config", f"Budget {key} must be an integer from {minimum} to {maximum}.")
        return value

    def _verify_snapshot(self):
        if self.manifest.get("immutable") is not True or self.manifest.get("index") != self.index:
            raise AnalyticsError("invalid_config", "Elasticsearch execution requires a matching immutable index manifest; freeze ingestion first.")
        settings = self.client.request("GET", f"/{quote(self.index)}/_settings")
        if set(settings) != {self.index}:
            raise AnalyticsError("invalid_config", "Configured dataset must resolve to exactly its concrete index, not an alias.")
        index_settings = settings[self.index].get("settings", {}).get("index", {})
        if not self.manifest.get("index_uuid") or index_settings.get("uuid") != self.manifest["index_uuid"]:
            raise AnalyticsError("invalid_config", "Index identity differs from the frozen manifest; publish a new dataset version.")
        block = index_settings.get("blocks", {}).get("write", index_settings.get("blocks.write"))
        if block not in {True, "true"}:
            raise AnalyticsError("invalid_config", "Dataset index is writable; freeze it before analytical execution.")

    @staticmethod
    def _check_deadline(deadline):
        if time.monotonic() > deadline:
            raise AnalyticsError("budget_exceeded", "Analytical request deadline exceeded; no complete result is available.")

    def _open_pit(self):
        response = self.client.request("POST", f"/{quote(self.index)}/_pit?keep_alive=1m&allow_partial_search_results=false")
        pit = response.get("id")
        try:
            _complete(response, search=False)
        except AnalyticsError:
            if isinstance(pit, str) and pit:
                self._close_pit(pit)
            raise
        if not isinstance(pit, str) or not pit:
            raise AnalyticsError("partial_execution", "Elasticsearch omitted the point-in-time identifier.")
        return pit

    @staticmethod
    def _group_key(key, spec):
        key = dict(key)
        for group in spec.get("group_by", []):
            field = group["field"]
            if "interval" not in group or key.get(field) is None:
                continue
            try:
                value = key[field]
                date = (datetime.fromtimestamp(value / 1000, timezone.utc)
                        if isinstance(value, (int, float)) else datetime.fromisoformat(value.replace("Z", "+00:00")))
                if date.tzinfo is None:
                    raise ValueError()
                key[field] = date.astimezone(ZoneInfo(spec["timezone"])).isoformat()
            except (ValueError, TypeError, OverflowError, OSError):
                raise AnalyticsError("partial_execution", "Elasticsearch returned an invalid date bucket.") from None
        return key

    def _close_pit(self, pit):
        prior_error = sys.exc_info()[0] is not None
        try:
            response = self.client.request("DELETE", "/_pit", {"id": pit})
            if response.get("succeeded") is not True:
                raise AnalyticsError("backend_unavailable", "Elasticsearch did not confirm point-in-time cleanup.")
        except AnalyticsError:
            if not prior_error:
                raise

    def execute(self, spec, *, deadline=None):
        from .compiler import compile_search
        if spec.get("operation") not in {"records", "aggregate"}:
            raise AnalyticsError("unsupported_operation", "Elasticsearch executor supports records and aggregate operations.")
        self._verify_snapshot()
        deadline = time.monotonic() + self.deadline_seconds if deadline is None else deadline
        pit = self._open_pit()
        rows, after, seen_after, seen_groups, total = [], None, set(), set(), None
        names = spec.get("metrics", ["count"])
        approximate = bool(set(names) & {"median_closure_hours", "p90_closure_hours"})
        try:
            while True:
                self._check_deadline(deadline)
                bucket_factor = 1 + len(set(names) & {"closed_count", "open_count"})
                body = compile_search(spec, after_key=after, page_size=min(self.page_size, 5000 // bucket_factor))
                body["track_total_hits"] = total is None
                body["pit"] = {"id": pit, "keep_alive": "1m"}
                body["timeout"] = f"{max(1, int((deadline - time.monotonic()) * 1000))}ms"
                response = self.client.request("POST", "/_search?allow_partial_search_results=false", body)
                pit = response.get("pit_id", pit)
                _complete(response)
                self._check_deadline(deadline)
                page_total = _total(response) if total is None or response.get("hits", {}).get("total") is not None else total
                if total is not None and page_total != total:
                    raise AnalyticsError("partial_execution", "Match count changed inside the immutable snapshot.")
                total = page_total
                if spec["operation"] == "records":
                    hits = response.get("hits", {}).get("hits")
                    if not isinstance(hits, list) or any(not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict) for hit in hits):
                        raise AnalyticsError("partial_execution", "Elasticsearch omitted record sources.")
                    rows = [hit["_source"] for hit in hits]
                    if len(rows) != min(total, spec["preview_limit"]):
                        raise AnalyticsError("partial_execution", "Record preview does not match the exact count and requested preview limit.")
                    break
                aggs = response.get("aggregations", {})
                if not isinstance(aggs, dict):
                    raise AnalyticsError("partial_execution", "Elasticsearch returned malformed aggregations.")
                if not spec.get("group_by"):
                    rows = [{"group": {}, **_metrics(aggs, total, names)}]
                    break
                groups = aggs.get("groups", {})
                if not isinstance(groups, dict):
                    raise AnalyticsError("partial_execution", "Elasticsearch returned malformed composite groups.")
                buckets = groups.get("buckets")
                if not isinstance(buckets, list):
                    raise AnalyticsError("partial_execution", "Elasticsearch omitted composite groups.")
                for bucket in buckets:
                    if not isinstance(bucket, dict) or not isinstance(bucket.get("key"), dict) or type(bucket.get("doc_count")) is not int or bucket["doc_count"] < 0:
                        raise AnalyticsError("partial_execution", "Elasticsearch returned malformed group data.")
                    if set(bucket["key"]) != {group["field"] for group in spec["group_by"]}:
                        raise AnalyticsError("partial_execution", "Elasticsearch group keys differ from requested dimensions.")
                    key = self._group_key(bucket["key"], spec)
                    group_marker = json.dumps(key, sort_keys=True)
                    if group_marker in seen_groups:
                        raise AnalyticsError("partial_execution", "Elasticsearch returned a duplicate composite group.")
                    seen_groups.add(group_marker)
                    rows.append({"group": key, **_metrics(bucket, bucket["doc_count"], names)})
                if len(rows) > self.max_groups:
                    raise AnalyticsError("budget_exceeded", "Complete group enumeration exceeds max_groups; narrow the analysis.")
                after = groups.get("after_key")
                if not buckets and after is not None:
                    raise AnalyticsError("partial_execution", "Empty composite page supplied a continuation key.")
                if not buckets or after is None:
                    break
                marker = json.dumps(after, sort_keys=True)
                if marker in seen_after:
                    raise AnalyticsError("partial_execution", "Elasticsearch composite pagination did not advance.")
                seen_after.add(marker)
            if spec["operation"] == "aggregate" and spec.get("group_by") and sum(row["count"] for row in rows) != total:
                raise AnalyticsError("partial_execution", "Complete group counts do not reconcile with the exact matched population.")
            return {"rows": rows, "total": total, "approximate": approximate,
                    "warnings": ["Elasticsearch closure percentiles are approximate."] if approximate else []}
        finally:
            self._close_pit(pit)

    def iter_records(self, spec, *, deadline=None, source_fields=None):
        """Stream all matching records; generator.close() releases the latest PIT."""
        from .compiler import compile_query
        source_fields = validate_source_fields(source_fields)
        self._verify_snapshot()
        deadline = time.monotonic() + self.deadline_seconds if deadline is None else deadline
        query = compile_query(spec)
        pit = self._open_pit()
        after, total, emitted = None, None, 0
        try:
            while True:
                self._check_deadline(deadline)
                body = {"size": self.page_size, "query": query, "track_total_hits": total is None,
                        "sort": [{"created_date": "asc"}, {"unique_key": "asc"}, {"_shard_doc": "asc"}],
                        "pit": {"id": pit, "keep_alive": "1m"},
                        "timeout": f"{max(1, int((deadline - time.monotonic()) * 1000))}ms"}
                if source_fields is not None:
                    body["_source"] = source_fields
                if after is not None:
                    body["search_after"] = after
                response = self.client.request("POST", "/_search?allow_partial_search_results=false", body)
                pit = response.get("pit_id", pit)
                _complete(response)
                self._check_deadline(deadline)
                page_total = _total(response) if total is None or response.get("hits", {}).get("total") is not None else total
                if total is not None and total != page_total:
                    raise AnalyticsError("partial_execution", "Match count changed while exporting.")
                total = page_total
                if total > self.max_export_rows:
                    raise AnalyticsError("budget_exceeded", "Matching records exceed max_export_rows; narrow the export or configure a larger explicit budget.")
                hits = response.get("hits", {}).get("hits")
                if not isinstance(hits, list):
                    raise AnalyticsError("partial_execution", "Elasticsearch omitted export records.")
                if not hits:
                    if emitted != total:
                        raise AnalyticsError("partial_execution", "Export ended before the exact matching record count.")
                    break
                for hit in hits:
                    if not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict) or not isinstance(hit.get("sort"), list):
                        raise AnalyticsError("partial_execution", "Elasticsearch export record is missing source or pagination values.")
                    emitted += 1
                    if emitted > total:
                        raise AnalyticsError("partial_execution", "Export returned more rows than the exact match count.")
                    yield hit["_source"]
                    self._check_deadline(deadline)
                next_after = hits[-1]["sort"]
                if next_after == after:
                    raise AnalyticsError("partial_execution", "Elasticsearch export pagination did not advance.")
                after = next_after
        finally:
            self._close_pit(pit)
