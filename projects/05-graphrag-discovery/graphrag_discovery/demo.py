"""Authored pump-history demonstration. No remote calls or model inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .records import DomainError, utc


class SimulatedClock:
    """Explicit test clock, used only by this demonstration entry point."""

    def __init__(self, value: str):
        self.value = utc(value)

    def set(self, value: str) -> None:
        normalized = utc(value)
        if normalized < self.value:
            raise DomainError("invalid_demo_clock", "Fixture clock cannot move backward", {})
        self.value = normalized

    def __call__(self) -> str:
        return self.value


def _id(result: Any, name: str) -> str:
    if not isinstance(result, dict) or not isinstance(result.get(name), str):
        raise DomainError("demo_contract_error", f"Service result lacks {name}", {})
    return result[name]


def _assertion_ids(result: dict[str, Any]) -> set[str]:
    return {item["assertion_id"] for item in result.get("items", []) if item.get("assertion_id")}


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GraphRAG authored-fixture demonstration", "",
        "**Simulated UTC history; fictional public text; authored assertions.** No LLM extraction, "
        "embeddings, real-data discovery accuracy, or scale performance is demonstrated.", "",
        "SQLite reference engine: lexical matching and bounded traversal over authored assertions. "
        "Comparison reports endpoint-state differences; intermediate ledger-event enumeration is not implemented.", "",
        "Five batches preserve initial reporting, a plan, a late correction, a conflicting report, "
        "and withdrawal. Ingestion, assertion preparation, and publication use distinct fixture times.", "",
        "## Published snapshots", "", "| Batch | Snapshot | Simulated publication |",
        "| --- | --- | --- |",
    ]
    for batch in report["batches"]:
        lines.append(f"| {batch['batch_id']} | `{batch['snapshot_id']}` | {batch['published_at']} |")
    lines.extend(["", "## Observed temporal queries", ""])
    for name, query in report["queries"].items():
        lines.extend([f"### {name.replace('_', ' ')}", ""])
        items = [item for item in query.get("items", []) if item.get("assertion_id")]
        if not items:
            lines.append("No assertion returned within this query's scope.")
        for item in items:
            text = str(item.get("text", "")).replace("\n", " ")
            citation = item.get("evidence", {})
            lines.append(
                f"- `{item['assertion_id']}`: {text} "
                f"(modality: {item.get('modality', 'unknown')}; disputed: {item.get('disputed', False)}). "
                f"Source: `{citation.get('document_id', '?')}/{citation.get('version_id', '?')}`, "
                f"span [{citation.get('start', '?')}, {citation.get('end', '?')})."
            )
        if query.get("truncated"):
            lines.append("Results are partial; inspect scope/usage in report.json.")
        lines.append("")
    lines.extend(["## Baseline comparisons", ""])
    for name, comparison in report["comparisons"].items():
        categories = sorted({
            str(category)
            for change in comparison.get("changes", [])
            for category in change.get("categories", [change.get("category", "unclassified")])
        })
        lines.append(
            f"- {name.replace('_', ' ')}: {len(comparison.get('changes', []))} change candidates; "
            f"categories: {', '.join(categories) or 'none'}; partial: {comparison.get('truncated', False)}."
        )
    lines.extend([
        "", "World-state comparison evaluates January 31 and February 4 under the same corrected "
        "knowledge boundary. It is distinct from comparing the original saved belief with later knowledge.",
        "", "## Demonstration checks", "",
    ])
    for name, passed in report["checks"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'}: {name.replace('_', ' ')}")
    lines.extend([
        "", "These authored checks establish fixture behavior only. They do not validate a model extractor "
        "or completeness on a real corpus.", "", "## Evidence and saved work", "",
        "[Full report](report.json) contains exact query scopes, result evidence, both baseline kinds, "
        "the saved investigation, paired change evidence, and local export manifests.", "",
        "Local bundles retain exact version references:", "",
        "- [Saved baseline](baseline/report.md)",
        "- [Latest query](latest/report.md)",
        "- [Fixed-knowledge world comparison](world-comparison/report.md)",
        "- [Withdrawal since conflict review](withdrawal-comparison/report.md)", "",
        "A source withdrawal removes that source's current support; it does not prove a reverse world transition.", "",
    ])
    return "\n".join(lines)


def run_demo(db_path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Run the five fixture batches in a fresh database and write local artifacts."""
    from .resources import resource_path

    with resource_path("fixtures", "pump") as fixtures:
        return _run_demo(db_path, destination, fixtures)


def _run_demo(db_path: str | Path, destination: str | Path, fixtures: Path) -> dict[str, Any]:
    from .cli import read_json, read_jsonl
    from .engine import Engine

    database = Path(db_path)
    output = Path(destination)
    if str(db_path) == ":memory:" or database.exists():
        raise DomainError(
            "demo_requires_fresh_database",
            "Choose a new database path; simulated history cannot overwrite or mix with an existing database",
            {"database": str(database)},
        )
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise DomainError("demo_output_exists", "Choose a new or empty output directory", {"output": str(output)})
    manifest = read_json(fixtures / "manifest.json")
    batches = manifest["batches"]
    if len(batches) != 5:
        raise DomainError("invalid_demo_fixture", "Demo requires the five pump-history batches", {})
    corpus = manifest["corpus_id"]
    clock = SimulatedClock(batches[0]["ingested_at"])
    database.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    engine = Engine(str(database), clock=clock)
    try:
        batch_results = []
        baseline_run = None
        findings_baseline = None
        neighborhood_baseline = None
        conflict_baseline = None
        conflict_run = None
        investigation = None
        for index, batch in enumerate(batches):
            clock.set(batch["ingested_at"])
            job = engine.ingest(corpus, read_jsonl(fixtures / batch["records"]), batch["id"])
            job_id = _id(job, "job_id")
            clock.set(batch["prepared_at"])
            engine.stage_assertions(job_id, read_json(fixtures / batch["assertions"]))
            clock.set(batch["published_at"])
            snapshot = engine.publish_snapshot(job_id, label=f"Authored fixture: {batch['id']}")
            snapshot_id = _id(snapshot, "snapshot_id")
            batch_results.append({
                "batch_id": batch["id"], "job_id": job_id, "snapshot_id": snapshot_id,
                "ingested_at": batch["ingested_at"], "prepared_at": batch["prepared_at"],
                "published_at": batch["published_at"],
            })
            if index == 1:
                baseline_run = engine.search(corpus, "Pump P", snapshot_id=snapshot_id, mode="graphrag")
                findings_baseline = engine.save_baseline(_id(baseline_run, "run_id"), kind="saved_findings")
                neighborhood_baseline = engine.save_baseline(
                    _id(baseline_run, "run_id"), kind="entity_neighborhood", seed_entity_ids=["pump-p"], hops=1
                )
                investigation = engine.save_investigation({
                    "corpus_id": corpus, "title": "Pump P operator history — authored demonstration",
                    "question": "What was planned, what was later reported, and what remains disputed?",
                    "snapshot_id": snapshot_id, "status": "active",
                    "notes": ["Simulated clock; authored-fixture assertions, not model extraction."],
                    "run_ids": [_id(baseline_run, "run_id")],
                    "baseline_ids": [_id(findings_baseline, "baseline_id"), _id(neighborhood_baseline, "baseline_id")],
                    "view": {"selected_entity_ids": ["pump-p"]},
                })
            elif index == 3:
                conflict_run = engine.search(
                    corpus, "Pump P", snapshot_id=snapshot_id,
                    valid_time="2025-02-04T00:00:00Z", mode="graphrag",
                )
                conflict_baseline = engine.save_baseline(
                    _id(conflict_run, "run_id"), kind="entity_neighborhood", seed_entity_ids=["pump-p"], hops=1
                )
        latest_id = batch_results[-1]["snapshot_id"]
        correction_id = batch_results[2]["snapshot_id"]
        correction_time = batches[2]["published_at"]
        queries = {
            "saved_baseline": baseline_run,
            "historical_before_correction": engine.search(
                corpus, "Pump P", snapshot_id=latest_id, knowledge_cutoff="2025-02-05T00:00:00Z",
                valid_time="2025-02-02T00:00:00Z", mode="graphrag",
            ),
            "corrected_view_of_same_event_time": engine.search(
                corpus, "Pump P", snapshot_id=latest_id, knowledge_cutoff=correction_time,
                valid_time="2025-02-02T00:00:00Z", mode="graphrag",
            ),
            "conflicting_view": conflict_run,
            "latest_reported_state": engine.search(
                corpus, "Pump P", snapshot_id=latest_id,
                valid_time="2025-02-04T00:00:00Z", mode="graphrag",
            ),
        }
        comparisons = {
            "saved_findings_knowledge_change": engine.compare(
                _id(findings_baseline, "baseline_id"), target_snapshot_id=latest_id, mode="knowledge_change"
            ),
            "entity_neighborhood_knowledge_change": engine.compare(
                _id(neighborhood_baseline, "baseline_id"), target_snapshot_id=latest_id, mode="knowledge_change"
            ),
            "source_changes": engine.compare(
                _id(findings_baseline, "baseline_id"), target_snapshot_id=latest_id, mode="source_change"
            ),
            "fixed_knowledge_world_change": engine.compare(
                _id(neighborhood_baseline, "baseline_id"), target_snapshot_id=correction_id,
                mode="world_state_change", knowledge_cutoff=correction_time,
                valid_from_time="2025-01-31T00:00:00Z", valid_to_time="2025-02-04T00:00:00Z",
            ),
            "withdrawal_since_conflict_review": engine.compare(
                _id(conflict_baseline, "baseline_id"), target_snapshot_id=latest_id, mode="knowledge_change"
            ),
        }
        investigation_data = {
            "investigation_id": _id(investigation, "investigation_id"), "corpus_id": corpus,
            "title": "Pump P operator history — authored demonstration",
            "question": "What was planned, what was later reported, and what remains disputed?",
            "snapshot_id": latest_id, "status": "concluded",
            "notes": [
                "Simulation only. The late correction changes the reported handover date.",
                "Withdrawal of C's report removes that support; it does not prove a C-to-B transition.",
            ],
            "run_ids": [query["run_id"] for query in queries.values()] + [run["run_id"] for run in comparisons.values()],
            "baseline_ids": [
                _id(findings_baseline, "baseline_id"), _id(neighborhood_baseline, "baseline_id"),
                _id(conflict_baseline, "baseline_id"),
            ],
            "view": {"selected_entity_ids": ["pump-p"]},
        }
        updated = engine.save_investigation(investigation_data, expected_version=investigation["version"])
        reopened = engine.get_investigation(_id(updated, "investigation_id"))
        exports = {}
        for name, run in (
            ("baseline", baseline_run), ("latest", queries["latest_reported_state"]),
            ("world-comparison", comparisons["fixed_knowledge_world_change"]),
            ("withdrawal-comparison", comparisons["withdrawal_since_conflict_review"]),
        ):
            exports[name] = engine.export_evidence(run["run_id"], str(output / name))
        historical_items = queries["historical_before_correction"].get("items", [])
        conflict_items = queries["conflicting_view"].get("items", [])
        world_changes = comparisons["fixed_knowledge_world_change"].get("changes", [])
        world_before = {
            item["assertion_id"] for change in world_changes for item in change.get("before", [])
            if item.get("assertion_id")
        }
        world_after = {
            item["assertion_id"] for change in world_changes for item in change.get("after", [])
            if item.get("assertion_id")
        }
        checks = {
            "five_snapshots_published": len(batch_results) == 5,
            "old_query_has_only_planned_b": (
                _assertion_ids(queries["historical_before_correction"]) == {"b-planned"}
                and all(item.get("modality") == "planned" for item in historical_items if item.get("assertion_id"))
            ),
            "corrected_past_has_reported_a": _assertion_ids(queries["corrected_view_of_same_event_time"]) == {"a-corrected"},
            "conflicting_reports_preserved": (
                _assertion_ids(queries["conflicting_view"]) == {"b-corrected", "c-report"}
                and all(item.get("disputed") for item in conflict_items if item.get("assertion_id"))
            ),
            "withdrawal_leaves_reported_b": _assertion_ids(queries["latest_reported_state"]) == {"b-corrected"},
            "fixed_knowledge_world_change_pairs_a_and_b": world_before == {"a-corrected"} and world_after == {"b-corrected"},
            "withdrawn_c_has_retraction_evidence": any(
                "retraction" in change.get("categories", [])
                and {item.get("assertion_id") for item in change.get("before", [])} == {"c-report"}
                and not change.get("after")
                for change in comparisons["withdrawal_since_conflict_review"].get("changes", [])
            ),
            "reopened_investigation_same_version": reopened["version"] == updated["version"],
            "saved_baseline_stays_on_original_snapshot": (
                engine.get_baseline(_id(findings_baseline, "baseline_id")) == findings_baseline
            ),
        }
        report = {
            "schema_version": "1", "demo_kind": "authored-fixture", "clock_mode": "simulated_utc",
            "extraction_method": "authored-fixture", "corpus_id": corpus, "backend": "sqlite-reference-v1",
            "limitations": [
                "No model extraction or embeddings", "No acquired real corpus", "No scale or discovery-quality claim",
                "Comparison shows endpoint-state differences; intermediate ledger-event enumeration is not implemented",
            ],
            "batches": batch_results,
            "baselines": {
                "saved_findings": findings_baseline, "entity_neighborhood": neighborhood_baseline,
                "conflict_review": conflict_baseline,
            },
            "queries": queries, "comparisons": comparisons, "investigation": reopened,
            "exports": exports, "checks": checks, "all_checks_passed": all(checks.values()),
        }
        report_path = output / "report.json"
        markdown_path = output / "report.md"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(_markdown(report), encoding="utf-8")
        if not report["all_checks_passed"]:
            raise DomainError(
                "demo_checks_failed", "Authored demonstration checks failed; inspect the saved report",
                {"checks": checks, "report": str(report_path.resolve())},
            )
        return {
            "clock_mode": report["clock_mode"], "extraction_method": report["extraction_method"],
            "corpus_id": corpus, "snapshots": batch_results, "checks": checks,
            "all_checks_passed": report["all_checks_passed"], "limitations": report["limitations"],
            "report": str(report_path.resolve()), "readable_report": str(markdown_path.resolve()),
        }
    finally:
        close = getattr(engine, "close", None)
        if close is not None:
            close()
