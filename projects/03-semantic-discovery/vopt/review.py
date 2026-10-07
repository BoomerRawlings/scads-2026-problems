"""Append-only review decisions bound to immutable extraction fingerprints."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from .io import canonical, digest
from .schema import require, identifier
from .db import Connection

CORRECTIONS = {"model", "variant", "attribute", "value", "value_max", "unit", "qualifier", "conditions", "tolerance"}


def record_fingerprint(record):
    # Paths/run timestamps are deliberately excluded; evidence and processing identity are bound.
    return digest({key: record.get(key) for key in ("document", "sha256", "processing_version", "pages", "assertions")})


class ReviewStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS review_events (event_id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, assertion_id TEXT NOT NULL, fingerprint TEXT NOT NULL, decision TEXT NOT NULL, actor TEXT NOT NULL, actor_kind TEXT NOT NULL, reason TEXT NOT NULL, correction TEXT NOT NULL, created TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS review_lookup ON review_events(doc_id,assertion_id,fingerprint,event_id)")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=Connection)
        db.row_factory = sqlite3.Row
        return db

    def decide(self, record, assertion_id, decision, actor, actor_kind="human", correction=None, reason="", expected_fingerprint=None, expected_event_id=0):
        fingerprint = record_fingerprint(record)
        require(expected_fingerprint == fingerprint, "Stale review: reload the current extraction before deciding")
        require(decision in ("accept", "reject", "correct"), "Unknown review decision")
        require(actor_kind in ("human", "agent", "fixture"), "Unknown reviewer kind")
        require(isinstance(actor, str) and bool(actor.strip()) and len(actor) <= 100, "Reviewer identity required")
        require(isinstance(reason, str) and len(reason) <= 2000, "Invalid review reason")
        require(any(a["assertion_id"] == assertion_id for a in record["assertions"]), "Assertion not in record")
        correction = correction or {}
        require(isinstance(correction, dict) and not (correction.keys() - CORRECTIONS), "Forbidden correction fields")
        require(decision == "correct" or not correction, "Corrections require a correct decision")
        require(decision != "correct" or bool(correction), "Correction fields required")
        if decision in ("accept", "correct"):
            from .schema import validate_review_candidate
            candidate = next(a for a in record["assertions"] if a["assertion_id"] == assertion_id)
            validate_review_candidate({**candidate, **correction}, record["document"])
        doc_id = record["document"]["doc_id"]
        identifier(doc_id, "doc_id")
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            require(type(expected_event_id) is int and expected_event_id >= 0, "Invalid review event token")
            prior = db.execute("SELECT event_id FROM review_events WHERE doc_id=? AND assertion_id=? ORDER BY event_id DESC LIMIT 1", (doc_id, assertion_id)).fetchone()
            require(expected_event_id == (prior[0] if prior else 0), "Review changed: reload the latest decision before replacing it")
            row = db.execute("INSERT INTO review_events(doc_id,assertion_id,fingerprint,decision,actor,actor_kind,reason,correction,created) VALUES (?,?,?,?,?,?,?,?,?)", (doc_id, assertion_id, fingerprint, decision, actor, actor_kind, reason, canonical(correction).decode(), now))
            return {"event_id": row.lastrowid, "fingerprint": fingerprint, "decision": decision}

    def status(self, record):
        import json
        fingerprint = record_fingerprint(record)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM review_events WHERE doc_id=? ORDER BY event_id", (record["document"]["doc_id"],)).fetchall()
        latest = {}
        for row in rows:
            event = dict(row)
            event["correction"] = json.loads(event["correction"])
            latest[event["assertion_id"]] = event
        result = []
        for a in record["assertions"]:
            event = latest.get(a["assertion_id"])
            state = "pending" if event is None else (event["decision"] if event["fingerprint"] == fingerprint else "stale")
            result.append({"assertion": a, "review_status": state, "event": event})
        return {"fingerprint": fingerprint, "items": result}

    def approved(self, record, required_kind=None):
        approved = []
        for item in self.status(record)["items"]:
            if item["review_status"] not in ("accept", "correct"):
                continue
            if required_kind is not None and item["event"]["actor_kind"] != required_kind:
                continue
            a = copy.deepcopy(item["assertion"])
            a.update(item["event"]["correction"])
            a["status"] = "reviewed"
            approved.append(a)
        return approved

    def audit(self, doc_id=None):
        with self.connect() as db:
            if doc_id:
                rows = db.execute("SELECT * FROM review_events WHERE doc_id=? ORDER BY event_id", (doc_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM review_events ORDER BY event_id").fetchall()
        return [dict(row) for row in rows]
