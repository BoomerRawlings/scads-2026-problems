"""Read-only dataset preparation followed by an explicit, revision-checked build.

Preparation jobs are ephemeral: restarting the server discards uncommitted data.
The existing workspace is touched only after the analyst reviews the plan.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import math
import re
import threading
import time
import uuid

from .demo import demo_dataset
from .ingest import EVIDENCE_KINDS, parse_bytes
from .store import Conflict, dumps, now, valid_date


UPLOAD_LIMIT = 100 * 1024 * 1024
STAGES = (("inspect", "Inspect source"), ("profile", "Measure coverage"),
          ("plan", "Plan the graph"), ("database", "Save dataset"),
          ("infer", "Analyze connections"), ("ready", "Open the chart"))


def validate_package(package, dataset):
    """Check history structure in memory before the atomic restore is offered."""
    if package.get("schema_version") != 1 or package.get("format") != "orggraph-package":
        raise ValueError("Unsupported graph package format.")
    history = package.get("history")
    if not isinstance(history, dict) or not isinstance(history.get("snapshots"), list) or not history["snapshots"]:
        raise ValueError("Graph package requires preserved snapshot history.")
    ids = {e["id"] for e in dataset["entities"]}
    message_ids = {m["id"] for m in dataset.get("messages", [])}

    def records(value, label):
        if not isinstance(value, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in value):
            raise ValueError(f"Package {label} must contain records with nonempty IDs.")
        if len({item["id"] for item in value}) != len(value):
            raise ValueError(f"Package {label} contains duplicate IDs.")
        return value

    def assertion(item):
        if not isinstance(item, dict) or any(item.get(key) not in ids for key in ("subject", "object")):
            raise ValueError("Package assertion references an unknown identity.")
        if not isinstance(item.get("relation"), str) or not item["relation"]:
            raise ValueError("Package assertion requires a relation.")
        for field in ("valid_from", "valid_to"):
            valid_date(item.get(field))
        for field in ("raw_score", "candidate_probability", "selected_probability"):
            value = item.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError("Package assertion scores must be finite values from 0 to 1 or null.")
        if not isinstance(item.get("evidence_ids", []), list) or any(not isinstance(value, str) for value in item.get("evidence_ids", [])):
            raise ValueError("Package assertion evidence IDs must be a list.")

    def evidence_records(value, label):
        for item in records(value, label):
            if item.get("kind") not in EVIDENCE_KINDS or not isinstance(item.get("available", True), bool):
                raise ValueError("Package evidence has an unsupported kind or availability flag.")
            if not isinstance(item.get("details", {}), dict):
                raise ValueError("Package evidence details must be an object.")
            sources = item.get("details", {}).get("source_refs", [])
            if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
                raise ValueError("Package evidence source references must be a list of strings.")
            if item.get("source_ref") is not None and not isinstance(item["source_ref"], str):
                raise ValueError("Package evidence source reference must be a string or null.")
            messages = item.get("message_ids", [])
            if not isinstance(messages, list) or any(not isinstance(value, str) for value in messages):
                raise ValueError("Package evidence message references must be a list of strings.")
            if item.get("available", True) and any(value not in message_ids for value in messages):
                raise ValueError("Available package evidence refers to missing messages.")
            if item.get("text") is not None and not isinstance(item["text"], str):
                raise ValueError("Package evidence text must be a string or null.")

    snapshot_ids, revisions = set(), set()
    for snapshot in history["snapshots"]:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("metadata"), dict):
            raise ValueError("Package snapshot requires metadata.")
        metadata = snapshot["metadata"]
        revision = metadata.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0 or revision in revisions:
            raise ValueError("Package snapshot revisions must be unique positive integers.")
        revisions.add(revision)
        for field in ("id", "reason", "created_at"):
            if not isinstance(metadata.get(field), str) or not metadata[field]:
                raise ValueError(f"Package snapshot requires {field}.")
        if metadata["id"] in snapshot_ids:
            raise ValueError("Package snapshot IDs must be unique.")
        snapshot_ids.add(metadata["id"])
        valid_date(metadata.get("as_of"))
        for field in ("threshold", "margin"):
            value = metadata.get(field, .55 if field == "threshold" else .08)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
                raise ValueError("Package inference parameters must be finite values from 0 to 1.")
        for item in records(snapshot.get("assertions", []), "assertions"):
            assertion(item)
        evidence_records(snapshot.get("evidence", []), "evidence")
        for group in records(snapshot.get("groups", []), "groups"):
            members = group.get("members", [])
            if not isinstance(members, list) or any(not isinstance(member, str) or member not in ids for member in members):
                raise ValueError("Package group members must reference imported entities.")
        for field in ("metrics", "model", "unresolved"):
            if not isinstance(snapshot.get(field, {}), dict):
                raise ValueError(f"Package {field} must be an object.")
        if any(not isinstance(value, dict) for value in snapshot.get("metrics", {}).values()):
            raise ValueError("Package per-person metrics must be objects.")
    reviews = records(history.get("reviews", []), "reviews")
    review_ids = {review["id"] for review in reviews}
    for review in reviews:
        if review.get("subject") not in ids or review.get("action") not in {"accept", "reject", "replace", "undo"}:
            raise ValueError("Package review requires a known subject and supported action.")
        if isinstance(review.get("seq"), bool) or not isinstance(review.get("seq"), int) or review["seq"] not in revisions:
            raise ValueError("Package review must refer to a saved snapshot revision.")
        if review["action"] == "undo":
            if review.get("event_id") not in review_ids or review["event_id"] == review["id"]:
                raise ValueError("Package undo references an unknown review.")
        else:
            assertion(review.get("assertion"))
            if not isinstance(review.get("semantic"), list) or len(review["semantic"]) != 4:
                raise ValueError("Package review requires its original relationship signature.")
        evidence_records(review.get("evidence", []), "review evidence")
    withdrawals = package.get("withdrawals", {})
    if not isinstance(withdrawals, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in withdrawals.items()):
        raise ValueError("Package withdrawals must map source references to reasons.")


def dataset_profile(dataset, report):
    """Exact normalized-record coverage, without drawing authority conclusions."""
    entities = dataset.get("entities", [])
    people = [e for e in entities if e.get("type", "person") == "person"]
    messages = dataset.get("messages", [])
    assertions = dataset.get("assertions", [])
    evidence = dataset.get("evidence", [])
    labels = dataset.get("labels", [])
    kinds = Counter(e.get("type", "person") for e in entities)
    pairs = set()
    events = 0
    for message in messages:
        recipients = set(message.get("to", []) + message.get("cc", [])) - {message["sender"]}
        events += len(recipients)
        pairs.update((message["sender"], recipient) for recipient in recipients)
    counts = {"entities": len(entities), "people": len(people), "units": kinds["unit"],
              "shared_mailboxes": kinds["shared_mailbox"], "messages": len(messages),
              "assertions": len(assertions), "evidence": len(evidence), "labels": len(labels),
              "data_points": len(entities) + len(messages) + len(assertions) + len(evidence),
              "communication_links": len(pairs), "communication_events": events}
    fields = []
    for key, label, rows, predicate in (
        ("names", "Person names", people, lambda r: r.get("name")),
        ("emails", "Person email addresses", people, lambda r: r.get("email")),
        ("roles", "Position titles", people, lambda r: r.get("role")),
        ("units", "Person department references", people, lambda r: r.get("unit_id")),
        ("senders", "Message senders", messages, lambda r: r.get("sender")),
        ("recipients", "Message recipients", messages, lambda r: r.get("to") or r.get("cc")),
        ("timestamps", "Message timestamps", messages, lambda r: r.get("timestamp")),
        ("bodies", "Message bodies", messages, lambda r: bool((r.get("body") or "").strip())),
        ("subjects", "Message subjects", messages, lambda r: bool((r.get("subject") or "").strip())),
    ):
        present = sum(bool(predicate(row)) for row in rows)
        fields.append({"id": key, "label": label, "present": present, "missing": len(rows) - present, "total": len(rows)})
    times = [m["timestamp"] for m in messages if m.get("timestamp")]
    relation_counts = Counter(a["relation"] for a in assertions)
    notes = ["Counts describe accepted source records; a communication link is a distinct directed sender–recipient pair, not a reporting relationship.",
             "Data points count entities, messages, assertions and evidence. Evaluation labels are counted separately and excluded from inference.",
             "People are distinct imported identities. Missing or ambiguous identity records may change the real number of individuals.",
             "Coverage describes normalized fields. Names may be derived from email addresses; populated names are not verified identities.",
             "The preview contains supplied relationships only. Any new reporting proposals are produced during analysis; imported assertion origins are preserved."]
    if not messages:
        notes.append("No messages are available. Analysis can preserve supplied reporting links, but cannot infer communication-based authority.")
    if dataset.get("corpus", {}).get("synthetic"):
        notes.append("This is a fictional workflow fixture, not independent evidence of real-world model accuracy.")
    issues = report.get("issues", [])
    return {"counts": counts, "fields": fields,
            "relations": [{"relation": relation, "count": count} for relation, count in sorted(relation_counts.items())],
            "quality": {**{key: report.get(key, 0) for key in ("read", "accepted", "duplicate", "quarantined", "unsupported")},
                        "issue_count": len(issues), "issues": [{"code": str(i.get("code", "warning")), "reason": str(i.get("reason", ""))[:300]} for i in issues[:20]]},
            "notes": notes, "timestamp_start": min(times) if times else None, "timestamp_end": max(times) if times else None}


def graph_plan(dataset, *, max_nodes=24, max_edges=40):
    """Bounded source sample, separate from a predicted organizational chart."""
    entities = dataset.get("entities", [])
    by_id = {e["id"]: e for e in entities}
    chosen, edges, seen_edges = {}, [], set()

    def add_edge(source, target, relation, origin):
        if source not in by_id or target not in by_id or source == target:
            return
        key = (source, target, relation)
        if key in seen_edges or len(edges) >= max_edges:
            return
        missing = {source, target} - chosen.keys()
        if len(chosen) + len(missing) > max_nodes:
            return
        for ident in (source, target):
            entity = by_id[ident]
            chosen.setdefault(ident, {"id": ident, "label": entity["name"], "kind": entity.get("type", "person")})
        edges.append({"source": source, "target": target, "relation": relation, "origin": origin})
        seen_edges.add(key)

    for assertion in dataset.get("assertions", []):
        add_edge(assertion["subject"], assertion["object"], assertion["relation"], assertion.get("origin", "source"))
        if len(edges) >= max_edges:
            break
    for message in dataset.get("messages", []):
        for recipient in dict.fromkeys(message.get("to", []) + message.get("cc", [])):
            add_edge(message["sender"], recipient, "communicates_with", "message")
        if len(edges) >= max_edges:
            break
    for entity in entities:
        if len(chosen) >= max_nodes:
            break
        chosen.setdefault(entity["id"], {"id": entity["id"], "label": entity["name"], "kind": entity.get("type", "person")})
    return {"nodes": list(chosen.values()), "edges": edges, "sampled": True,
            "sample_nodes": len(chosen), "total_nodes": len(entities), "sample_edges": len(edges),
            "total_source_relations": len(dataset.get("assertions", [])),
            "note": "Bounded sample of supplied records; communication and membership do not establish formal authority. Supplied model assertions remain unverified proposals. Evaluation labels are not drawn."}


class IntakeManager:
    """At most one worker and two retained jobs; inactive jobs expire in 30 min."""

    def __init__(self, store, *, ttl=1800, capacity=2):
        self.store = store
        self.ttl = ttl
        self.capacity = capacity
        self.lock = threading.RLock()
        self.jobs = {}
        self.running = set()

    def _cleanup(self):
        expired = [ident for ident, job in self.jobs.items()
                   if ident not in self.running and time.monotonic() - job["_touched"] > self.ttl]
        for ident in expired:
            del self.jobs[ident]

    @staticmethod
    def _public(job):
        return deepcopy({key: value for key, value in job.items() if not key.startswith("_")})

    def _workspace(self, fingerprint=None, package=False):
        # Existing database is read only here. No Store is created for preflight.
        with self.store.lock, self.store.connection() as db:
            revision = self.store._meta(db, "revision", 0)
            active = self.store._meta(db, "active_snapshot")
            same, reusable = False, False
            if active:
                snapshot = self.store._snapshot(db)
                current_digest = db.execute("SELECT digest FROM imports WHERE id=?", (snapshot["import_id"],)).fetchone()[0]
                same = fingerprint is not None and fingerprint == current_digest
                reusable = same and snapshot.get("model", {}).get("id", "none") != "none"
            return {"base_revision": revision, "occupied": bool(active), "same_dataset": same,
                    "requires_replacement": bool(active) and not same,
                    "can_reuse": reusable and not package, "package_requires_empty": bool(active) and package}

    @staticmethod
    def _validate_request_key(request_key):
        if request_key is not None and (not isinstance(request_key, str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_key)):
            raise ValueError("Inspection request key must contain 8–128 letters, digits, underscores or hyphens.")

    def _new(self, mode, source, loader, *, request_key=None, request_signature=None):
        self._validate_request_key(request_key)
        with self.lock:
            self._cleanup()
            if request_key is not None:
                previous = next((job for job in self.jobs.values() if job.get("_request_key") == request_key), None)
                if previous:
                    if previous["_request_signature"] != request_signature:
                        raise Conflict("This inspection request key was already used for another dataset. Start a new inspection.")
                    previous["_touched"] = time.monotonic()
                    return self._public(previous)
            if self.running:
                raise Conflict("Another intake is running. Wait for it to finish before preparing another dataset.")
            if len(self.jobs) >= self.capacity:
                removable = [j for j in self.jobs.values() if j["status"] in ("ready", "failed", "cancelled")]
                if not removable:
                    raise Conflict("Two dataset previews are already open. Cancel one before preparing another.")
                del self.jobs[min(removable, key=lambda j: j["_touched"])["id"]]
            ident = "intake_" + uuid.uuid4().hex
            job = {"id": ident, "mode": mode, "status": "profiling", "source": source,
                   "stages": [{"id": ident, "label": label, "status": "queued", "detail": ""} for ident, label in STAGES],
                   "profile": None, "plan": None, "workspace": self._workspace(), "result": None,
                   "error": None, "retryable": False, "created_at": now(), "_touched": time.monotonic(), "_payload": None,
                   "_request_key": request_key, "_request_signature": request_signature}
            self.jobs[ident] = job
            self._start(ident, lambda: self._prepare(ident, loader))
            return self._public(job)

    def synthetic(self, people=10000, *, request_key=None):
        if isinstance(people, bool) or not isinstance(people, int) or not 72 <= people <= 100000:
            raise ValueError("Synthetic size must be an integer from 72 to 100,000 people.")

        def generate():
            dataset = demo_dataset(person_count=people)
            count = sum(len(dataset.get(k, [])) for k in ("entities", "messages", "assertions", "evidence", "labels"))
            return {"dataset": dataset, "report": {"read": count, "accepted": count, "duplicate": 0,
                    "quarantined": 0, "unsupported": 0, "issues": [], "note": "Deterministic fictional corpus; not real-world validation."}}

        return self._new("synthetic", {"name": f"Meridian · {people:,} people", "format": "synthetic", "bytes": None, "requested_people": people}, generate,
                         request_key=request_key, request_signature=("synthetic", people))

    def upload(self, data, filename, *, request_key=None):
        if len(data) > UPLOAD_LIMIT:
            raise ValueError("Upload limit is 100 MiB. Use the CLI for larger archives.")
        name = Path(filename.replace("\\", "/")).name[:255] or "upload.json"
        return self._new("import", {"name": name, "format": Path(name).suffix.lower().lstrip(".") or "unknown", "bytes": len(data)},
                         lambda: parse_bytes(data, name), request_key=request_key,
                         request_signature=("import", name, hashlib.sha256(data).hexdigest()) if request_key is not None else None)

    def _start(self, ident, action):
        self.running.add(ident)

        def run():
            try:
                action()
            finally:
                with self.lock:
                    self.running.discard(ident)
        threading.Thread(target=run, name="orggraph-intake", daemon=True).start()

    def _stage(self, ident, stage_id, status, detail):
        with self.lock:
            job = self.jobs[ident]
            if job["status"] == "cancelled":
                return False
            stage = next(stage for stage in job["stages"] if stage["id"] == stage_id)
            stage.update(status=status, detail=detail)
            if status == "running":
                stage["started_at"] = now()
                stage.pop("finished_at", None)
            else:
                stage["finished_at"] = now()
            job["_touched"] = time.monotonic()
            return True

    def _prepare(self, ident, loader):
        try:
            self._stage(ident, "inspect", "running", "Reading and normalizing source records in memory.")
            parsed = loader()
            dataset = parsed["dataset"]
            if not dataset.get("entities"):
                issues = parsed.get("report", {}).get("issues", [])
                reason = issues[0].get("reason") if issues else "No usable entities found. Check the format and required fields."
                raise ValueError(reason)
            if not self._stage(ident, "inspect", "complete", "Source normalized; no dataset records saved yet."):
                return
            self._stage(ident, "profile", "running", "Counting identities, records, available fields and missing information.")
            profile = dataset_profile(dataset, parsed["report"])
            with self.lock:
                if self.jobs[ident]["status"] == "cancelled":
                    return
                self.jobs[ident]["profile"] = profile
            self._stage(ident, "profile", "complete", f"{profile['counts']['people']:,} people and {profile['counts']['data_points']:,} data points measured.")
            self._stage(ident, "plan", "running", "Preparing a bounded source graph and checking workspace compatibility.")
            plan = graph_plan(dataset)
            canonical = dumps(dataset).encode("utf-8")
            fingerprint = hashlib.sha256(canonical).hexdigest()
            canonical_bytes = len(canonical)
            del canonical
            package = parsed.get("package", {}).get("format") == "orggraph-package"
            if package:
                validate_package(parsed["package"], dataset)
            workspace = self._workspace(fingerprint, package)
            with self.lock:
                job = self.jobs[ident]
                if job["status"] == "cancelled":
                    return
                job.update(plan=plan, workspace=workspace, _payload=parsed, _fingerprint=fingerprint)
                job["profile"]["canonical_bytes"] = canonical_bytes
                if job["mode"] == "synthetic":
                    job["source"]["bytes"] = canonical_bytes
                self._stage(ident, "plan", "complete", "Review the source coverage and plan before saving dataset records.")
                job.update(status="ready_for_review", _touched=time.monotonic())
        except Exception as exc:
            self._failed(ident, exc, retryable=False)

    def _failed(self, ident, exc, *, retryable):
        with self.lock:
            job = self.jobs[ident]
            if job["status"] == "cancelled":
                return
            for stage in job["stages"]:
                if stage["status"] == "running":
                    stage.update(status="error", detail=str(exc), finished_at=now())
            job.update(status="failed", error=str(exc), retryable=retryable, _touched=time.monotonic())
            if not retryable:
                job["_payload"] = None

    def get(self, ident):
        with self.lock:
            self._cleanup()
            if ident not in self.jobs:
                raise KeyError("Intake preview expired or was not found. Prepare the dataset again.")
            self.jobs[ident]["_touched"] = time.monotonic()
            return self._public(self.jobs[ident])

    def get_request(self, request_key):
        """Recover a prepared request even when the initial POST reply was lost."""
        if request_key is None:
            raise ValueError("An inspection request key is required for recovery.")
        self._validate_request_key(request_key)
        with self.lock:
            self._cleanup()
            job = next((job for job in self.jobs.values() if job.get("_request_key") == request_key), None)
            if job is None:
                raise KeyError("Intake preview expired or was not found. Prepare the dataset again.")
            job["_touched"] = time.monotonic()
            return self._public(job)

    def cancel(self, ident):
        with self.lock:
            self.get(ident)
            job = self.jobs[ident]
            if job["status"] in ("building", "ready"):
                raise Conflict("Dataset saving has started. It cannot be rolled back by cancelling this preview.")
            job.update(status="cancelled", _payload=None, retryable=False)
            for stage in job["stages"]:
                if stage["status"] in ("queued", "running"):
                    stage.update(status="skipped", detail="Preview cancelled before saving.")
            return self._public(job)

    def build(self, ident, *, base_revision, replace=False):
        with self.lock:
            self.get(ident)
            job = self.jobs[ident]
            if job["status"] == "ready":
                return self._public(job)
            if self.running:
                raise Conflict("An intake is still running. Wait before starting another step.")
            if job["status"] != "ready_for_review" and not (job["status"] == "failed" and job["retryable"]):
                raise Conflict("Prepare and review this dataset before saving it.")
            parsed = job["_payload"]
            package = parsed.get("package", {}).get("format") == "orggraph-package"
            workspace = self._workspace(job["_fingerprint"], package)
            if base_revision != workspace["base_revision"]:
                job["workspace"] = workspace
                raise Conflict("Workspace changed since this preview. Review the current workspace revision and retry.")
            if workspace["package_requires_empty"]:
                raise Conflict("Graph packages must be restored into an empty workspace to preserve history IDs.")
            if workspace["requires_replacement"] and not replace:
                raise Conflict("Explicit replacement is required. Existing snapshots and reviews will be preserved.")
            job.update(status="building", error=None, retryable=False, workspace=workspace)
            self._start(ident, lambda: self._build(ident, base_revision, replace))
            return self._public(job)

    def _build(self, ident, base_revision, replace):
        job = self.jobs[ident]
        parsed = job["_payload"]
        try:
            self._stage(ident, "database", "running", "Saving canonical records with revision checks; preserving earlier snapshots.")
            package = parsed.get("package", {}).get("format") == "orggraph-package"
            if package:
                with self.store.lock:
                    with self.store.connection() as db:
                        self.store._check_revision(db, base_revision)
                    workspace = self.store.restore_package(parsed["package"])
                self._stage(ident, "database", "complete", "Restored dataset, snapshots and analyst history.")
                self._stage(ident, "infer", "skipped", "Preserved the package's published analysis and analyst corrections.")
            else:
                # Capture the imported snapshot under the same lock. Another
                # write must never make this intake infer a different corpus.
                with self.store.lock:
                    outcome = self.store.import_dataset(parsed["dataset"], parsed["report"], replace=replace, base_revision=base_revision)
                    workspace = self.store.workspace()
                    if workspace["active_snapshot"] != outcome["snapshot"]:
                        raise Conflict("Workspace changed while saving. Review the current dataset before retrying.")
                self._stage(ident, "database", "complete", "Reused identical saved records." if outcome["duplicate"] else "Canonical dataset saved. Earlier snapshots remain available.")
                if outcome["duplicate"] and (workspace.get("model") or {}).get("id", "none") != "none":
                    self._stage(ident, "infer", "skipped", "Reused existing analysis and analyst corrections for this identical dataset.")
                else:
                    self._stage(ident, "infer", "running", "Analyzing communication evidence; evaluation labels are excluded from model input.")
                    outcome = self.store.run_inference(base_revision=workspace["revision"])
                    if outcome["job"]["state"] != "complete":
                        raise Conflict("Analysis was cancelled before publication. Saved source records remain available for retry.")
                    workspace = outcome["workspace"]
                    if workspace["active_snapshot"] != outcome["job"]["snapshot"]:
                        raise Conflict("Workspace changed after analysis. The completed snapshot was preserved; review the current dataset before retrying.")
                    self._stage(ident, "infer", "complete", f"Published {workspace['counts']['selected']:,} selected reporting links; unresolved positions remain explicit.")
            self._stage(ident, "ready", "running", "Preparing the published chart and evidence explorer.")
            with self.lock:
                current = self._workspace(job["_fingerprint"], package)
                if current["base_revision"] != workspace["revision"]:
                    raise Conflict("Workspace changed before this chart opened. Review the current dataset before retrying.")
                job.update(result=workspace, workspace=current)
                self._stage(ident, "ready", "complete", "Chart ready. Inspect evidence and uncertainty before accepting inferred authority.")
                job.update(status="ready", _payload=None, _touched=time.monotonic())
        except Exception as exc:
            with self.lock:
                job["workspace"] = self._workspace(job["_fingerprint"], parsed.get("package", {}).get("format") == "orggraph-package")
            self._failed(ident, exc, retryable=True)
