"""SQLite reference backend for the first evidence and temporal workflow slice.

No model or network calls. Assertions are explicitly imported authored fixtures.
Projection size is bounded; this backend makes no large-scale performance claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import wraps
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .records import DomainError, canonical_hash, now_utc, text_hash, utc, validate_assertion, validate_record
from .storage import migrate, SCHEMA_VERSION, bounded_query
from .vectors import VectorMixin, cosine, ranked_fusion
from .pipeline import PipelineMixin


MAX_EVENTS = 20_000
MAX_BATCH = 1_000
MAX_BATCH_BYTES = 16 * 1024 * 1024
CHUNK_SIZE = 1200


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _id(prefix):
    return prefix + "_" + uuid.uuid4().hex


def _key(record):
    return canonical_hash([record["corpus_id"], record["document_id"], record["version_id"], record.get("processing_version", "plain-text-v1")])


def _clean(value):
    return {k: v for k, v in value.items() if not k.startswith("_")}


def _terms(text):
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def _projection_request(function):
    """Cache immutable projections only for one operation, never across publishes."""
    @wraps(function)
    def call(self, *args, **kwargs):
        previous = getattr(self, "_projection_cache", None)
        self._projection_cache = previous if previous is not None else {}
        try:
            return function(self, *args, **kwargs)
        finally:
            self._projection_cache = previous
    return call


class Engine(VectorMixin, PipelineMixin):
    def __init__(self, db_path, clock=None):
        self.path = Path(db_path) if str(db_path) != ":memory:" else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or now_utc
        self.db = sqlite3.connect(str(db_path), timeout=10)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
            self.db.close()
            raise DomainError("newer_database", "This database requires a newer application version")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY, corpus TEXT NOT NULL, idem TEXT NOT NULL,
          payload_hash TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL,
          records TEXT NOT NULL, result TEXT NOT NULL, assertions TEXT,
          snapshot_id TEXT, UNIQUE(corpus,idem));
        CREATE TABLE IF NOT EXISTS events(
          id TEXT PRIMARY KEY, corpus TEXT NOT NULL, event_id TEXT NOT NULL,
          payload TEXT NOT NULL, received TEXT NOT NULL, seq INTEGER,
          published TEXT, UNIQUE(corpus,event_id));
        CREATE TABLE IF NOT EXISTS snapshots(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          corpus TEXT NOT NULL, published TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS active(corpus TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assertions(
          id TEXT NOT NULL, corpus TEXT NOT NULL, payload TEXT NOT NULL,
          seq INTEGER NOT NULL, published TEXT NOT NULL, PRIMARY KEY(corpus,id));
        CREATE TABLE IF NOT EXISTS extraction(
          corpus TEXT NOT NULL, record_key TEXT NOT NULL, seq INTEGER NOT NULL,
          status TEXT NOT NULL, PRIMARY KEY(corpus,record_key,seq));
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, corpus TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cursors(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
          offset INTEGER NOT NULL, expires TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS baselines(id TEXT PRIMARY KEY, corpus TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, corpus TEXT NOT NULL,
          version INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_scope ON events(corpus,seq,published);
        CREATE INDEX IF NOT EXISTS assertions_scope ON assertions(corpus,seq,published);
        """)
        migrate(self.db)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _now(self):
        value = self.clock()
        return utc(value.isoformat() if isinstance(value, datetime) else value)

    def _checkpoint(self):
        deadline = getattr(self, "_query_deadline", None)
        if deadline is not None and time.monotonic() >= deadline:
            raise DomainError("query_budget_exhausted", "Query deadline reached while projecting evidence; no incomplete projection returned")

    def _one(self, table, identifier):
        # Table names are internal constants, never caller SQL.
        if table not in {"jobs", "runs", "baselines", "investigations"}:
            raise ValueError("internal table")
        row = self.db.execute(f"SELECT * FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise DomainError("not_found", f"Unknown {table} identifier")
        return row

    def validate_corpus(self, corpus_id, records):
        if not isinstance(records, list) or len(records) > MAX_BATCH:
            raise DomainError("batch_limit", f"Provide at most {MAX_BATCH} records")
        if len(_dump(records).encode("utf-8")) > MAX_BATCH_BYTES:
            raise DomainError("batch_limit", "Batch exceeds 16 MiB")
        accepted, rejected = [], []
        for index, record in enumerate(records):
            try:
                accepted.append(validate_record(record, corpus_id))
            except DomainError as exc:
                rejected.append({"index": index, "event_id": record.get("event_id") if isinstance(record, dict) else None, "error": exc.to_dict()})
        return {"corpus_id": corpus_id, "accepted": len(accepted), "rejected": len(rejected),
                "errors": rejected, "records": accepted, "sampled": False,
                "adapter": "lossless-plain-text-v1", "supported_language": "en"}

    def ingest(self, corpus_id, records, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200:
            raise DomainError("invalid_request", "A bounded nonempty idempotency key is required")
        payload_hash = canonical_hash(records)
        old = self.db.execute("SELECT * FROM jobs WHERE corpus=? AND idem=?", (corpus_id, idempotency_key)).fetchone()
        if old:
            if old["payload_hash"] != payload_hash:
                raise DomainError("idempotency_conflict", "Key already used with a different payload")
            return self.get_job(old["id"])
        report = self.validate_corpus(corpus_id, records)
        received, job_id = self._now(), _id("job")
        kept, rejected = [], list(report["errors"])
        with self.db:
            # Serialize the version check with inserts; callers may already hold
            # this lock while reserving a new corpus for a generated dataset.
            if not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT * FROM jobs WHERE corpus=? AND idem=?", (corpus_id, idempotency_key)).fetchone()
            if old:
                if old["payload_hash"] != payload_hash:
                    raise DomainError("idempotency_conflict", "Key already used with a different payload")
                return self.get_job(old["id"])
            versions = defaultdict(list)
            for row in self.db.execute("SELECT payload FROM events WHERE corpus=?", (corpus_id,)):
                prior = json.loads(row["payload"])
                if prior["operation"] == "upsert":
                    versions[(prior["document_id"], prior["version_id"])].append(prior)
            for record in report["records"]:
                try:
                    existing = self.db.execute("SELECT payload FROM events WHERE corpus=? AND event_id=?", (corpus_id, record["event_id"])).fetchone()
                    if existing and _dump(json.loads(existing["payload"])) != _dump(record):
                        raise DomainError("event_conflict", "Source event ID has different content")
                    if record["operation"] == "upsert":
                        for prior in versions[(record["document_id"], record["version_id"])]:
                            if prior["source_sha256"] != record["source_sha256"] or (_key(prior) == _key(record) and prior["content_sha256"] != record["content_sha256"]):
                                raise DomainError("version_conflict", "Immutable version content conflicts")
                            if _key(prior) == _key(record) and prior != record:
                                semantic_prior = {k: v for k, v in prior.items() if k != "event_id"}
                                semantic_new = {k: v for k, v in record.items() if k != "event_id"}
                                if semantic_prior != semantic_new:
                                    raise DomainError("version_conflict", "Immutable version metadata conflicts")
                    self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,NULL,NULL)",
                                    (canonical_hash([corpus_id, record["event_id"]]), corpus_id, record["event_id"], _dump(record), received))
                    if not existing and record["operation"] == "upsert":
                        versions[(record["document_id"], record["version_id"])].append(record)
                    kept.append(record)
                except DomainError as exc:
                    rejected.append({"event_id": record["event_id"], "error": exc.to_dict()})
            result = {"job_id": job_id, "corpus_id": corpus_id, "accepted": len(kept),
                      "rejected": len(rejected), "errors": rejected, "created_at": received,
                      "status": "succeeded", "publication": "pending", "method": "source-ingestion"}
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL)",
                            (job_id, corpus_id, idempotency_key, payload_hash, received, "succeeded", _dump(kept), _dump(result)))
        return result

    def get_job(self, job_id):
        row = self._one("jobs", job_id)
        result = json.loads(row["result"])
        result.update(status=row["status"], snapshot_id=row["snapshot_id"], publication="published" if row["snapshot_id"] else "pending")
        return result

    def cancel_job(self, job_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self._one("jobs", job_id)
            if row["snapshot_id"]:
                raise DomainError("already_published", "The snapshot is already published")
            self.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return self.get_job(job_id)

    def stage_assertions(self, job_id, assertions, *, preparation=None):
        job = self._one("jobs", job_id)
        if job["snapshot_id"] or job["status"] == "cancelled":
            raise DomainError("job_closed", "Cannot stage assertions for a closed job")
        if not isinstance(assertions, list) or len(assertions) > 5000:
            raise DomainError("batch_limit", "At most 5000 authored assertions per job")
        records = {_key(r): r for r in json.loads(job["records"]) if r["operation"] == "upsert"}
        normalized, ids = [], set()
        for assertion in assertions:
            if not isinstance(assertion, dict) or not all(isinstance(assertion.get(k), str) for k in ("document_id", "version_id", "processing_version")):
                raise DomainError("invalid_evidence", "Assertion requires document, version, and processing identifiers")
            lookup = dict(assertion, corpus_id=job["corpus"])
            record = records.get(_key(lookup))
            if record is None:
                raise DomainError("invalid_evidence", "Assertion source must be in this job")
            result = validate_assertion(assertion, record)
            if result["method"] == "local-model-v1" and preparation is None:
                raise DomainError("missing_model_provenance", "Local-model assertions must be staged through the extraction pipeline")
            if result["assertion_id"] in ids:
                raise DomainError("assertion_conflict", "Duplicate assertion ID in batch")
            ids.add(result["assertion_id"])
            normalized.append(result)
        # Recheck under the publication lock after potentially expensive validation.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            job = self._one("jobs", job_id)
            if job["snapshot_id"] or job["status"] == "cancelled":
                raise DomainError("job_closed", "Cannot stage assertions for a closed job")
            if job["assertions"] is not None and json.loads(job["assertions"]) != normalized:
                raise DomainError("assertion_conflict", "Job already has a different authored extraction")
            self.db.execute("UPDATE jobs SET assertions=? WHERE id=?", (_dump(normalized), job_id))
            if preparation is not None:
                self.db.execute("INSERT INTO model_preparations VALUES(?,?)", (job_id, _dump(preparation)))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return {"job_id": job_id, "assertions": len(normalized), "method": preparation["method"] if preparation else "authored-fixture", "prepared_at": self._now()}

    def _events(self, corpus, seq, cutoff):
        rows = self.db.execute("SELECT * FROM events WHERE corpus=? AND seq<=? AND published<=? ORDER BY seq,id LIMIT ?", (corpus, seq, cutoff, MAX_EVENTS + 1)).fetchall()
        if len(rows) > MAX_EVENTS:
            raise DomainError("reference_capacity_exceeded", f"Reference projection supports at most {MAX_EVENTS} published events; use the planned scale backend")
        return rows

    def _sources(self, snapshot, cutoff, *, history=False):
        cache = getattr(self, "_projection_cache", None)
        cache_key = ("sources", snapshot["corpus_id"], snapshot["sequence"], cutoff, history)
        if cache is not None and cache_key in cache:
            return cache[cache_key]
        versions, withdrawn, superseded = {}, set(), set()
        for row in self._events(snapshot["corpus_id"], snapshot["sequence"], cutoff):
            self._checkpoint()
            r = json.loads(row["payload"])
            if r["operation"] == "withdraw":
                withdrawn.add((r["document_id"], r["version_id"]))
                continue
            key = _key(r)
            if key not in versions:
                versions[key] = dict(r, _key=key, _received=row["received"], _visible=row["published"], _sequence=row["seq"])
            if r.get("supersedes_version_id"):
                superseded.add((r["document_id"], r["supersedes_version_id"]))
        for record in versions.values():
            identity = (record["document_id"], record["version_id"])
            record["_active"] = identity not in withdrawn and identity not in superseded
            record["_source_status"] = "withdrawn" if identity in withdrawn else "superseded" if identity in superseded else "active"
        result = {key: r for key, r in versions.items() if history or r["_active"]}
        if cache is not None:
            cache[(*cache_key[:-1], True)] = versions
            cache[(*cache_key[:-1], False)] = {key: r for key, r in versions.items() if r["_active"]}
        return result

    def publish_snapshot(self, job_id, label=None, allow_exclusions=False):
        # BEGIN IMMEDIATE serializes publication and cancellation across connections.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            job = self._one("jobs", job_id)
            if job["snapshot_id"]:
                self.db.rollback()
                return self.get_snapshot(job["snapshot_id"])
            if job["status"] == "cancelled":
                raise DomainError("job_cancelled", "Cancelled job cannot publish")
            result, records = json.loads(job["result"]), json.loads(job["records"])
            if result["rejected"] and not allow_exclusions:
                raise DomainError("excluded_records", "Publication requires explicit allowance of recorded exclusions", result["errors"])
            published = self._now()
            if published < job["created"]:
                raise DomainError("invalid_clock", "Publication cannot precede ingestion")
            last = self.db.execute("SELECT MAX(published) t FROM snapshots WHERE corpus=?", (job["corpus"],)).fetchone()["t"]
            if last and published < last:
                raise DomainError("invalid_clock", "Publication clocks must be monotonic per corpus")
            known = {(r["document_id"], r["version_id"]) for r in records if r["operation"] == "upsert"}
            parent_map = {}
            for row in self.db.execute("SELECT payload FROM events WHERE corpus=? AND seq IS NOT NULL", (job["corpus"],)):
                r = json.loads(row["payload"])
                if r["operation"] == "upsert":
                    known.add((r["document_id"], r["version_id"]))
                    parent_map[(r["document_id"], r["version_id"])] = r.get("supersedes_version_id")
            for r in records:
                parent = r.get("supersedes_version_id") if r["operation"] == "upsert" else r["version_id"]
                if parent and (r["document_id"], parent) not in known:
                    raise DomainError("pending_reference", "Source revision/withdrawal target is not published or in this batch")
                if r["operation"] == "upsert":
                    parent_map[(r["document_id"], r["version_id"])] = parent
            for (document, version) in parent_map:
                seen, cursor = set(), version
                while cursor:
                    if cursor in seen:
                        raise DomainError("revision_cycle", "Source revision chain contains a cycle")
                    seen.add(cursor)
                    cursor = parent_map.get((document, cursor))
            snapshot_id = _id("snap")
            insert = self.db.execute("INSERT INTO snapshots(id,corpus,published,data) VALUES(?,?,?,?)", (snapshot_id, job["corpus"], published, "{}"))
            sequence = insert.lastrowid
            for r in records:
                self.db.execute("UPDATE events SET seq=?,published=? WHERE corpus=? AND event_id=? AND seq IS NULL", (sequence, published, job["corpus"], r["event_id"]))
            authored = json.loads(job["assertions"]) if job["assertions"] is not None else None
            preparation_row = self.db.execute("SELECT metadata FROM model_preparations WHERE job_id=?", (job_id,)).fetchone()
            preparation = json.loads(preparation_row["metadata"]) if preparation_row else None
            model_outcomes = {(o["document_id"], o["version_id"]): o.get("status", "succeeded_with_assertions" if o["assertions"] else "abstained") for o in preparation["outcomes"]} if preparation else {}
            if authored is not None:
                existing_ids = {row[0] for row in self.db.execute("SELECT id FROM assertions WHERE corpus=?", (job["corpus"],))}
                incoming_ids = {a["assertion_id"] for a in authored}
                for a in authored:
                    for old_id in a.get("supersedes", []):
                        if old_id not in existing_ids:
                            raise DomainError("pending_reference", "Superseded assertion must already be published")
                        if old_id in incoming_ids:
                            raise DomainError("assertion_cycle", "Cannot supersede an assertion in the same batch")
                    prior = self.db.execute("SELECT payload FROM assertions WHERE corpus=? AND id=?", (job["corpus"], a["assertion_id"])).fetchone()
                    if prior and json.loads(prior["payload"]) != a:
                        raise DomainError("assertion_conflict", "Immutable assertion ID has different interpretation")
                    self.db.execute("INSERT OR IGNORE INTO assertions VALUES(?,?,?,?,?)", (a["assertion_id"], job["corpus"], _dump(a), sequence, published))
                counts = Counter(_key(dict(a, corpus_id=job["corpus"])) for a in authored)
                for r in records:
                    if r["operation"] == "upsert":
                        status = "succeeded_with_assertions" if counts[_key(r)] else "succeeded_empty"
                        if preparation:
                            status = model_outcomes.get((r["document_id"], r["version_id"]), "abstained")
                        self.db.execute("INSERT OR IGNORE INTO extraction VALUES(?,?,?,?)", (job["corpus"], _key(r), sequence, status))
            snapshot = {"snapshot_id": snapshot_id, "corpus_id": job["corpus"], "published_at": published,
                        "sequence": sequence, "label": label or snapshot_id, "backend": "sqlite-reference-v1"}
            self.db.execute("UPDATE jobs SET snapshot_id=? WHERE id=?", (snapshot_id, job_id))
            coverage = self._coverage(snapshot, published)
            capabilities = ["lexical", "source_compare"]
            if coverage["interpretation_complete"]:
                capabilities += ["assertions", "expansion", "knowledge_compare", "world_compare"]
                projected = self._assertions(snapshot, published)
                if not any(a["temporal_status"]["from"] == "known" and a["temporal_status"]["to"] != "unknown" for a in projected):
                    capabilities.remove("world_compare")
            snapshot.update(capabilities=capabilities, coverage=dict(coverage, excluded_in_batch=result["rejected"]))
            self.db.execute("UPDATE snapshots SET data=? WHERE id=?", (_dump(snapshot), snapshot_id))
            self.db.execute("INSERT INTO active VALUES(?,?) ON CONFLICT(corpus) DO UPDATE SET snapshot_id=excluded.snapshot_id", (job["corpus"], snapshot_id))
            self.db.execute("UPDATE jobs SET snapshot_id=? WHERE id=?", (snapshot_id, job_id))
            self.db.commit()
            return snapshot
        except BaseException:
            self.db.rollback()
            raise

    def get_snapshot(self, snapshot_id, corpus_id=None):
        if snapshot_id == "latest":
            row = self.db.execute("SELECT snapshot_id FROM active WHERE corpus=?", (corpus_id,)).fetchone()
            if not row:
                raise DomainError("not_ready", "No published snapshot for this corpus")
            snapshot_id = row["snapshot_id"]
        row = self.db.execute("SELECT data FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if not row:
            raise DomainError("not_found", "Unknown snapshot")
        snapshot = json.loads(row["data"])
        if corpus_id is not None and snapshot["corpus_id"] != corpus_id:
            raise DomainError("scope_mismatch", "Snapshot belongs to another corpus")
        return snapshot

    def list_snapshots(self, corpus_id):
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM snapshots WHERE corpus=? ORDER BY seq", (corpus_id,))]

    def list_corpora(self):
        return [{"corpus_id": r["corpus"], **{k: v for k, v in self.get_corpus_status(r["corpus"]).items() if k in {"status", "snapshot"}}} for r in self.db.execute("SELECT DISTINCT corpus FROM jobs ORDER BY corpus")]

    def doctor(self):
        checks = [row[0] for row in self.db.execute("PRAGMA quick_check")]
        return {"schema_version": self.db.execute("PRAGMA user_version").fetchone()[0], "integrity": checks, "ok": checks == ["ok"], "corpora": len(self.list_corpora()), "backend": "sqlite", "local_models": "llama.cpp-loopback", "vectors": "exact-cosine; optional immutable artifacts"}

    def backup(self, destination):
        target = Path(destination)
        if target.exists():
            raise DomainError("backup_exists", "Choose a new backup path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        connection = sqlite3.connect(str(target))
        try:
            self.db.backup(connection)
        finally:
            connection.close()
        return {"path": str(target.resolve()), "schema_version": SCHEMA_VERSION, "bytes": target.stat().st_size}

    def get_corpus_status(self, corpus_id):
        snapshots = self.list_snapshots(corpus_id)
        return {"corpus_id": corpus_id, "status": "ready" if snapshots else "not_ready", "snapshot": snapshots[-1] if snapshots else None,
                "jobs": [self.get_job(r["id"]) for r in self.db.execute("SELECT id FROM jobs WHERE corpus=? ORDER BY created,id", (corpus_id,))],
                "vector_indexes": self.list_vector_indexes(corpus_id),
                "limitations": ["sqlite-reference-backend", "no-ANN-index", "no-generated-answers", "entity-resolution-not-implemented"]}

    def _scope(self, corpus_id, snapshot_id, cutoff):
        snapshot = self.get_snapshot(snapshot_id, corpus_id)
        cutoff = utc(cutoff) if cutoff else snapshot["published_at"]
        if cutoff > snapshot["published_at"]:
            raise DomainError("invalid_cutoff", "Knowledge cutoff exceeds snapshot watermark")
        return snapshot, cutoff

    def _coverage(self, snapshot, cutoff):
        cache = getattr(self, "_projection_cache", None)
        cache_key = ("coverage", snapshot["corpus_id"], snapshot["sequence"], cutoff)
        if cache is not None and cache_key in cache:
            return dict(cache[cache_key])
        sources = self._sources(snapshot, cutoff)
        outcomes, processing = Counter(), {}
        for row in self.db.execute("SELECT e.record_key,e.status FROM extraction e JOIN snapshots s ON e.seq=s.seq WHERE e.corpus=? AND e.seq<=? AND s.published<=? ORDER BY e.seq", (snapshot["corpus_id"], snapshot["sequence"], cutoff)):
            self._checkpoint()
            processing[row["record_key"]] = row["status"]
        for key in sources:
            outcomes[processing.get(key, "pending")] += 1
        exclusions = []
        for row in self.db.execute("SELECT j.id,j.result FROM jobs j JOIN snapshots s ON j.snapshot_id=s.id WHERE j.corpus=? AND s.seq<=? AND s.published<=? ORDER BY s.seq", (snapshot["corpus_id"], snapshot["sequence"], cutoff)):
            self._checkpoint()
            exclusions.extend(dict(e, job_id=row["id"]) for e in json.loads(row["result"])["errors"])
        model_jobs = self.db.execute("SELECT COUNT(*) FROM model_preparations p JOIN jobs j ON j.id=p.job_id JOIN snapshots s ON s.id=j.snapshot_id WHERE j.corpus=? AND s.seq<=? AND s.published<=?", (snapshot["corpus_id"], snapshot["sequence"], cutoff)).fetchone()[0]
        result = {"active_documents": len(sources), "extraction": dict(outcomes),
                "excluded_records": len(exclusions), "exclusions": exclusions,
                "method": "local-model-and/or-authored" if model_jobs else "authored-fixture" if processing else "source-only",
                "interpretation_complete": bool(processing) and not any(outcomes[s] for s in ("pending", "abstained", "failed")),
                "knowledge_cutoff": cutoff}
        if cache is not None:
            cache[cache_key] = result
        return dict(result)

    def _chunks(self, record):
        for start in range(0, len(record["text"]), CHUNK_SIZE):
            end = min(start + CHUNK_SIZE, len(record["text"]))
            yield {"id": "chunk_" + canonical_hash([record["_key"], start, end])[:32], "start": start, "end": end,
                   "text": record["text"][start:end]}

    def _citation(self, record, start, end):
        return {"corpus_id": record["corpus_id"], "document_id": record["document_id"], "version_id": record["version_id"],
                "processing_version": record["processing_version"], "source_uri": record["source_uri"], "start": start, "end": end,
                "text_hash": text_hash(record["text"][start:end]), "content_sha256": record["content_sha256"],
                "source_available_at": record.get("source_available_at"), "ingested_at": record["_received"],
                "visible_from": record["_visible"], "source_status": record["_source_status"]}

    def _assertions(self, snapshot, cutoff, valid_time=None, *, history=False):
        when = utc(valid_time) if valid_time else None
        cache = getattr(self, "_projection_cache", None)
        rows_key = ("assertion_rows", snapshot["corpus_id"], snapshot["sequence"], cutoff)
        cache_key = (*rows_key, when, history)
        if cache is not None and cache_key in cache:
            return cache[cache_key]
        records = self._sources(snapshot, cutoff, history=history)
        by_version = {(r["document_id"], r["version_id"], r["processing_version"]): r for r in records.values()}
        cached_rows = cache.get(rows_key) if cache is not None else None
        if cached_rows is None:
            rows = self.db.execute("SELECT * FROM assertions WHERE corpus=? AND seq<=? AND published<=? ORDER BY seq,id LIMIT ?", (snapshot["corpus_id"], snapshot["sequence"], cutoff, MAX_EVENTS + 1)).fetchall()
            if len(rows) > MAX_EVENTS:
                raise DomainError("reference_capacity_exceeded", "Assertion projection exceeds reference capacity")
            parsed, superseded = [], set()
            for row in rows:
                self._checkpoint()
                assertion = json.loads(row["payload"])
                parsed.append((row["published"], assertion))
                superseded.update(assertion.get("supersedes", []))
            cached_rows = parsed, superseded
            if cache is not None:
                cache[rows_key] = cached_rows
        parsed, superseded = cached_rows
        output = []
        for published, a in parsed:
            self._checkpoint()
            record = by_version.get((a["document_id"], a["version_id"], a["processing_version"]))
            if record is None or (not history and a["assertion_id"] in superseded):
                continue
            if when:
                status = a["temporal_status"]
                if status["from"] != "known" or status["to"] == "unknown":
                    continue
                if not (a["valid_from"] <= when and (status["to"] == "open" or when < a["valid_to"])):
                    continue
            item = dict(a, id=a["assertion_id"], kind="assertion", recorded_at=published,
                        evidence=self._citation(record, a["start"], a["end"]), status="superseded" if a["assertion_id"] in superseded else a["modality"], disputed=False)
            output.append(item)
        self._mark_disputes(output)
        if cache is not None:
            cache[cache_key] = output
        return output

    def _mark_disputes(self, assertions):
        """Same exclusive-group overlap predicate, without all-pairs comparison."""
        groups = defaultdict(list)
        for a in assertions:
            self._checkpoint()
            if (a["modality"] == "reported" and a.get("qualifiers", {}).get("exclusive")
                    and a.get("relation_group") and a["temporal_status"]["from"] == "known"
                    and a["temporal_status"]["to"] != "unknown"):
                groups[a["relation_group"]].append(a)
        for group in groups.values():
            ordered = sorted(group, key=lambda a: (a["valid_from"], a["id"]))
            # Forward: maximum prior end from a different endpoint pair.
            # Reverse: minimum later start from a different endpoint pair.
            # Two distinct pairs suffice for each query; open ends sort last.
            for forward in (True, False):
                best = {}
                for a in ordered if forward else reversed(ordered):
                    self._checkpoint()
                    pair = a["subject_id"], a["object_id"]
                    end = a["valid_to"] or "\uffff"
                    if any(other != pair and (bound > a["valid_from"] if forward else bound < end)
                           for other, bound in best.items()):
                        a.update(disputed=True, status="disputed")
                    bound = end if forward else a["valid_from"]
                    best[pair] = (max if forward else min)(best.get(pair, bound), bound)
                    best = dict(sorted(best.items(), key=lambda entry: entry[1], reverse=forward)[:2])

    def _adjacency(self, assertions):
        cache = getattr(self, "_projection_cache", None)
        cache_key = ("adjacency", id(assertions))
        if cache is not None and cache_key in cache:
            return cache[cache_key]
        result = defaultdict(list)
        for a in assertions:
            self._checkpoint()
            for entity in {a["subject_id"], a["object_id"]}:
                result[entity].append(a)
        if cache is not None:
            cache[cache_key] = result
        return result

    @_projection_request
    def get_evidence(self, corpus_id, snapshot_id="latest", *, chunk_id=None, assertion_id=None, knowledge_cutoff=None, history=False):
        if bool(chunk_id) == bool(assertion_id):
            raise DomainError("invalid_request", "Supply exactly one chunk or assertion ID")
        snapshot, cutoff = self._scope(corpus_id, snapshot_id, knowledge_cutoff)
        scope = {"corpus_id": corpus_id, "snapshot_id": snapshot["snapshot_id"],
                 "knowledge_cutoff": cutoff, "history": history}
        if assertion_id:
            for item in self._assertions(snapshot, cutoff, history=history):
                if item["assertion_id"] == assertion_id:
                    context = {key: item[key] for key in ("subject_id", "subject_label", "object_id", "object_label",
                               "valid_from", "valid_to", "temporal_status", "method", "recorded_at", "supersedes", "disputed")}
                    return dict(item["evidence"], **context, scope=scope, assertion_id=assertion_id,
                                text=item["text"], modality=item["modality"], status=item["status"])
        else:
            for record in self._sources(snapshot, cutoff, history=history).values():
                for chunk in self._chunks(record):
                    if chunk["id"] == chunk_id:
                        return dict(self._citation(record, chunk["start"], chunk["end"]), scope=scope,
                                    chunk_id=chunk_id, text=chunk["text"])
        raise DomainError("evidence_not_visible", "Evidence is absent or not eligible in this snapshot/cutoff")

    def _budget(self, budget):
        defaults = {"max_candidates": 300, "max_edges": 500, "max_hops": 2, "max_per_node": 50,
                    "max_evidence_chars": 48000, "max_scan": 5000, "max_request_wall_ms": 5000}
        aliases = {"candidate_limit": "max_candidates", "edge_limit": "max_edges", "hop_limit": "max_hops"}
        for key, value in (budget or {}).items():
            key = aliases.get(key, key)
            if key not in defaults or isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > max(defaults[key] * 10, 1):
                raise DomainError("invalid_budget", "Unsupported or out-of-range budget field")
            defaults[key] = value
        return defaults

    def _save_run(self, corpus, result):
        result["run_id"] = _id("run")
        result.setdefault("created_at", self._now())
        with self.db:
            self.db.execute("INSERT INTO runs VALUES(?,?,?)", (result["run_id"], corpus, _dump(result)))
        return result

    def get_run(self, run_id):
        return json.loads(self._one("runs", run_id)["data"])

    def overview(self, corpus_id, snapshot_id="latest", knowledge_cutoff=None):
        """Read-only, complete eligible counts plus a bounded list of real hubs."""
        return self._overview(corpus_id, snapshot_id, knowledge_cutoff,
                              budget={"max_request_wall_ms": 2500})

    @_projection_request
    @bounded_query
    def _overview(self, corpus_id, snapshot_id, knowledge_cutoff, *, budget):
        started = time.monotonic()
        snapshot, cutoff = self._scope(corpus_id, snapshot_id, knowledge_cutoff)
        sources = self._sources(snapshot, cutoff)
        assertions = self._assertions(snapshot, cutoff)
        labels, connections = {}, Counter()
        modalities = Counter()
        for item in assertions:
            self._checkpoint()
            modalities[item["modality"]] += 1
            for end in ("subject", "object"):
                labels.setdefault(item[end + "_id"], item[end + "_label"])
            connections.update({item["subject_id"], item["object_id"]})
        hubs = [{"id": entity, "label": labels[entity], "connections": count}
                for entity, count in connections.items()]
        hubs.sort(key=lambda hub: (-hub["connections"], hub["label"].casefold(), hub["id"]))
        coverage = self._coverage(snapshot, cutoff)
        self._checkpoint()
        result = {"operation": "overview",
                  "scope": {"corpus_id": corpus_id, "snapshot_id": snapshot["snapshot_id"],
                            "knowledge_cutoff": cutoff, "valid_time": None},
                  "counts": {"active_documents": len({r["document_id"] for r in sources.values()}),
                             "active_source_versions": len(sources), "assertions": len(assertions),
                             "entities": len(connections), "reported": modalities["reported"],
                             "planned": modalities["planned"], "negated": modalities["negated"],
                             "disputed": sum(item["disputed"] for item in assertions)},
                  "top_entities": hubs[:20], "top_entities_truncated": len(hubs) > 20,
                  "capabilities": snapshot["capabilities"], "coverage": dict(coverage, counts_complete=True),
                  "truncated": False, "stop_reasons": [],
                  "budget": {"max_request_wall_ms": 2500, "max_source_events": MAX_EVENTS,
                             "max_assertion_versions": MAX_EVENTS, "top_entity_limit": 20},
                  "usage": {"model_calls": 0, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)},
                  "notice": "Eligible source interpretations; disputed is an overlay on reported assertions. Entity IDs are not automatically merged."}
        if corpus_id == "discovery-network":
            from .network_demo import SCENARIOS
            result["scenarios"] = SCENARIOS
        return result

    def preview(self, corpus_id, query, snapshot_id="latest", knowledge_cutoff=None,
                valid_time=None, mode="lexical"):
        """Ephemeral typing feedback: fixed limits, no vectors, no saved run/cursor."""
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 256 or len(query) > 256 or len(_terms(query)) > 16:
            raise DomainError("invalid_query", "Preview requires 2–256 characters and at most 16 terms")
        if mode not in {"lexical", "graphrag"}:
            raise DomainError("unsupported_capability", "Preview supports lexical or graph retrieval without vectors")
        return self.search(corpus_id, query, snapshot_id=snapshot_id, knowledge_cutoff=knowledge_cutoff,
                           valid_time=valid_time, mode=mode, limit=12, page_size=12,
                           budget={"max_candidates": 12, "max_edges": 12, "max_hops": 1,
                                   "max_per_node": 8, "max_evidence_chars": 14400,
                                   "max_scan": 20000, "max_request_wall_ms": 750}, _preview=True)

    @_projection_request
    @bounded_query
    def search(self, corpus_id, query, snapshot_id="latest", knowledge_cutoff=None, valid_time=None,
               mode="lexical", limit=20, page_size=10, budget=None,
               vector_index_id=None, query_vector=None, embedding_profile=None, *, _preview=False):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise DomainError("invalid_query", "Supply a nonempty query of at most 4000 characters")
        if type(limit) is not int or not 1 <= limit <= 300 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise DomainError("invalid_request", "Invalid result/page size")
        snapshot, cutoff = self._scope(corpus_id, snapshot_id, knowledge_cutoff)
        if mode not in {"lexical", "dense", "hybrid", "graphrag"} or (mode == "graphrag" and "assertions" not in snapshot["capabilities"]):
            raise DomainError("unsupported_capability", "This snapshot/reference engine does not support the requested retrieval mode")
        if valid_time and mode != "graphrag":
            raise DomainError("unsupported_temporal_query", "Source text has no extracted world-time assertions; use graph mode")
        if _preview and (mode not in {"lexical", "graphrag"} or any(x is not None for x in (vector_index_id, query_vector, embedding_profile))):
            raise DomainError("invalid_query", "Preview does not accept vector retrieval")
        use_vectors = mode in {"dense", "hybrid"} or vector_index_id is not None
        if mode == "lexical" and any(x is not None for x in (vector_index_id, query_vector, embedding_profile)):
            raise DomainError("invalid_query", "Lexical mode does not use vector parameters")
        if use_vectors and not vector_index_id:
            raise DomainError("vector_index_required", "Dense/hybrid retrieval requires an explicit immutable index")
        if not use_vectors and any(x is not None for x in (query_vector, embedding_profile)):
            raise DomainError("vector_index_required", "Query vectors require an explicit immutable index")
        index, query_embedding = self._vector_query(vector_index_id, corpus_id, query_vector, embedding_profile) if use_vectors else (None, None)
        budget, start_time = self._budget(budget), time.monotonic()
        query_terms = _terms(query)
        terms = set(query_terms)
        # Only the unfinished final word is a prefix; completed words keep the
        # normal search scoring. A trailing separator marks the word complete.
        prefix = query_terms[-1] if _preview and query_terms and re.search(r"\w$", query) else None
        candidates, scanned, reasons = [], 0, []
        assertions = self._assertions(snapshot, cutoff, valid_time) if mode == "graphrag" else []
        if mode == "graphrag":
            iterator = iter(assertions)
        else:
            def chunks():
                for r in self._sources(snapshot, cutoff).values():
                    for c in self._chunks(r):
                        yield dict(c, chunk_id=c["id"], kind="chunk", evidence=self._citation(r, c["start"], c["end"]))
            iterator = chunks()
        for item in iterator:
            if scanned >= budget["max_scan"] or (time.monotonic() - start_time) * 1000 >= budget["max_request_wall_ms"]:
                reasons.append("scan_or_time_budget")
                break
            scanned += 1
            counts = Counter(_terms(item["text"]))
            score = sum(min(counts[t], 3) for t in terms) / max(len(terms), 1)
            if prefix:
                expanded = sum(count for term, count in counts.items() if term.startswith(prefix))
                score += (min(expanded, 3) - min(counts[prefix], 3)) / len(terms)
            if use_vectors:
                vector = self._item_vector(vector_index_id, item)
                candidates.append(dict(item, lexical_score=score, dense_score=cosine(query_embedding, vector)))
            elif score:
                candidates.append(dict(item, score=score, selection_reason={"channel": "assertion_lexical" if mode == "graphrag" else "passage_lexical"}))
        if use_vectors:
            candidates = ranked_fusion(candidates, dense_only=mode == "dense")
        else:
            candidates.sort(key=lambda x: (-x["score"], x["id"]))
        if len(candidates) > budget["max_candidates"]:
            reasons.append("candidate_budget")
        candidates = candidates[:budget["max_candidates"]]
        if mode == "graphrag" and candidates:
            adjacency = self._adjacency(assertions)
            if len(candidates) > budget["max_edges"]:
                reasons.append("edge_budget")
            selected = {a["id"]: a for a in candidates[:budget["max_edges"]]}
            frontier = {e for a in selected.values() for e in (a["subject_id"], a["object_id"])}
            visited, edge_visits = set(), 0
            for hop in range(budget["max_hops"]):
                next_frontier = set()
                for entity in sorted(frontier - visited):
                    visited.add(entity)
                    adjacent = adjacency.get(entity, [])
                    if len(adjacent) > budget["max_per_node"]:
                        reasons.append("per_node_budget")
                    for a in adjacent[:budget["max_per_node"]]:
                        if edge_visits >= budget["max_edges"] or (time.monotonic() - start_time) * 1000 >= budget["max_request_wall_ms"]:
                            reasons.append("edge_or_time_budget")
                            break
                        edge_visits += 1
                        if a["id"] not in selected and len(selected) < budget["max_edges"]:
                            selected[a["id"]] = dict(a, score=0, selection_reason={"channel": "graph_expansion", "predecessor_entity": entity, "hop": hop + 1})
                            next_frontier.update((a["subject_id"], a["object_id"]))
                frontier = next_frontier
            candidates = sorted(selected.values(), key=lambda a: (-a["score"], a["id"]))
        total_matches = len(candidates)
        items, used_chars = [], 0
        for item in candidates[:limit]:
            if used_chars + len(item["text"]) > budget["max_evidence_chars"]:
                reasons.append("evidence_budget")
                break
            used_chars += len(item["text"])
            items.append(item)
        if total_matches > limit:
            reasons.append("result_limit")
        result = {"operation": "search", "query": query, "items": items,
                  "scope": {"corpus_id": corpus_id, "snapshot_id": snapshot["snapshot_id"], "knowledge_cutoff": cutoff, "valid_time": utc(valid_time) if valid_time else None, "mode": mode},
                  "usage": {"scanned": scanned, "returned": len(items), "evidence_chars": used_chars, "model_calls": 0, "model_tokens": 0, "elapsed_ms": round((time.monotonic()-start_time)*1000, 3)},
                  "budget": budget, "truncated": bool(reasons), "stop_reasons": sorted(set(reasons)),
                  "coverage": self._coverage(snapshot, cutoff), "answer": None,
                  "notice": "Retrieved source evidence; no generated answer or real-model extraction", "page_size": page_size}
        result["notice"] = "Retrieved source evidence, not a generated answer. Model extraction remains an unverified interpretation."
        if index:
            result["scope"].update(vector_index_id=vector_index_id, embedding_profile=index["profile"], query_vector_hash=canonical_hash(query_vector))
            result["retrieval"] = dict(index, query_embedding_hash=canonical_hash(query_vector))
            result["coverage"]["vector_eligibility"] = "Source/assertion cutoff and validity checked before exact scoring"
        if mode == "graphrag" and valid_time:
            unfiltered = self._assertions(snapshot, cutoff)
            result["coverage"]["unknown_time_assertions_excluded"] = sum(a["temporal_status"]["from"] == "unknown" or a["temporal_status"]["to"] == "unknown" for a in unfiltered)
        if _preview:
            self._checkpoint()
            result.update(operation="preview", notice="Live prefix preview; run a search to retain results.")
            result.pop("page_size")
            result["usage"]["elapsed_ms"] = round((time.monotonic() - start_time) * 1000, 3)
            return result
        self._save_run(corpus_id, result)
        return self._page(result, 0)

    def _page(self, run, offset):
        result = dict(run)
        size = run.get("page_size", 100)
        result["items"] = run["items"][offset:offset+size]
        result["total_returned"] = len(run["items"])
        result["next_cursor"] = None
        if offset + size < len(run["items"]):
            existing = self.db.execute("SELECT id FROM cursors WHERE run_id=? AND offset=?", (run["run_id"], offset+size)).fetchone()
            cursor = existing["id"] if existing else _id("cursor")
            if not existing:
                expires = (datetime.fromisoformat(self._now()) + timedelta(days=1)).isoformat(timespec="microseconds")
                with self.db:
                    self.db.execute("INSERT INTO cursors VALUES(?,?,?,?)", (cursor, run["run_id"], offset+size, expires))
            result["next_cursor"] = cursor
        return result

    def page(self, cursor, scope=None):
        row = self.db.execute("SELECT * FROM cursors WHERE id=?", (cursor,)).fetchone()
        if not row or self._now() >= row["expires"]:
            raise DomainError("cursor_unavailable", "Cursor is unknown or expired")
        run = self.get_run(row["run_id"])
        if scope is not None and scope != run["scope"]:
            raise DomainError("cursor_scope_mismatch", "Cursor is pinned to a different effective scope")
        return self._page(run, row["offset"])

    def save_baseline(self, run_id, kind="saved_findings", finding_ids=None, seed_entity_ids=None, hops=1):
        run = self.get_run(run_id)
        if run["operation"] != "search":
            raise DomainError("invalid_baseline", "A baseline starts from a search run")
        if kind not in {"saved_findings", "entity_neighborhood"} or type(hops) is not int or not 1 <= hops <= 2:
            raise DomainError("invalid_baseline", "Unsupported baseline kind or radius")
        available = {i["id"]: i for i in run["items"]}
        chosen = list(available) if finding_ids is None else finding_ids
        if not isinstance(chosen, list) or not chosen or any(i not in available for i in chosen):
            raise DomainError("invalid_baseline", "Select evidence IDs from the saved run")
        items = [available[i] for i in dict.fromkeys(chosen)]
        entities = {e for i in run["items"] if i["kind"] == "assertion" for e in (i["subject_id"], i["object_id"])}
        seeds = seed_entity_ids or []
        if kind == "entity_neighborhood" and (run["scope"]["mode"] != "graphrag" or not seeds or any(e not in entities for e in seeds)):
            raise DomainError("invalid_baseline", "Neighborhood seeds must be entities from a graph run")
        result = {"baseline_id": _id("baseline"), "run_id": run_id, "kind": kind, "scope": run["scope"],
                  "query": run["query"], "finding_ids": chosen, "items": items, "seed_entity_ids": sorted(set(seeds)),
                  "hops": hops, "tracked_documents": sorted({i["evidence"]["document_id"] for i in items}),
                  "coverage": run["coverage"], "origin_truncated": run["truncated"], "created_at": self._now()}
        with self.db:
            self.db.execute("INSERT INTO baselines VALUES(?,?,?)", (result["baseline_id"], run["scope"]["corpus_id"], _dump(result)))
        return result

    def get_baseline(self, baseline_id):
        return json.loads(self._one("baselines", baseline_id)["data"])

    def list_baselines(self, corpus_id):
        return [json.loads(row["data"]) for row in self.db.execute("SELECT data FROM baselines WHERE corpus=? ORDER BY rowid", (corpus_id,))]

    def _baseline_items(self, baseline, snapshot, cutoff, valid_time, budget, *, source_only=False):
        if source_only or baseline["scope"]["mode"] != "graphrag":
            items = []
            for record in self._sources(snapshot, cutoff).values():
                if record["document_id"] not in baseline["tracked_documents"]:
                    continue
                for chunk in self._chunks(record):
                    items.append(dict(chunk, kind="chunk", chunk_id=chunk["id"], evidence=self._citation(record, chunk["start"], chunk["end"])))
            return items, False
        if "assertions" not in snapshot["capabilities"]:
            raise DomainError("unsupported_capability", "Target snapshot lacks graph coverage")
        assertions = self._assertions(snapshot, cutoff, valid_time)
        if baseline["kind"] == "saved_findings":
            # Conservative candidate scope, intentionally not global semantic equivalence.
            old_ids = set(baseline["finding_ids"])
            endpoints = {(a["subject_id"], a["object_id"], a.get("relation_group")) for a in baseline["items"] if a["kind"] == "assertion"}
            return [a for a in assertions if a["evidence"]["document_id"] in baseline["tracked_documents"] or old_ids.intersection(a.get("supersedes", [])) or (a["subject_id"], a["object_id"], a.get("relation_group")) in endpoints], False
        frontier, seen, selected, truncated = set(baseline["seed_entity_ids"]), set(), {}, False
        adjacency = self._adjacency(assertions)
        for _ in range(min(baseline["hops"], budget["max_hops"])):
            next_frontier = set()
            for entity in sorted(frontier - seen):
                self._checkpoint()
                seen.add(entity)
                matches = adjacency.get(entity, [])
                truncated |= len(matches) > budget["max_per_node"]
                for a in matches[:budget["max_per_node"]]:
                    if a["id"] not in selected and len(selected) >= budget["max_edges"]:
                        truncated = True
                        break
                    selected[a["id"]] = a
                    next_frontier.update((a["subject_id"], a["object_id"]))
            frontier = next_frontier
        truncated |= baseline["hops"] > budget["max_hops"]
        return sorted(selected.values(), key=lambda a: a["id"]), truncated

    @_projection_request
    @bounded_query
    def compare(self, baseline_id, target_snapshot_id=None, mode="knowledge_change", knowledge_cutoff=None,
                valid_from_time=None, valid_to_time=None, budget=None):
        baseline = self.get_baseline(baseline_id)
        corpus = baseline["scope"]["corpus_id"]
        if mode not in {"knowledge_change", "source_change", "world_state_change"}:
            raise DomainError("invalid_comparison", "Unsupported comparison mode")
        bounds, began = self._budget(budget), time.monotonic()
        target, cutoff = self._scope(corpus, target_snapshot_id or "latest", knowledge_cutoff)
        old_snapshot = self.get_snapshot(baseline["scope"]["snapshot_id"], corpus)
        base_cutoff = baseline["scope"]["knowledge_cutoff"]
        source_only = mode == "source_change"
        if source_only and baseline["kind"] == "entity_neighborhood":
            raise DomainError("unsupported_comparison", "Source comparison requires saved findings; graph neighborhood source projection is not implemented")
        if mode == "world_state_change":
            if baseline["scope"]["mode"] != "graphrag" or "world_compare" not in target["capabilities"] or not valid_from_time or not valid_to_time:
                raise DomainError("unsupported_temporal_query", "World-state comparison requires a graph baseline, compatible analysis snapshot, and two valid times")
            v0, v1 = utc(valid_from_time), utc(valid_to_time)
            if v1 <= v0:
                raise DomainError("invalid_comparison", "World-state end must follow start")
            all_candidates, candidate_partial = self._baseline_items(baseline, target, cutoff, None, bounds)
            unknown_times = sum(i["temporal_status"]["from"] == "unknown" or i["temporal_status"]["to"] == "unknown" for i in all_candidates)
            if unknown_times:
                raise DomainError("unsupported_temporal_query", "Baseline scope contains unknown validity; a complete world-state comparison is not supported", {"unknown_time_assertions": unknown_times, "candidate_scope_partial": candidate_partial})
            before, t0 = self._baseline_items(baseline, target, cutoff, v0, bounds)
            after, t1 = self._baseline_items(baseline, target, cutoff, v1, bounds)
        else:
            if target["sequence"] < old_snapshot["sequence"] or cutoff < base_cutoff:
                raise DomainError("invalid_comparison", "Target cannot precede baseline knowledge")
            v0 = v1 = baseline["scope"].get("valid_time")
            before, t0 = self._baseline_items(baseline, old_snapshot, base_cutoff, v0, bounds, source_only=source_only)
            after, t1 = self._baseline_items(baseline, target, cutoff, v1, bounds, source_only=source_only)
        old, new = {i["id"]: i for i in before}, {i["id"]: i for i in after}
        changes, unchanged, matched_old = [], [], set()
        truncated = t0 or t1
        reasons = ["neighborhood_budget"] if truncated else []
        processed = 0
        def can_scan():
            nonlocal processed, truncated
            if processed >= bounds["max_scan"] or (time.monotonic()-began)*1000 >= bounds["max_request_wall_ms"]:
                truncated = True
                reasons.append("scan_or_time_budget")
                return False
            processed += 1
            return True
        def add(categories, prior, current, basis):
            changes.append({"change_id": "change_" + canonical_hash([categories, [x["id"] for x in prior], [x["id"] for x in current]])[:24],
                            "category": categories[0], "categories": categories, "before": prior, "after": current,
                            "matching_basis": basis, "uncertainty": "Source reports, not independent verification"})
        if mode == "world_state_change":
            groups = {}
            grouped = True
            for side, collection in (("before", before), ("after", after)):
                for item in collection:
                    if not can_scan():
                        grouped = False
                        break
                    group = item.get("relation_group") or item["object_id"]
                    groups.setdefault(group, {"before": [], "after": []})[side].append(item)
                if not grouped:
                    break
            # An incomplete side cannot justify an apparent temporal disappearance.
            for group, pair in sorted(groups.items()) if grouped and not truncated else []:
                if (time.monotonic()-began)*1000 >= bounds["max_request_wall_ms"]:
                    truncated = True
                    reasons.append("scan_or_time_budget")
                    break
                if {x["id"] for x in pair["before"]} == {x["id"] for x in pair["after"]}:
                    unchanged.extend(pair["after"])
                    continue
                planned = any(x["modality"] == "planned" for x in pair["before"] + pair["after"])
                categories = ["planned_transition" if planned else "world_state_change"]
                if any(x.get("disputed") for x in pair["before"] + pair["after"]):
                    categories.append("unresolved_conflict")
                add(categories, pair["before"], pair["after"], "fixed-K state projections; explicit fixture group " + group)
        else:
            for identifier, item in sorted(new.items()):
                if not can_scan():
                    break
                if identifier in old:
                    matched_old.add(identifier)
                    if item.get("disputed") != old[identifier].get("disputed"):
                        add(["unresolved_conflict" if item.get("disputed") else "assessment_change"], [old[identifier]], [item], "same assertion with changed conflict candidates")
                    else:
                        unchanged.append(item)
                    continue
                prior = [old[x] for x in item.get("supersedes", []) if x in old]
                if source_only:
                    prior = [x for x in before if x["evidence"]["document_id"] == item["evidence"]["document_id"]]
                if prior:
                    matched_old.update(x["id"] for x in prior)
                    categories = ["source_revision" if source_only else "correction"]
                    if not source_only and all(x["evidence"]["version_id"] == item["evidence"]["version_id"] for x in prior):
                        categories = ["processing_discovery"]
                else:
                    categories = ["new_support"]
                citation = item["evidence"]
                if citation.get("source_available_at") and citation["source_available_at"] < citation["ingested_at"]:
                    categories.append("late_evidence")
                if item.get("disputed"):
                    categories.append("unresolved_conflict")
                add(categories, prior, [item], "explicit lineage" if prior else "new candidate in declared baseline scope")
            if not truncated:
                history_records = self._sources(target, cutoff, history=True)
                for identifier, item in sorted(old.items()):
                    if identifier in matched_old or identifier in new:
                        continue
                    if not can_scan():
                        break
                    evidence = item["evidence"]
                    record = history_records.get(_key(evidence))
                    category = "retraction" if record and record["_source_status"] == "withdrawn" else "source_revision" if record and record["_source_status"] == "superseded" else "coverage_change"
                    add([category], [item], [], "source lifecycle or eligibility; absence does not establish world end")
        if len(changes) + len(unchanged) > bounds["max_candidates"]:
            changes = changes[:bounds["max_candidates"]]
            unchanged = unchanged[:max(0, bounds["max_candidates"] - len(changes))]
            truncated = True
            reasons.append("candidate_budget")
        used_chars = 0
        def fits(items):
            nonlocal used_chars, truncated
            size = sum(len(i["text"]) for i in items)
            if used_chars + size > bounds["max_evidence_chars"]:
                truncated = True
                reasons.append("evidence_budget")
                return False
            used_chars += size
            return True
        changes = [c for c in changes if fits(c["before"] + c["after"])]
        unchanged = [i for i in unchanged if fits([i])]
        original_findings = [i for i in baseline["items"] if fits([i])]
        scope = {"corpus_id": corpus, "baseline_id": baseline_id, "baseline_kind": baseline["kind"],
                 "baseline_snapshot_id": old_snapshot["snapshot_id"], "target_snapshot_id": target["snapshot_id"],
                 "analysis_snapshot_id": target["snapshot_id"] if mode == "world_state_change" else None,
                 "knowledge_cutoff": cutoff, "mode": mode, "valid_from_time": v0, "valid_to_time": v1}
        result = {"operation": "compare", "changes": changes, "unchanged": unchanged, "scope": scope, "truncated": truncated,
                  "stop_reasons": sorted(set(reasons)),
                  "coverage": {"baseline_candidates": len(before), "target_candidates": len(after), "complete_within_candidate_scope": not truncated,
                               "scope_limit": "Explicit source lineages/endpoint candidates or bounded entity neighborhood; no semantic completeness guarantee"},
                  "usage": {"scanned": processed, "evidence_chars": used_chars, "elapsed_ms": round((time.monotonic()-began)*1000, 3), "model_calls": 0}, "budget": bounds,
                  "original_saved_findings": original_findings, "next_cursor": None,
                  "notice": "Source-assertion comparison; model interpretations are unverified; resumable ledger enumeration is not implemented"}
        return self._save_run(corpus, result)

    def save_investigation(self, data, expected_version=None):
        required = {"corpus_id", "title", "question", "snapshot_id"}
        allowed = required | {"investigation_id", "notes", "run_ids", "baseline_ids", "view", "status"}
        if not isinstance(data, dict) or not required <= data.keys() or data.keys() - allowed:
            raise DomainError("invalid_investigation", "Invalid investigation fields")
        if not all(isinstance(data[k], str) and data[k].strip() for k in required) or len(_dump(data)) > 100000:
            raise DomainError("invalid_investigation", "Investigation fields are empty or too large")
        if data.get("status", "active") not in {"active", "concluded"}:
            raise DomainError("invalid_investigation", "Unsupported investigation status")
        for key in ("run_ids", "baseline_ids"):
            if not isinstance(data.get(key, []), list) or any(not isinstance(x, str) or not x for x in data.get(key, [])):
                raise DomainError("invalid_investigation", key + " must be a list of identifiers")
        notes = data.get("notes", "")
        if not isinstance(notes, str) and not (isinstance(notes, list) and all(isinstance(n, str) for n in notes)):
            raise DomainError("invalid_investigation", "Notes must be text or a list of text notes")
        if "view" in data and not isinstance(data["view"], dict):
            raise DomainError("invalid_investigation", "View must be an object")
        self.get_snapshot(data["snapshot_id"], data["corpus_id"])
        for run_id in data.get("run_ids", []):
            if self.get_run(run_id)["scope"]["corpus_id"] != data["corpus_id"]:
                raise DomainError("scope_mismatch", "Run belongs to another corpus")
        for baseline_id in data.get("baseline_ids", []):
            if self.get_baseline(baseline_id)["scope"]["corpus_id"] != data["corpus_id"]:
                raise DomainError("scope_mismatch", "Baseline belongs to another corpus")
        identifier = data.get("investigation_id") or _id("investigation")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM investigations WHERE id=?", (identifier,)).fetchone()
            if row and (row["corpus"] != data["corpus_id"] or expected_version != row["version"]):
                raise DomainError("version_conflict", "Investigation was changed; reload before saving")
            if not row and expected_version is not None:
                raise DomainError("version_conflict", "Investigation does not exist")
            result = dict(data, investigation_id=identifier, version=row["version"] + 1 if row else 1, updated_at=self._now())
            self.db.execute("INSERT INTO investigations VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data",
                            (identifier, data["corpus_id"], result["version"], _dump(result)))
            self.db.commit()
            return result
        except BaseException:
            self.db.rollback()
            raise

    def get_investigation(self, investigation_id):
        return json.loads(self._one("investigations", investigation_id)["data"])

    def list_investigations(self, corpus_id):
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM investigations WHERE corpus=? ORDER BY rowid", (corpus_id,))]

    @_projection_request
    def export_evidence(self, run_id, destination):
        run = self.get_run(run_id)
        target = Path(destination)
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise DomainError("export_exists", "Export destination must be new or empty")
        evidence = list(run.get("items", [])) + list(run.get("unchanged", [])) + list(run.get("original_saved_findings", []))
        for change in run.get("changes", []):
            evidence.extend(change["before"] + change["after"])
        evidence = list({canonical_hash([e["id"], e["evidence"]]): e for e in evidence}.values())
        # Verify the frozen excerpts themselves, without substituting current text.
        for item in evidence:
            if text_hash(item["text"]) != item["evidence"]["text_hash"]:
                raise DomainError("evidence_integrity", "Saved evidence hash no longer matches")
            citation = item["evidence"]
            rows = self.db.execute("SELECT payload FROM events WHERE corpus=? AND seq IS NOT NULL", (citation["corpus_id"],))
            source = next((r for row in rows if (r := json.loads(row["payload"]))["operation"] == "upsert" and _key(r) == _key(citation)), None)
            if source is None or source["content_sha256"] != citation["content_sha256"] or source["text"][citation["start"]:citation["end"]] != item["text"]:
                raise DomainError("evidence_integrity", "Saved evidence does not resolve to its immutable source span")
        lines = ["# GraphRAG evidence export", "", "Local evidence engine. Inspect each assertion's method; model interpretations are unverified. No generated answers.", "",
                 f"Run: {run_id}", f"Operation: {run['operation']}", f"Partial: {run['truncated']}", "", "## Scope", "", "```json", json.dumps(run["scope"], indent=2), "```", ""]
        if run["operation"] == "compare":
            lines += ["## Change categories", ""]
            lines += ["- " + ", ".join(change["categories"]) for change in run["changes"]]
            lines += ["", "Absence or withdrawal does not prove a real-world relationship ended.", ""]
        lines += ["## Evidence", ""]
        for item in evidence:
            citation = item["evidence"]
            fence = "`" * max(3, max((len(x) for x in re.findall(r"`+", item["text"])), default=0) + 1)
            lines += [f"### {item['id']}", "", f"Source: {citation['document_id']} / {citation['version_id']} / {citation['processing_version']}",
                      f"Span: [{citation['start']}, {citation['end']}) | SHA256: {citation['text_hash']}",
                      f"Status: {item.get('status', citation['source_status'])}", "", fence + "text", item["text"], fence, ""]
        payloads = {"run.json": _dump(run) + "\n", "evidence.json": _dump(evidence) + "\n", "report.md": "\n".join(lines)}
        manifest = {"schema_version": "1", "run_id": run_id, "created_at": self._now(), "backend": "sqlite-reference-v1",
                    "reproducibility": "inspectable citations and exact saved-run output; vector profile/hash when used; model weights and vector contents not bundled",
                    "scope": run["scope"], "truncated": run["truncated"], "coverage": run["coverage"],
                    "files": [{"path": name, "sha256": text_hash(text), "bytes": len(text.encode("utf-8"))} for name, text in payloads.items()],
                    "omitted": ["full source corpus", "model weights", "external index artifacts"]}
        target.mkdir(parents=True, exist_ok=True)
        for name, content in dict(payloads, **{"manifest.json": _dump(manifest) + "\n"}).items():
            with (target / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        return {"destination": str(target.resolve()), "manifest": manifest, "files": list(payloads) + ["manifest.json"]}
