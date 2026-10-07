"""SQLite persistence, immutable projections, and scoped analyst decisions.

Database queries page materialized projections; the browser never receives the
whole organization. Imports and published snapshots are committed atomically.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid


class Conflict(ValueError):
    """An operation would silently overwrite newer or incompatible state."""


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def valid_date(value):
    if value is not None:
        date.fromisoformat(value)
    return value


def eligible(assertion, as_of):
    if not as_of:
        return True  # Explicit undated exploration; never implied to be current.
    start, end = assertion.get("valid_from"), assertion.get("valid_to")
    if not start and not end:
        return False
    return (not start or start[:10] <= as_of) and (not end or as_of < end[:10])


def overlaps(a, b):
    return max(a.get("valid_from") or "0001-01-01", b.get("valid_from") or "0001-01-01") < min(a.get("valid_to") or "9999-12-31", b.get("valid_to") or "9999-12-31")


def semantic(a):
    return (a["subject"], a["relation"], a["object"], a.get("reporting_type", "primary"))


def active_reviews(reviews):
    undone = {e["event_id"] for e in reviews if e["action"] == "undo"}
    return [e for e in reviews if e["action"] != "undo" and e["id"] not in undone]


def evidence_available(evidence, withdrawn):
    return (evidence.get("available", True) and evidence.get("source_ref") not in withdrawn
            and not withdrawn.intersection(evidence.get("details", {}).get("source_refs", [])))


def redact_evidence(evidence, withdrawn):
    if evidence_available(evidence, set(withdrawn)):
        return evidence
    return {"id": evidence["id"], "kind": evidence["kind"], "source_ref": evidence.get("source_ref"),
            "available": False, "text": None, "details": {"reason": "Source withdrawn or unavailable"}}


def process_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def project(entities, assertions, reviews, *, as_of=None, threshold=.55, margin=.08):
    """Return independent assertions and a cycle-free primary parent map.

    A rejected edge does not automatically promote its runner-up. Competing
    source assertions remain unresolved unless an explicit analyst decision wins.
    """
    people = {e["id"] for e in entities if e.get("type", "person") == "person"}
    rows = [deepcopy(a) for a in assertions]
    by_id = {a["id"]: a for a in rows}
    blocked = set()
    forced = {}
    for event in active_reviews(reviews):
        if not eligible(event, as_of):
            continue
        if event["action"] == "reject":
            blocked.add(event["subject"])
            forced.pop(event["subject"], None)
            for a in rows:
                if semantic(a) == tuple(event["semantic"]) and overlaps(a, event):
                    a["review_status"] = "rejected"
        elif event["action"] in ("accept", "replace"):
            a = deepcopy(event["assertion"])
            a["id"] = f"review:{event['id']}"
            a["review_status"] = "accepted"
            a["review_event"] = event["id"]
            rows.append(a)
            by_id[a["id"]] = a
            if a.get("reporting_type", "primary") == "primary":
                forced[a["subject"]] = a
                blocked.discard(a["subject"])

    candidates = defaultdict(list)
    unresolved = {p: "insufficient_evidence" for p in people}
    for a in rows:
        a["selected"] = False
        if a.get("relation") != "reports_to" or a.get("reporting_type", "primary") != "primary":
            continue
        if a["subject"] not in people or a["object"] not in people or a["subject"] == a["object"]:
            continue
        if a.get("review_status") == "rejected":
            continue
        if not eligible(a, as_of):
            unresolved[a["subject"]] = "outside_time_scope" if a.get("valid_from") else "unknown_dates"
            continue
        if a.get("stale") and a.get("review_status") != "accepted":
            unresolved[a["subject"]] = "evidence_unavailable"
            continue
        candidates[a["subject"]].append(a)

    choices = []
    for subject, options in candidates.items():
        if subject in blocked:
            unresolved[subject] = "analyst_rejected"
            continue
        if subject in forced:
            choices.append((0, forced[subject]))
            continue
        documented = [a for a in options if a.get("origin") in ("source", "analyst")]
        if documented:
            if len({a["object"] for a in documented}) > 1:
                unresolved[subject] = "conflicting_sources"
                continue
            choices.append((1, sorted(documented, key=lambda a: a["id"])[0]))
            continue
        ranked = sorted(options, key=lambda a: (-float(a.get("raw_score") or 0), a["object"], a["id"]))
        best = ranked[0]
        distinct = next((a for a in ranked[1:] if a["object"] != best["object"]), None)
        if float(best.get("raw_score") or 0) < threshold or best.get("selection_hint") is False:
            unresolved[subject] = best.get("selection_reason", "weak_evidence")
        elif distinct and float(best.get("raw_score") or 0) - float(distinct.get("raw_score") or 0) < margin:
            unresolved[subject] = "close_alternatives"
        else:
            choices.append((2, best))

    # With one outgoing parent edge per person, disjoint sets detect cycles in
    # near-linear time, including pathological deep chains.
    components = {p: p for p in people}
    def find(p):
        while components[p] != p:
            components[p] = components[components[p]]
            p = components[p]
        return p
    selected = {}
    for priority, a in sorted(choices, key=lambda item: (item[0], -float(item[1].get("raw_score") or 0), item[1]["subject"])):
        child, parent = a["subject"], a["object"]
        x, y = find(child), find(parent)
        if x == y:
            unresolved[child] = "cycle_conflict"
            continue
        components[x] = y
        a["selected"] = True
        selected[child] = a
        unresolved.pop(child, None)
    for child in blocked:
        unresolved[child] = "analyst_rejected"
    return rows, selected, unresolved


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, digest TEXT, data TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entities(import_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, search TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(import_id,id));
CREATE INDEX IF NOT EXISTS entities_name ON entities(import_id,name COLLATE NOCASE,id);
CREATE INDEX IF NOT EXISTS entities_kind_name ON entities(import_id,kind,name COLLATE NOCASE,id);
CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, import_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projections(snapshot_id TEXT NOT NULL, entity_id TEXT NOT NULL, manager_id TEXT, assertion_id TEXT, status TEXT NOT NULL, children_count INTEGER NOT NULL, metrics TEXT NOT NULL, unresolved_reason TEXT, PRIMARY KEY(snapshot_id,entity_id));
CREATE INDEX IF NOT EXISTS projection_parent ON projections(snapshot_id,manager_id,entity_id);
CREATE INDEX IF NOT EXISTS projection_status ON projections(snapshot_id,status,entity_id);
CREATE TABLE IF NOT EXISTS assertions(snapshot_id TEXT NOT NULL, id TEXT NOT NULL, subject TEXT NOT NULL, relation TEXT NOT NULL, object TEXT NOT NULL, selected INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(snapshot_id,id));
CREATE INDEX IF NOT EXISTS assertion_subject ON assertions(snapshot_id,subject,relation);
CREATE TABLE IF NOT EXISTS raw_assertions(snapshot_id TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(snapshot_id,id));
CREATE TABLE IF NOT EXISTS evidence(snapshot_id TEXT NOT NULL, id TEXT NOT NULL, source_ref TEXT, data TEXT NOT NULL, PRIMARY KEY(snapshot_id,id));
CREATE TABLE IF NOT EXISTS groups_data(snapshot_id TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(snapshot_id,id));
CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, import_id TEXT NOT NULL, seq INTEGER NOT NULL, idempotency_key TEXT, data TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS review_idempotency ON reviews(import_id,idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS withdrawals(import_id TEXT NOT NULL, source_ref TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(import_id,source_ref));
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._chart_indexes = {}
        with self.connection() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES('revision','0')")
            # A process restart must never pretend an interrupted run completed.
            for row in db.execute("SELECT id,data FROM jobs").fetchall():
                job = json.loads(row["data"])
                if job["state"] in ("running", "validating", "queued") and not process_alive(job.get("owner_pid")):
                    job.update(state="failed", error="Process interrupted; retry from saved input checkpoint.")
                    db.execute("UPDATE jobs SET data=? WHERE id=?", (dumps(job), row["id"]))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _meta(self, db, key, default=None):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, db, key, value):
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, dumps(value)))

    def _snapshot(self, db, snapshot=None):
        snapshot = snapshot or self._meta(db, "active_snapshot")
        row = db.execute("SELECT data FROM snapshots WHERE id=?", (snapshot,)).fetchone()
        if not row:
            raise KeyError("No snapshot. Import records or load the fictional demo first.")
        return json.loads(row[0])

    def _check_revision(self, db, revision):
        if revision != self._meta(db, "revision", 0):
            raise Conflict("Workspace changed. Refresh before applying this operation.")

    def _dataset(self, db, import_id):
        return json.loads(db.execute("SELECT data FROM imports WHERE id=?", (import_id,)).fetchone()[0])

    def _reviews(self, db, import_id, revision=None):
        args = [import_id]
        condition = "import_id=?"
        if revision is not None:
            condition += " AND seq<=?"
            args.append(revision)
        return [json.loads(r[0]) for r in db.execute(f"SELECT data FROM reviews WHERE {condition} ORDER BY seq", args)]

    def _rows(self, db, table, snapshot):
        if table not in ("assertions", "raw_assertions", "evidence", "groups_data"):
            raise ValueError("Invalid record type")
        return [json.loads(r[0]) for r in db.execute(f"SELECT data FROM {table} WHERE snapshot_id=?", (snapshot,))]

    def import_dataset(self, dataset, report=None, *, replace=False, base_revision=None):
        fingerprint = digest(dataset)
        with self.lock, self.connection() as db:
            if base_revision is not None:
                self._check_revision(db, base_revision)
            active = self._meta(db, "active_snapshot")
            if active:
                current = self._snapshot(db)
                old = db.execute("SELECT digest FROM imports WHERE id=?", (current["import_id"],)).fetchone()[0]
                if old == fingerprint:
                    return {"snapshot": active, "duplicate": True}
                if not replace:
                    raise Conflict("Workspace already contains a corpus. Explicit replacement is required; existing snapshots will be preserved.")
            iid = uid("import")
            db.execute("INSERT INTO imports VALUES(?,?,?,?,?)", (iid, fingerprint, dumps(dataset), dumps(report or {}), now()))
            db.executemany("INSERT INTO entities VALUES(?,?,?,?,?,?)", [(iid, e["id"], e["name"], e.get("type", "person"), " ".join(str(e.get(k) or "") for k in ("name", "email", "role", "id")) + " " + " ".join(e.get("aliases", [])), dumps(e)) for e in dataset["entities"]])
            sid = self._publish(db, iid, {"assertions": [], "evidence": [], "groups": [], "metrics": {}, "model": {"id": "none", "name": "Imported source records", "calibration_status": "unavailable"}}, reason="Imported records", as_of=None, threshold=.55, margin=.08)
            return {"snapshot": sid, "duplicate": False}

    def _publish(self, db, import_id, result, *, reason, as_of, threshold, margin, snapshot_id=None, revision=None, include_sources=True, created_at=None):
        dataset = self._dataset(db, import_id)
        revision = revision or (self._meta(db, "revision", 0) + 1)
        sid = snapshot_id or uid("snapshot")
        raw = (dataset.get("assertions", []) if include_sources else []) + result.get("assertions", [])
        raw = list({a["id"]: a for a in raw if not a.get("review_event")}.values())
        sources = {r[0] for r in db.execute("SELECT source_ref FROM withdrawals WHERE import_id=?", (import_id,))}
        reviews = self._reviews(db, import_id, revision)
        review_evidence = [e for r in reviews for e in r.get("evidence", [])]
        evidence = {e["id"]: deepcopy(e) for e in dataset.get("evidence", []) + review_evidence + result.get("evidence", [])}
        for e in evidence.values():
            if not evidence_available(e, sources):
                e["available"] = False
        for a in raw:
            ids = a.get("evidence_ids", [])
            if ids and any(i not in evidence or not evidence[i].get("available", True) for i in ids):
                a["stale"] = True
        assertions, selected, unresolved = project(dataset["entities"], raw, reviews, as_of=as_of, threshold=threshold, margin=margin)
        unresolved.update({k: v for k, v in result.get("unresolved", {}).items() if k in unresolved and unresolved[k] == "insufficient_evidence"})
        children = Counter(a["object"] for a in selected.values())
        review_count = len(active_reviews(reviews))
        counts = {"entities": len(dataset["entities"]), "people": sum(e.get("type", "person") == "person" for e in dataset["entities"]), "assertions": len(assertions), "selected": len(selected), "unresolved": len(unresolved), "reviewed": len({e["subject"] for e in active_reviews(reviews)}), "groups": len(result.get("groups", [])) + sum(e.get("type") == "unit" for e in dataset["entities"])}
        metadata = {"id": sid, "import_id": import_id, "revision": revision, "created_at": created_at or now(), "reason": reason, "as_of": as_of, "threshold": threshold, "margin": margin, "model": result.get("model", {}), "counts": counts, "review_count": review_count, "corpus": dataset["corpus"], "inference_run": result.get("run_id"), "projection_policy": "primary-forest-v1"}
        db.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (sid, import_id, revision, dumps(metadata)))
        db.executemany("INSERT INTO raw_assertions VALUES(?,?,?)", [(sid, a["id"], dumps(a)) for a in raw])
        db.executemany("INSERT INTO assertions VALUES(?,?,?,?,?,?,?)", [(sid, a["id"], a["subject"], a["relation"], a["object"], int(a.get("selected", False)), dumps(a)) for a in assertions])
        db.executemany("INSERT INTO evidence VALUES(?,?,?,?)", [(sid, e["id"], e.get("source_ref"), dumps(e)) for e in evidence.values()])
        db.executemany("INSERT INTO groups_data VALUES(?,?,?)", [(sid, g["id"], dumps(g)) for g in result.get("groups", [])])
        projection = []
        for entity in dataset["entities"]:
            ident = entity["id"]
            a = selected.get(ident)
            status = "reviewed" if a and a.get("review_status") == "accepted" else "source" if a and a.get("origin") == "source" else "inferred" if a else "unresolved" if entity.get("type", "person") == "person" else entity.get("type")
            projection.append((sid, ident, a["object"] if a else None, a["id"] if a else None, status, children[ident], dumps(result.get("metrics", {}).get(ident, {})), unresolved.get(ident)))
        db.executemany("INSERT INTO projections VALUES(?,?,?,?,?,?,?,?)", projection)
        self._set(db, "revision", revision)
        self._set(db, "active_snapshot", sid)
        return sid

    def workspace(self):
        with self.connection() as db:
            jobs = [json.loads(r[0]) for r in db.execute("SELECT data FROM jobs ORDER BY rowid DESC LIMIT 10")]
            if not self._meta(db, "active_snapshot"):
                return {"corpus": None, "active_snapshot": None, "revision": 0, "counts": dict.fromkeys(("entities", "people", "assertions", "selected", "unresolved", "reviewed", "groups"), 0), "model": None, "capabilities": [], "snapshots": [], "jobs": jobs, "coverage": {}}
            snap = self._snapshot(db)
            report = json.loads(db.execute("SELECT report FROM imports WHERE id=?", (snap["import_id"],)).fetchone()[0])
            snapshots = [json.loads(r[0]) for r in db.execute("SELECT data FROM snapshots WHERE import_id=? ORDER BY revision DESC LIMIT 100", (snap["import_id"],))]
            return {"corpus": snap["corpus"], "active_snapshot": snap["id"], "revision": self._meta(db, "revision"), "counts": snap["counts"], "model": snap["model"], "capabilities": ["import", "heuristic_inference", "review", "snapshot_comparison", "canonical_export"], "snapshots": snapshots, "jobs": jobs, "coverage": report}

    def run_inference(self, *, base_revision, threshold=.55, margin=.08, as_of=None, engine=None):
        valid_date(as_of)
        if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
            raise ValueError("Threshold and margin must be between 0 and 1.")
        if engine is None:
            from .inference import infer
            engine = infer
        with self.lock, self.connection() as db:
            self._check_revision(db, base_revision)
            snap = self._snapshot(db)
            dataset = self._dataset(db, snap["import_id"])
            dataset.pop("labels", None)
            dataset.pop("assertions", None)
            dataset.pop("evidence", None)
            withdrawn = {r[0] for r in db.execute("SELECT source_ref FROM withdrawals WHERE import_id=?", (snap["import_id"],))}
            dataset["messages"] = [m for m in dataset.get("messages", []) if m.get("source_ref") not in withdrawn and m.get("available", True)]
            job = {"id": uid("job"), "state": "running", "stage": "inference", "created_at": now(), "input_import": snap["import_id"], "base_revision": base_revision, "parameters": {"threshold": threshold, "margin": margin, "as_of": as_of}, "checkpoint": "canonical_input_saved", "owner_pid": os.getpid()}
            db.execute("INSERT INTO jobs VALUES(?,?)", (job["id"], dumps(job)))
        try:
            result = engine(dataset, threshold=threshold, margin=margin, as_of=as_of)
            with self.lock, self.connection() as db:
                state = json.loads(db.execute("SELECT data FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
                if state["state"] == "cancelled":
                    return {"workspace": self.workspace(), "job": state}
                self._check_revision(db, base_revision)
                result["run_id"] = job["id"]
                sid = self._publish(db, snap["import_id"], result, reason="Inference refreshed", as_of=as_of, threshold=threshold, margin=margin)
                job.update(state="complete", stage="published", snapshot=sid, finished_at=now())
                db.execute("UPDATE jobs SET data=? WHERE id=?", (dumps(job), job["id"]))
        except BaseException as exc:
            with self.connection() as db:
                job.update(state="failed", error=str(exc), finished_at=now())
                db.execute("UPDATE jobs SET data=? WHERE id=?", (dumps(job), job["id"]))
            raise
        return {"workspace": self.workspace(), "job": job}

    def cancel_job(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError("Job not found")
            job = json.loads(row[0])
            if job["state"] not in ("queued", "running", "validating"):
                raise Conflict("Only a running job can be cancelled.")
            job.update(state="cancelled", finished_at=now(), note="Cancellation takes effect before snapshot publication.")
            db.execute("UPDATE jobs SET data=? WHERE id=?", (dumps(job), job_id))
            return job

    def retry_job(self, job_id, base_revision):
        with self.connection() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError("Job not found")
            job = json.loads(row[0])
            if job["state"] not in ("failed", "cancelled"):
                raise Conflict("Only failed or cancelled jobs can be retried.")
            if self._snapshot(db)["import_id"] != job["input_import"]:
                raise Conflict("Job belongs to a different imported corpus.")
        return self.run_inference(base_revision=base_revision, **job["parameters"])

    def _entity_item(self, row):
        entity = json.loads(row["data"])
        return {**entity, "manager_id": row["manager_id"], "manager_name": row["manager_name"], "status": row["status"], "children_count": row["children_count"], "metrics": json.loads(row["metrics"]), "unresolved_reason": row["unresolved_reason"]}

    def entities(self, *, q="", type=None, status="all", offset=0, limit=50, snapshot=None, parent="__any__"):
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Use offset >= 0 and limit from 1 to 200.")
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            clauses = ["p.snapshot_id=?", "e.import_id=?"]
            args = [snap["id"], snap["import_id"]]
            if q:
                clauses.append("e.search LIKE ? ESCAPE '\\'")
                args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
            if type:
                clauses.append("e.kind=?")
                args.append(type)
            if status == "reviewed":
                reviewed = sorted({e["subject"] for e in active_reviews(self._reviews(db, snap["import_id"], snap["revision"]))})
                clauses.append("p.entity_id IN (SELECT value FROM json_each(?))")
                args.append(dumps(reviewed))
            elif status != "all":
                clauses.append("p.status=?")
                args.append(status)
            if parent != "__any__":
                clauses.append("p.manager_id IS ?")
                args.append(parent or None)
            where = " AND ".join(clauses)
            if status == "all" and parent == "__any__":
                # Drive ordinary paging from the ordered entity index. Starting
                # from all projections forces a full organization sort per page.
                index = "entities_kind_name" if type else "entities_name"
                join = f" FROM entities e INDEXED BY {index} CROSS JOIN projections p ON e.id=p.entity_id LEFT JOIN entities m ON m.id=p.manager_id AND m.import_id=e.import_id"
                count_clauses, count_args = clauses[1:], args[1:]
                total = db.execute("SELECT COUNT(*) FROM entities e WHERE " + " AND ".join(count_clauses), count_args).fetchone()[0]
            else:
                join = " FROM projections p JOIN entities e ON e.id=p.entity_id LEFT JOIN entities m ON m.id=p.manager_id AND m.import_id=e.import_id"
                total = db.execute("SELECT COUNT(*) FROM projections p JOIN entities e ON e.id=p.entity_id WHERE " + where, args).fetchone()[0]
            rows = db.execute("SELECT e.data,p.*,m.name manager_name" + join + " WHERE " + where + " ORDER BY e.name COLLATE NOCASE,e.id LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
            return {"items": [self._entity_item(r) for r in rows], "total": total, "offset": offset, "limit": limit, "snapshot": snap["id"]}

    def _evidence_records(self, db, snapshot, ids=None):
        snap = self._snapshot(db, snapshot)
        withdrawn = {r[0] for r in db.execute("SELECT source_ref FROM withdrawals WHERE import_id=?", (snap["import_id"],))}
        if ids is not None:
            rows = [db.execute("SELECT data FROM evidence WHERE snapshot_id=? AND id=?", (snapshot, i)).fetchone() for i in dict.fromkeys(ids)]
        else:
            rows = db.execute("SELECT data FROM evidence WHERE snapshot_id=?", (snapshot,)).fetchall()
        result = []
        for row in rows:
            if not row:
                continue
            e = json.loads(row[0])
            result.append(redact_evidence(e, withdrawn))
        return result

    def detail(self, entity_id, snapshot=None):
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            row = db.execute("SELECT e.data,p.*,m.name manager_name FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? LEFT JOIN entities m ON m.id=p.manager_id AND m.import_id=e.import_id WHERE p.snapshot_id=? AND p.entity_id=?", (snap["import_id"], snap["id"], entity_id)).fetchone()
            if not row:
                raise KeyError("Entity not found")
            entity = self._entity_item(row)
            rows = db.execute("SELECT a.data,eo.name object_name,es.name subject_name FROM assertions a LEFT JOIN entities eo ON eo.id=a.object AND eo.import_id=? LEFT JOIN entities es ON es.id=a.subject AND es.import_id=? WHERE a.snapshot_id=? AND (a.subject=? OR (a.object=? AND a.relation='higher_authority_than')) ORDER BY a.selected DESC LIMIT 100", (snap["import_id"], snap["import_id"], snap["id"], entity_id, entity_id)).fetchall()
            assertions = [{**json.loads(r["data"]), "object_name": r["object_name"], "subject_name": r["subject_name"]} for r in rows]
            evidence = self._evidence_records(db, snap["id"], [i for a in assertions for i in a.get("evidence_ids", [])])
            evidence_map = {e["id"]: e for e in evidence}
            for a in assertions:
                a["evidence"] = [evidence_map[i] for i in a.get("evidence_ids", []) if i in evidence_map]
            ancestors = []
            parent = row["manager_id"]
            seen = {entity_id}
            while parent and parent not in seen and len(ancestors) < 40:
                seen.add(parent)
                r = db.execute("SELECT e.data,p.manager_id FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.entity_id=?", (snap["import_id"], snap["id"], parent)).fetchone()
                if not r:
                    break
                ancestors.append(json.loads(r["data"]))
                parent = r["manager_id"]
            children = db.execute("SELECT e.data FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.manager_id=? ORDER BY e.name COLLATE NOCASE,e.id LIMIT 100", (snap["import_id"], snap["id"], entity_id)).fetchall()
            history = [e for e in self._reviews(db, snap["import_id"], snap["revision"]) if e.get("subject") == entity_id]
            undone = {e.get("event_id") for e in history if e["action"] == "undo"}
            withdrawn = {r[0] for r in db.execute("SELECT source_ref FROM withdrawals WHERE import_id=?", (snap["import_id"],))}
            for event in history:
                event["undone"] = event["id"] in undone
                event["evidence"] = [redact_evidence(e, withdrawn) for e in event.get("evidence", [])]
            return {"entity": entity, "manager": next((a for a in assertions if a.get("selected") and a["relation"] == "reports_to"), None), "alternatives": [a for a in assertions if not a.get("selected") and a["relation"] == "reports_to"], "relationships": assertions, "evidence": evidence, "ancestors": ancestors, "ancestors_truncated": bool(parent and len(ancestors) == 40), "children": [json.loads(r[0]) for r in children], "children_total": entity["children_count"], "history": history, "metrics": entity["metrics"], "unresolved_reason": entity.get("unresolved_reason"), "snapshot": snap["id"], "revision": snap["revision"]}

    def graph(self, *, focus=None, limit=80, snapshot=None):
        if not 1 <= limit <= 200:
            raise ValueError("Graph node budget must be between 1 and 200.")
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            selected_ids = []
            seen = set()
            queue = deque()
            def add(ident):
                if ident and ident not in seen and len(selected_ids) < limit:
                    seen.add(ident)
                    selected_ids.append(ident)
                    queue.append(ident)
            if focus:
                row = db.execute("SELECT entity_id,manager_id FROM projections WHERE snapshot_id=? AND entity_id=?", (snap["id"], focus)).fetchone()
                if not row:
                    raise KeyError("Focus entity not found")
                add(focus)
                cursor = row["manager_id"]
                while cursor and cursor not in seen and len(selected_ids) < min(40, limit):
                    add(cursor)
                    r = db.execute("SELECT manager_id FROM projections WHERE snapshot_id=? AND entity_id=?", (snap["id"], cursor)).fetchone()
                    cursor = r[0] if r else None
            else:
                roots = db.execute("SELECT p.entity_id FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.manager_id IS NULL AND e.kind='person' ORDER BY p.children_count DESC,e.name COLLATE NOCASE,e.id LIMIT ?", (snap["import_id"], snap["id"], min(8, limit))).fetchall()
                for row in roots:
                    add(row[0])
            while queue and len(selected_ids) < limit:
                parent = queue.popleft()
                children = db.execute("SELECT p.entity_id FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.manager_id=? ORDER BY e.name COLLATE NOCASE,e.id LIMIT ?", (snap["import_id"], snap["id"], parent, limit - len(selected_ids))).fetchall()
                for row in children:
                    add(row[0])
            if not focus and len(selected_ids) < limit:
                rows = db.execute("SELECT p.entity_id FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND e.kind='person' ORDER BY e.name COLLATE NOCASE,e.id LIMIT ?", (snap["import_id"], snap["id"], limit)).fetchall()
                for row in rows:
                    add(row[0])
            nodes, edges = [], []
            for ident in selected_ids:
                r = db.execute("SELECT e.data,p.manager_id,p.status,p.children_count,p.assertion_id FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.entity_id=?", (snap["import_id"], snap["id"], ident)).fetchone()
                entity = json.loads(r["data"])
                nodes.append({**entity, "status": r["status"], "manager_id": r["manager_id"], "children_count": r["children_count"], "depth": 0})
                if r["manager_id"] in seen and r["assertion_id"]:
                    a = json.loads(db.execute("SELECT data FROM assertions WHERE snapshot_id=? AND id=?", (snap["id"], r["assertion_id"])).fetchone()[0])
                    edges.append({"id": a["id"], "source": a["object"], "target": a["subject"], "origin": a.get("origin", "model"), "review_status": a.get("review_status", "unreviewed"), "raw_score": a.get("raw_score"), "calibration_status": a.get("calibration_status", "unavailable")})
            parents = {n["id"]: n["manager_id"] for n in nodes}
            for n in nodes:
                cursor = parents.get(n["id"])
                visited = set()
                while cursor in parents and cursor not in visited:
                    visited.add(cursor)
                    n["depth"] += 1
                    cursor = parents[cursor]
            return {"nodes": nodes, "edges": edges, "total_nodes": snap["counts"]["people"], "returned_nodes": len(nodes), "omitted_nodes": max(0, snap["counts"]["people"] - len(nodes)), "snapshot": snap["id"]}

    def chart(self, *, lens="formal", scope=None, person=None, offset=0, limit=60, snapshot=None):
        from .semantic import chart
        return chart(self, lens=lens, scope=scope, person=person, offset=offset, limit=limit, snapshot=snapshot)

    def groups(self, snapshot=None):
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            groups = self._rows(db, "groups_data", snap["id"])
            units = db.execute("SELECT id,name FROM entities WHERE import_id=? AND kind='unit' ORDER BY name", (snap["import_id"],)).fetchall()
            for unit in units:
                rows = db.execute("SELECT data FROM assertions WHERE snapshot_id=? AND relation='member_of' AND object=? ORDER BY subject", (snap["id"], unit["id"])).fetchall()
                memberships = [json.loads(r[0]) for r in rows]
                members = sorted({a["subject"] for a in memberships if eligible(a, snap["as_of"]) and not a.get("stale") and a.get("review_status") != "rejected"})
                groups.append({"id": unit["id"], "name": unit["name"], "kind": "formal", "members": members})
            visible = groups[:200]
            for group in visible:
                group.setdefault("kind", "inferred")
                group.setdefault("name", f"Communication group {group['id']}")
                group["member_count"] = len(group.get("members", []))
                group["members"] = group.get("members", [])[:200]
                group["members_truncated"] = group["member_count"] > 200
            # Resolve only the members already in this bounded response. Use
            # its import so historical groups cannot acquire current names.
            member_ids = sorted({ident for group in visible for ident in group["members"]})
            names = {}
            for offset in range(0, len(member_ids), 400):
                chunk = member_ids[offset:offset + 400]
                rows = db.execute(f"SELECT id,name FROM entities WHERE import_id=? AND id IN ({','.join('?' for _ in chunk)})",
                                  (snap["import_id"], *chunk)).fetchall()
                names.update({row["id"]: row["name"] for row in rows})
            for group in visible:
                group["member_names"] = {ident: names[ident] for ident in group["members"] if ident in names}
            return {"items": visible, "total": len(groups), "snapshot": snap["id"]}

    def _result(self, db, snap):
        projections = db.execute("SELECT entity_id,metrics,unresolved_reason FROM projections WHERE snapshot_id=?", (snap["id"],)).fetchall()
        return {"assertions": self._rows(db, "raw_assertions", snap["id"]), "evidence": self._evidence_records(db, snap["id"]), "groups": self._rows(db, "groups_data", snap["id"]), "metrics": {r["entity_id"]: json.loads(r["metrics"]) for r in projections}, "unresolved": {r["entity_id"]: r["unresolved_reason"] for r in projections if r["unresolved_reason"]}, "model": snap["model"], "run_id": snap.get("inference_run")}

    @staticmethod
    def _check_temporal_cycle(assertion, rows, reviews=(), *, threshold=.55, margin=.08):
        """Check effective parents during each reachable validity interval.

        Traversing all historical assertions invents cycles through superseded
        source links. Resolve review/source/model priority within each interval,
        splitting only at dates reachable along the proposed ancestry.
        """
        candidates = defaultdict(list)
        for a in rows:
            if a.get("relation") != "reports_to" or a.get("reporting_type", "primary") != "primary" or a.get("review_event") or a.get("review_status") == "rejected":
                continue
            if a.get("stale") and a.get("review_status") != "accepted":
                continue
            candidates[a["subject"]].append(a)
        decisions = defaultdict(list)
        for event in active_reviews(reviews):
            decisions[event["subject"]].append(event)

        def parent_at(node, when):
            blocked, forced = False, None
            for event in decisions[node]:
                if not eligible(event, when):
                    continue
                if event["action"] == "reject":
                    blocked, forced = True, None
                elif event["action"] in ("accept", "replace"):
                    blocked, forced = False, event["assertion"]
            if blocked:
                return None
            if forced:
                return forced["object"]
            options = [a for a in candidates[node] if eligible(a, when)]
            documented = [a for a in options if a.get("origin") in ("source", "analyst")]
            if documented:
                parents = {a["object"] for a in documented}
                return next(iter(parents)) if len(parents) == 1 else None
            ranked = sorted(options, key=lambda a: (-float(a.get("raw_score") or 0), a["object"], a["id"]))
            if not ranked:
                return None
            best = ranked[0]
            distinct = next((a for a in ranked[1:] if a["object"] != best["object"]), None)
            if float(best.get("raw_score") or 0) < threshold or best.get("selection_hint") is False:
                return None
            if distinct and float(best.get("raw_score") or 0) - float(distinct.get("raw_score") or 0) < margin:
                return None
            return best["object"]

        undated = not assertion.get("valid_from") and not assertion.get("valid_to")
        start = assertion.get("valid_from") or "0001-01-01"
        end = assertion.get("valid_to") or "9999-12-31"
        todo = [(assertion["object"], start, end)]
        seen = set()
        while todo:
            node, lo, hi = todo.pop()
            if node == assertion["subject"]:
                raise Conflict("This reporting relationship creates a cycle during its effective interval.")
            key = (node, lo, hi)
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 20000:
                raise Conflict("Affected ancestry exceeds the validation budget. Narrow the effective interval.")
            if undated:
                parent = parent_at(node, None)
                if parent:
                    todo.append((parent, lo, hi))
                continue
            boundaries = {lo, hi}
            for row in candidates[node] + decisions[node]:
                for field in ("valid_from", "valid_to"):
                    boundary = row.get(field)
                    if boundary and lo < boundary < hi:
                        boundaries.add(boundary)
            boundaries = sorted(boundaries)
            if len(boundaries) + len(seen) > 20000:
                raise Conflict("Affected ancestry exceeds the validation budget. Narrow the effective interval.")
            for lower, upper in zip(boundaries, boundaries[1:]):
                parent = parent_at(node, lower)
                if parent:
                    todo.append((parent, lower, upper))

    def review(self, request):
        action = request.get("action")
        if action not in ("accept", "reject", "replace", "undo"):
            raise ValueError("Unknown review action")
        reason = str(request.get("reason", "")).strip()
        if not reason or len(reason) > 2000:
            raise ValueError("A review reason of 1–2000 characters is required.")
        with self.lock, self.connection() as db:
            snap = self._snapshot(db)
            key = request.get("idempotency_key")
            if key:
                old = db.execute("SELECT data FROM reviews WHERE import_id=? AND idempotency_key=?", (snap["import_id"], key)).fetchone()
                if old:
                    event = json.loads(old[0])
                    if event.get("request_hash") != digest(request):
                        raise Conflict("Idempotency key already used for a different review.")
                    return {"event": event, "duplicate": True}
            self._check_revision(db, request.get("base_revision"))
            subject = request.get("subject")
            if not db.execute("SELECT 1 FROM entities WHERE import_id=? AND id=? AND kind='person'", (snap["import_id"], subject)).fetchone():
                raise ValueError("Review subject must be a known person.")
            eid = uid("review")
            revision = self._meta(db, "revision") + 1
            event = {"id": eid, "action": action, "subject": subject, "reason": reason, "actor": "local-analyst", "created_at": now(), "seq": revision, "base_revision": request["base_revision"], "request_hash": digest(request), "evidence": []}
            result = self._result(db, snap)
            if action == "undo":
                previous_reviews = self._reviews(db, snap["import_id"])
                before_decisions = active_reviews(previous_reviews)
                target = next((r for r in before_decisions if r["id"] == request.get("event_id") and r["subject"] == subject), None)
                if not target:
                    raise Conflict("Review is missing, already undone, or belongs to another person.")
                event["event_id"] = target["id"]
                resulting_reviews = previous_reviews + [event]
                after_decisions = active_reviews(resulting_reviews)
                before_subject = [r for r in before_decisions if r["subject"] == subject]
                after_subject = [r for r in after_decisions if r["subject"] == subject]
                raw = self._rows(db, "raw_assertions", snap["id"])

                def last_decision(decisions, when):
                    return next((r for r in reversed(decisions) if eligible(r, when)), None)

                # Undo can reactivate an older accepted edit. Validate only
                # intervals whose effective decision actually changes, so undo
                # of an already superseded event remains harmless.
                boundaries = {"0001-01-01", "9999-12-31"}
                for decision in before_subject:
                    boundaries.update(decision[field] for field in ("valid_from", "valid_to") if decision.get(field))
                boundaries = sorted(boundaries)
                if len(boundaries) > 20000:
                    raise Conflict("Affected review history exceeds the validation budget.")
                for lower, upper in zip(boundaries, boundaries[1:]):
                    before = last_decision(before_subject, lower)
                    after = last_decision(after_subject, lower)
                    if before and before["id"] == target["id"] and after and after["action"] in ("accept", "replace"):
                        restored = {**after["assertion"], "valid_from": lower, "valid_to": upper}
                        self._check_temporal_cycle(restored, raw, resulting_reviews, threshold=snap["threshold"], margin=snap["margin"])
                before = last_decision(before_subject, None)
                after = last_decision(after_subject, None)
                if before and before["id"] == target["id"] and after and after["action"] in ("accept", "replace") and not after.get("valid_from") and not after.get("valid_to"):
                    self._check_temporal_cycle(after["assertion"], raw, resulting_reviews, threshold=snap["threshold"], margin=snap["margin"])
            else:
                target = None
                if action in ("accept", "reject"):
                    row = db.execute("SELECT data FROM assertions WHERE snapshot_id=? AND id=? AND subject=? AND relation='reports_to'", (snap["id"], request.get("assertion_id"), subject)).fetchone()
                    if not row:
                        raise ValueError("Choose an existing reporting assertion for this person.")
                    target = json.loads(row[0])
                    if target.get("reporting_type", "primary") != "primary":
                        raise ValueError("This review workflow supports primary reporting only. Matrix relationships remain available as context.")
                    event["assertion_id"] = target["id"]
                else:
                    parent = request.get("object")
                    if parent == subject:
                        raise ValueError("A person cannot report to themselves.")
                    if not db.execute("SELECT 1 FROM entities WHERE import_id=? AND id=? AND kind='person'", (snap["import_id"], parent)).fetchone():
                        raise ValueError("Manager must be a known person; resolve their identity first.")
                    target = {"id": f"human:{eid}", "subject": subject, "object": parent, "relation": "reports_to", "origin": "analyst", "reporting_type": "primary", "valid_from": snap.get("as_of"), "valid_to": None, "raw_score": None, "candidate_probability": None, "selected_probability": None, "calibration_status": "unavailable", "evidence_ids": [f"evidence:{eid}"], "review_status": "accepted", "reason": reason}
                    result["evidence"].append({"id": f"evidence:{eid}", "kind": "analyst_reference", "source_ref": f"review:{eid}", "text": reason, "available": True})
                target = deepcopy(target)
                changed_scope = False
                for field in ("valid_from", "valid_to"):
                    if field in request and request[field] != target.get(field):
                        target[field] = valid_date(request[field])
                        changed_scope = True
                if target.get("valid_from") and target.get("valid_to") and target["valid_from"] >= target["valid_to"]:
                    raise ValueError("Effective end must be later than start.")
                if changed_scope and action == "accept":
                    target.update(origin="analyst", raw_score=None, candidate_probability=None, selected_probability=None, calibration_status="unavailable")
                event.update(semantic=list(semantic(target)), valid_from=target.get("valid_from"), valid_to=target.get("valid_to"), object=target["object"], assertion=target)
                event["evidence"] = [deepcopy(e) for e in result["evidence"] if e["id"] in target.get("evidence_ids", [])]
                if action in ("accept", "replace"):
                    self._check_temporal_cycle(target, self._rows(db, "raw_assertions", snap["id"]), self._reviews(db, snap["import_id"]), threshold=snap["threshold"], margin=snap["margin"])
            db.execute("INSERT INTO reviews VALUES(?,?,?,?,?)", (eid, snap["import_id"], revision, key, dumps(event)))
            self._publish(db, snap["import_id"], result, reason=f"Analyst {action}", as_of=snap["as_of"], threshold=snap["threshold"], margin=snap["margin"], revision=revision, include_sources=False)
        return {"event": event, "workspace": self.workspace()}

    def compare(self, before, after):
        with self.connection() as db:
            a, b = self._snapshot(db, before), self._snapshot(db, after)
            if a["import_id"] != b["import_id"]:
                raise Conflict("Compare snapshots from the same identity/import revision.")
            def state(s):
                return {r["subject"]: json.loads(r["data"]) for r in db.execute("SELECT subject,data FROM assertions WHERE snapshot_id=? AND selected=1", (s,))}
            old, new = state(before), state(after)
            changes = []
            for subject in sorted(old.keys() | new.keys()):
                x, y = old.get(subject), new.get(subject)
                kind = None
                if not x:
                    kind = "relationship_added"
                elif not y:
                    kind = "relationship_removed"
                elif semantic(x) != semantic(y):
                    kind = "manager_changed"
                elif (x.get("valid_from"), x.get("valid_to")) != (y.get("valid_from"), y.get("valid_to")):
                    kind = "validity_changed"
                elif x.get("review_status") != y.get("review_status"):
                    kind = "review_changed"
                elif x.get("raw_score") != y.get("raw_score"):
                    kind = "score_changed"
                if kind:
                    name = db.execute("SELECT name FROM entities WHERE import_id=? AND id=?", (a["import_id"], subject)).fetchone()[0]
                    changes.append({"subject": subject, "subject_name": name, "kind": kind, "before": x, "after": y, "system_cause": b["reason"]})
            return {"before": before, "after": after, "changes": changes[:1000], "total": len(changes), "truncated": len(changes) > 1000, "note": "System snapshot differences do not by themselves establish an organizational reorganization."}

    def withdraw_source(self, source_ref, reason, base_revision):
        if not source_ref or not reason.strip():
            raise ValueError("Source reference and reason required.")
        with self.lock, self.connection() as db:
            self._check_revision(db, base_revision)
            snap = self._snapshot(db)
            db.execute("INSERT OR REPLACE INTO withdrawals VALUES(?,?,?)", (snap["import_id"], source_ref, reason))
            result = self._result(db, snap)
            self._publish(db, snap["import_id"], result, reason="Evidence source withdrawn", as_of=snap["as_of"], threshold=snap["threshold"], margin=snap["margin"], include_sources=False)
        return self.workspace()

    def export_package(self, snapshot=None):
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            dataset = self._dataset(db, snap["import_id"])
            dataset.pop("labels", None)
            withdrawn = {r[0]: r[1] for r in db.execute("SELECT source_ref,reason FROM withdrawals WHERE import_id=?", (snap["import_id"],))}
            for index, message in enumerate(dataset.get("messages", [])):
                if message.get("source_ref") in withdrawn:
                    # Canonical imports may preserve extension fields containing
                    # another copy of the body. Export only structural reference
                    # fields after withdrawal, never those arbitrary extensions.
                    dataset["messages"][index] = {**{k: message[k] for k in ("id", "sender", "to", "cc", "timestamp", "source_ref") if k in message}, "body": "", "subject": "", "available": False}
            dataset["evidence"] = [redact_evidence(e, withdrawn) for e in dataset.get("evidence", [])]
            histories = []
            for r in db.execute("SELECT data FROM snapshots WHERE import_id=? AND revision<=? ORDER BY revision", (snap["import_id"], snap["revision"])).fetchall():
                metadata = json.loads(r[0])
                histories.append({"metadata": metadata, **self._result(db, metadata)})
            reviews = self._reviews(db, snap["import_id"], snap["revision"])
            for event in reviews:
                event["evidence"] = [redact_evidence(e, withdrawn) for e in event.get("evidence", [])]
            return {"format": "orggraph-package", "schema_version": 1, "dataset": dataset, "history": {"snapshots": histories, "reviews": reviews}, "withdrawals": withdrawn, "manifest": {"snapshot": snap["id"], "created_at": now(), "calibration": "Scores are uncalibrated unless explicitly scoped otherwise.", "omissions": ["Training/evaluation labels excluded", "Withdrawn evidence bodies excluded"], "synthetic": bool(dataset["corpus"].get("synthetic")), "projection_policy": "primary-forest-v1"}}

    def restore_package(self, package):
        if package.get("schema_version") != 1 or package.get("format") != "orggraph-package":
            raise ValueError("Unsupported graph package format.")
        from .ingest import parse_bytes
        parsed = parse_bytes(dumps(package["dataset"]).encode(), "dataset.json")
        dataset = parsed["dataset"]
        histories = package.get("history", {}).get("snapshots", [])
        if not histories:
            raise ValueError("Graph package has no snapshot history.")
        with self.lock, self.connection() as db:
            if self._meta(db, "active_snapshot"):
                raise Conflict("Restore graph packages into an empty workspace to preserve their history IDs.")
            iid = uid("import")
            db.execute("INSERT INTO imports VALUES(?,?,?,?,?)", (iid, digest(dataset), dumps(dataset), dumps(parsed["report"]), now()))
            db.executemany("INSERT INTO entities VALUES(?,?,?,?,?,?)", [(iid, e["id"], e["name"], e.get("type", "person"), " ".join(str(e.get(k) or "") for k in ("name", "email", "role", "id")) + " " + " ".join(e.get("aliases", [])), dumps(e)) for e in dataset["entities"]])
            for source, reason in package.get("withdrawals", {}).items():
                db.execute("INSERT INTO withdrawals VALUES(?,?,?)", (iid, source, reason))
            for event in package.get("history", {}).get("reviews", []):
                db.execute("INSERT INTO reviews VALUES(?,?,?,?,?)", (event["id"], iid, event["seq"], None, dumps(event)))
            ids = {e["id"] for e in dataset["entities"]}
            for h in sorted(histories, key=lambda h: h["metadata"]["revision"]):
                meta = h["metadata"]
                for a in h.get("assertions", []):
                    if a["subject"] not in ids or a["object"] not in ids:
                        raise ValueError("Package assertion references an unknown identity.")
                self._publish(db, iid, h, reason=meta["reason"], as_of=meta.get("as_of"), threshold=meta.get("threshold", .55), margin=meta.get("margin", .08), snapshot_id=meta["id"], revision=meta["revision"], include_sources=False, created_at=meta["created_at"])
        return self.workspace()

    def export_chart(self, snapshot=None):
        package = self.export_package(snapshot)
        current = package["history"]["snapshots"][-1]
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            chosen = self._rows(db, "assertions", snap["id"])
        names = {e["id"]: e["name"] for e in package["dataset"]["entities"]}
        selected = {a["subject"]: a for a in chosen if a.get("selected")}
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["employee_id", "employee", "manager_id", "manager", "origin", "review_status", "raw_score_not_probability", "calibration_status", "valid_from", "valid_to", "snapshot", "export_note"])
        def safe(value):
            text = "" if value is None else str(value)
            return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
        for entity in package["dataset"]["entities"]:
            if entity.get("type", "person") != "person":
                continue
            a = selected.get(entity["id"], {})
            writer.writerow([safe(v) for v in [entity["id"], entity["name"], a.get("object"), names.get(a.get("object")), a.get("origin"), a.get("review_status"), a.get("raw_score"), a.get("calibration_status", "unavailable"), a.get("valid_from"), a.get("valid_to"), current["metadata"]["id"], "Lossy primary chart: alternatives, evidence, non-reporting relations and history omitted. Not evaluation truth."]])
        return output.getvalue()

    def export_report(self, snapshot=None):
        with self.connection() as db:
            snap = self._snapshot(db, snapshot)
            rows = db.execute("SELECT e.name,p.unresolved_reason FROM projections p JOIN entities e ON e.id=p.entity_id AND e.import_id=? WHERE p.snapshot_id=? AND p.status='unresolved' ORDER BY e.name LIMIT 30", (snap["import_id"], snap["id"])).fetchall()
            selected = db.execute("SELECT a.data,e.name employee,m.name manager FROM assertions a JOIN entities e ON e.id=a.subject AND e.import_id=? JOIN entities m ON m.id=a.object AND m.import_id=e.import_id WHERE a.snapshot_id=? AND a.selected=1 ORDER BY e.name LIMIT 100", (snap["import_id"], snap["id"])).fetchall()
            def esc(s):
                return str(s).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
            lines = [f"# {esc(snap['corpus']['name'])} organization analysis", "", f"Snapshot: `{snap['id']}`; effective view: {snap['as_of'] or 'undated exploration; not a current-date claim'}.", "", f"Synthetic corpus: {bool(snap['corpus'].get('synthetic'))}. Model: {esc(snap['model'].get('name', 'none'))}.", "", "Model scores are ranking signals, not calibrated probabilities. These results do not establish real-world manager accuracy or target calibration.", "", f"People: {snap['counts']['people']}; selected reporting links: {snap['counts']['selected']}; unresolved: {snap['counts']['unresolved']}; reviewed people: {snap['counts']['reviewed']}.", "", "## Selected reporting assertions", "", "| Employee | Manager | Origin and review | Assertion and evidence |", "| --- | --- | --- | --- |"]
            for row in selected:
                a = json.loads(row["data"])
                lines.append(f"| {esc(row['employee'])} | {esc(row['manager'])} | {esc(a.get('origin'))}; {esc(a.get('review_status', 'unreviewed'))} | `{a['id']}`; {esc(', '.join(a.get('evidence_ids', [])))} |")
            lines += ["", "Table bounded to 100 selected assertions. The canonical package contains full typed relationships, evidence references, and review history.", "", "## Unresolved cases", ""]
            lines += [f"- {esc(r['name'])}: {esc(r['unresolved_reason'])}." for r in rows]
            lines += ["", "Unresolved list bounded to 30. Missing edges are unknown, not proof that an employee has no manager. Source coverage and incomplete archives limit interpretation.", ""]
            return "\n".join(lines)
