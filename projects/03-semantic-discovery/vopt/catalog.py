"""Atomic SQLite metadata snapshots, monotonic policy, and revocation-safe rollback."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
from .io import canonical
from .schema import require, validate_bundle
from .db import Connection


class Catalog:
    def __init__(self, path, readonly=False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        if readonly:
            require(self.path.is_file(), "Catalog does not exist")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS assertions (assertion_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, model TEXT NOT NULL, attribute TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS assertions_doc ON assertions(doc_id,model,attribute)")
            db.execute("CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS catalog_history (sequence INTEGER PRIMARY KEY, bundle TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS catalog_events (event_id INTEGER PRIMARY KEY, action TEXT NOT NULL, sequence INTEGER NOT NULL, integrity TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    def connect(self):
        if self.readonly:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=15, factory=Connection)
        else:
            db = sqlite3.connect(self.path, timeout=15, factory=Connection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        if not self.readonly:
            db.execute("PRAGMA secure_delete=ON")
        return db

    @staticmethod
    def _meta(db):
        return {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key,value FROM catalog_meta")}

    @staticmethod
    def _set(db, key, value):
        db.execute("INSERT INTO catalog_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, canonical(value).decode()))

    @staticmethod
    def _safe_under_policy(bundle, policy, profile):
        require(not (set(policy["revoked_doc_ids"]) & {d["doc_id"] for d in bundle["documents"]}), "Rollback/import would restore a revoked document")
        require(not (set(policy["revoked_assertion_ids"]) & {a["assertion_id"] for a in bundle["assertions"]}), "Rollback/import would restore a revoked assertion")
        require(not (profile == "coverage" and bundle["profile"] == "values"), "Rollback would restore withdrawn specification values")

    def _replace(self, db, bundle):
        from .search import build_index
        db.execute("DELETE FROM assertions")
        db.execute("DELETE FROM documents")
        db.executemany("INSERT INTO documents(doc_id,data) VALUES (?,?)", [(d["doc_id"], canonical(d).decode()) for d in bundle["documents"]])
        db.executemany("INSERT INTO assertions(assertion_id,doc_id,model,attribute,data) VALUES (?,?,?,?,?)", [(a["assertion_id"], a["doc_id"], a["model"], a["attribute"], canonical(a).decode()) for a in bundle["assertions"]])
        build_index(db, bundle["documents"], bundle["assertions"])
        for key, value in {"catalog_id": bundle["catalog_id"], "active_sequence": bundle["sequence"], "profile": bundle["profile"], "integrity": bundle["integrity"]}.items():
            self._set(db, key, value)

    def import_bundle(self, bundle):
        require(not self.readonly, "Read-only discovery cannot import catalogs")
        validate_bundle(bundle)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            meta = self._meta(db)
            if meta:
                require(bundle["catalog_id"] == meta["catalog_id"], "Catalog identity mismatch")
                high = meta["highest_sequence"]
                if bundle["sequence"] == meta["active_sequence"] and bundle["integrity"] == meta["integrity"]:
                    return {"status": "unchanged", "sequence": bundle["sequence"]}
                require(bundle["sequence"] > high, "Stale/replayed sequence; new imports must increase the high-water sequence")
                old_policy, new_policy = meta["effective_policy"], bundle["policy"]
                require(new_policy["version"] >= old_policy["version"], "Release policy cannot go backwards")
                for key in ("revoked_doc_ids", "revoked_assertion_ids"):
                    require(set(old_policy[key]) <= set(new_policy[key]), "Revocations cannot be removed")
                changed_policy = old_policy != new_policy or bundle["profile"] != meta["permitted_profile"]
                require(not changed_policy or new_policy["version"] > old_policy["version"], "Policy/profile changes require a newer policy version")
            self._replace(db, bundle)
            self._set(db, "highest_sequence", bundle["sequence"])
            self._set(db, "effective_policy", bundle["policy"])
            self._set(db, "permitted_profile", bundle["profile"])
            db.execute("INSERT INTO catalog_history(sequence,bundle) VALUES (?,?)", (bundle["sequence"], canonical(bundle).decode()))
            # Retain only snapshots eligible under current revocations and field-release mode.
            for row in list(db.execute("SELECT sequence,bundle FROM catalog_history")):
                prior = json.loads(row["bundle"])
                try:
                    self._safe_under_policy(prior, bundle["policy"], bundle["profile"])
                except ValueError:
                    db.execute("DELETE FROM catalog_history WHERE sequence=?", (row["sequence"],))
            db.execute("INSERT INTO catalog_events(action,sequence,integrity) VALUES ('import',?,?)", (bundle["sequence"], bundle["integrity"]))
        return {"status": "imported", "sequence": bundle["sequence"], "documents": len(bundle["documents"]), "assertions": len(bundle["assertions"])}

    def rollback(self, sequence):
        require(not self.readonly, "Read-only discovery cannot roll back catalogs")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            meta = self._meta(db)
            row = db.execute("SELECT bundle FROM catalog_history WHERE sequence=?", (sequence,)).fetchone()
            require(row is not None, "No eligible snapshot for that sequence; it may have been revoked")
            bundle = validate_bundle(json.loads(row["bundle"]))
            self._safe_under_policy(bundle, meta["effective_policy"], meta["permitted_profile"])
            self._replace(db, bundle)
            db.execute("INSERT INTO catalog_events(action,sequence,integrity) VALUES ('rollback',?,?)", (sequence, bundle["integrity"]))
        return {"status": "rolled_back", "sequence": sequence}

    def info(self):
        with self.connect() as db:
            db.execute("BEGIN")
            meta = self._meta(db)
            meta["document_count"] = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            meta["assertion_count"] = db.execute("SELECT COUNT(*) FROM assertions").fetchone()[0]
            meta["eligible_snapshots"] = [r[0] for r in db.execute("SELECT sequence FROM catalog_history ORDER BY sequence")]
        return meta

    def search(self, query, limit=10, method="lexical"):
        from .search import search
        with self.connect() as db:
            db.execute("BEGIN")  # One snapshot across metadata, assertions, and both derived indexes.
            require(bool(self._meta(db)), "No metadata bundle imported")
            return search(db, query, limit=limit, method=method)

    def options(self):
        from .guidance import search_options
        with self.connect() as db:
            db.execute("BEGIN")
            meta = self._meta(db)
            require(bool(meta), "No metadata bundle imported")
            return search_options(db, meta)
