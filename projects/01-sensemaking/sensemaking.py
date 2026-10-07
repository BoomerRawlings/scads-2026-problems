"""Local, evidence-preserving tools for an agent-driven sensemaking workflow.

The tools retrieve and organize evidence. The host agent synthesizes the analysis.
Python 3.11+, standard library only. No model calls or hidden network access.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

DATA = Path(__file__).resolve().parent / "data"
RELATIONS = {"contains", "depends_on", "supplied_by", "reports_to"}


class Workspace:
    def __init__(self, data_dir: Path = DATA):
        self.data_dir = Path(data_dir).resolve()
        self.graph_data = json.loads((self.data_dir / "graph.json").read_text(encoding="utf-8"))
        nodes = self.graph_data["nodes"]
        self.nodes = {n["id"]: n for n in nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("Duplicate entity IDs")
        self._evidence = {}
        # CSV is the portable seed. Every structured retrieval uses SQLite.
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE records (id TEXT PRIMARY KEY, entity_id TEXT, title TEXT, date TEXT, text TEXT, subject TEXT, predicate TEXT, value TEXT)")
        with (self.data_dir / "records.csv").open(encoding="utf-8", newline="") as stream:
            for line_number, row in enumerate(csv.DictReader(stream), 2):
                self.db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)", tuple(row[k] for k in ("id", "entity_id", "title", "date", "text", "subject", "predicate", "value")))
                self._add({"id": row["id"], "entity_ids": [row["entity_id"]], "kind": "record", "title": row["title"], "date": row["date"], "text": row["text"], "source": f"records.csv#row={line_number}", "assertions": [{k: row[k] for k in ("subject", "predicate", "value")}], "extraction": "structured_record"})
        for item in json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8")):
            path = self._safe_path(item["path"])
            self._add({**item, "source": item["path"], "text": path.read_text(encoding="utf-8")})
        for edge in self.graph_data["edges"]:
            if edge["source"] not in self.nodes or edge["target"] not in self.nodes:
                raise ValueError("Dangling graph endpoint")
            if edge["relation"] not in RELATIONS:
                raise ValueError(f"Unsupported relation: {edge['relation']}")
            if not edge.get("evidence_ids") or any(e not in self._evidence for e in edge["evidence_ids"]):
                raise ValueError("Every relationship must cite existing evidence")

    def close(self):
        self.db.close()

    def _safe_path(self, relative: str) -> Path:
        path = (self.data_dir / relative).resolve()
        if not path.is_relative_to(self.data_dir):
            raise ValueError("Evidence paths must remain within data directory")
        return path

    def _add(self, item):
        if item["id"] in self._evidence:
            raise ValueError(f"Duplicate evidence ID: {item['id']}")
        if not item["entity_ids"] or any(i not in self.nodes for i in item["entity_ids"]):
            raise ValueError("Evidence must link to known entities")
        item["sha256"] = hashlib.sha256(item["text"].encode("utf-8")).hexdigest()
        self._evidence[item["id"]] = item

    def entities(self) -> list[dict]:
        return list(self.nodes.values())

    def resolve(self, query: str) -> dict:
        key = query.strip().casefold()
        if not key:
            raise ValueError("An entity ID or exact name is required")
        if key in self.nodes:
            return self.nodes[key]
        matches = [n for n in self.entities() if key in [s.casefold() for s in [n["name"], *n.get("aliases", [])]]]
        if not matches:
            raise ValueError(f"Unknown entity: {query}")
        if len(matches) > 1:
            raise ValueError("Ambiguous entity; choose an ID: " + ", ".join(n["id"] for n in matches))
        return matches[0]

    def graph(self, target: str, max_hops: int = 3) -> dict:
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 0 <= max_hops <= 10:
            raise ValueError("max_hops must be an integer from 0 through 10")
        node = self.resolve(target)
        paths = {node["id"]: [node["id"]]}
        queue = deque([node["id"]])
        edges = []
        while queue:
            current = queue.popleft()
            if len(paths[current]) - 1 >= max_hops:
                continue
            for edge in self.graph_data["edges"]:
                if edge["source"] != current:
                    continue
                edges.append(edge)
                dest = edge["target"]
                if dest not in paths:
                    paths[dest] = paths[current] + [dest]
                    queue.append(dest)
        scope_note = "Directed contains / depends_on / supplied_by edges only. Path inclusion is relevance, not proof of an inherited property."
        if any(edge["relation"] == "reports_to" for edge in edges):
            scope_note = ("Directed contains / depends_on / supplied_by / reports_to edges only. "
                          "reports_to points from employee to manager and preserves attributed source claims, not selected-chart or verified current authority. "
                          "Path inclusion is relevance, not proof of an inherited property.")
        return {"target": node, "max_hops": max_hops, "node_ids": list(paths), "nodes": [self.nodes[i] for i in paths], "edges": edges, "paths": paths, "scope_note": scope_note}

    def search(self, query: str = "", entity_ids: list[str] | None = None) -> list[dict]:
        if entity_ids is not None:
            unknown = set(entity_ids) - self.nodes.keys()
            if unknown:
                raise ValueError("Unknown entity IDs: " + ", ".join(sorted(unknown)))
        tokens = query.casefold().split()
        selected = set(entity_ids) if entity_ids is not None else None
        # Parameterized SQLite scope lookup, never interpolated user SQL.
        if selected is None:
            rows = self.db.execute("SELECT id FROM records ORDER BY id")
        elif selected:
            placeholders = ",".join("?" for _ in selected)
            rows = self.db.execute(f"SELECT id FROM records WHERE entity_id IN ({placeholders}) ORDER BY id", sorted(selected))
        else:
            rows = []
        candidates = [self._evidence[r["id"]] for r in rows]
        candidates += [e for e in self._evidence.values() if e["kind"] != "record" and (selected is None or selected.intersection(e["entity_ids"]))]
        return sorted([e for e in candidates if all(t in (e["title"] + " " + e["text"]).casefold() for t in tokens)], key=lambda e: e["id"])

    def read(self, evidence_id: str) -> dict:
        if evidence_id not in self._evidence:
            raise ValueError(f"Unknown evidence: {evidence_id}")
        return self._evidence[evidence_id]

    def investigate(self, target: str, max_hops: int = 3) -> dict:
        """Deterministic evidence packet, explicitly not autonomous agent reasoning."""
        graph = self.graph(target, max_hops)
        evidence = {e["id"]: e for e in self.search(entity_ids=graph["node_ids"])}
        # Include proofs for graph edges even when their record belongs to another node.
        for edge in graph["edges"]:
            for eid in edge["evidence_ids"]:
                evidence[eid] = self.read(eid)
        claims = defaultdict(lambda: defaultdict(list))
        for e in evidence.values():
            for claim in e.get("assertions", []):
                claims[(claim["subject"], claim["predicate"])][claim["value"]].append(e["id"])
        conflicts = [{"subject": key[0], "predicate": key[1], "alternatives": [{"value": value, "evidence_ids": ids} for value, ids in values.items()], "status": "unresolved", "note": "Different recorded values; dates and scope require agent review. Newer does not automatically mean correct."} for key, values in sorted(claims.items()) if len(values) > 1]
        return {"schema_version": "1.0", "mode": "deterministic_evidence_packet", "graph": graph, "evidence": sorted(evidence.values(), key=lambda e: e["id"]), "conflicts": conflicts, "counts_by_kind": dict(Counter(e["kind"] for e in evidence.values())), "limitations": ["Synthetic authored fixture; not an independent benchmark.", "Assertions and entity links are supplied by the fixture, not extracted by an NLP model.", "Image annotations and video transcripts are authored text; raw-media inspection is a separate tool step.", "This packet is retrieval output. An agent must synthesize and qualify the analytic findings."]}


def evaluate(workspace: Workspace) -> dict:
    """Fixture checks only. No model quality or human time-saving claims."""
    cases = json.loads((workspace.data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        packet = workspace.investigate(case["target"], case["max_hops"])
        actual = {e["id"] for e in packet["evidence"]}
        expected = set(case["expected_evidence_ids"])
        actual_conflicts = {(c["subject"], c["predicate"]) for c in packet["conflicts"]}
        expected_conflicts = {(c["subject"], c["predicate"]) for c in case["expected_conflicts"]}
        results.append({"id": case["id"], "passed": actual == expected and actual_conflicts == expected_conflicts, "missing_evidence": sorted(expected - actual), "extra_evidence": sorted(actual - expected), "missing_conflicts": sorted(expected_conflicts - actual_conflicts), "extra_conflicts": sorted(actual_conflicts - expected_conflicts)})
    return {"evaluation": "authored_fixture_retrieval_and_conflict_regression", "passed": sum(c["passed"] for c in results), "total": len(results), "cases": results, "limitations": "Same authored corpus and oracle; verifies implementation, not generalization, agent quality, or analyst time savings."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("entities")
    for name in ("graph", "investigate"):
        p = sub.add_parser(name)
        p.add_argument("target")
        p.add_argument("--max-hops", type=int, default=3)
    p = sub.add_parser("search")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--entity", action="append", dest="entity_ids")
    p = sub.add_parser("read")
    p.add_argument("evidence_id")
    sub.add_parser("evaluate")
    args = parser.parse_args()
    workspace = None
    try:
        workspace = Workspace(args.data)
        if args.command == "entities": result = workspace.entities()
        elif args.command in ("graph", "investigate"): result = getattr(workspace, args.command)(args.target, args.max_hops)
        elif args.command == "search": result = workspace.search(args.query, args.entity_ids)
        elif args.command == "read": result = workspace.read(args.evidence_id)
        else: result = evaluate(workspace)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if args.command == "evaluate" and result["passed"] != result["total"] else 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    finally:
        if workspace: workspace.close()


if __name__ == "__main__":
    raise SystemExit(main())
