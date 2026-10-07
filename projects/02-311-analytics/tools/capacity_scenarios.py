"""Replay bounded sizing arithmetic; never allocate corpora or launch services."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from analytics311 import __version__
from analytics311.capacity import plan_capacity
from analytics311.errors import AnalyticsError


MAX_INPUT_BYTES = 1024 * 1024
MAX_COMBINATIONS = 100
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "examples/capacity/scenarios.json"


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise AnalyticsError("invalid_scenarios", "Scenario JSON contains duplicate object keys.")
        value[key] = item
    return value


def _invalid_constant(_):
    raise AnalyticsError("invalid_scenarios", "Scenario JSON contains a nonfinite number.")


def run_scenarios(source):
    """Read at most 1 MiB and return at most 100 complete modeled plans."""
    try:
        with Path(source).open("rb") as stream:
            content = stream.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise AnalyticsError("scenario_io_error", "Cannot read scenario input.") from None
    if len(content) > MAX_INPUT_BYTES:
        raise AnalyticsError("invalid_scenarios", "Scenario input exceeds 1 MiB.")
    try:
        value = json.loads(content, object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise AnalyticsError("invalid_scenarios", "Scenario input must be valid bounded JSON.") from None
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("evidence_kind") != "hypothetical_host_scenarios"):
        raise AnalyticsError("invalid_scenarios", "Use schema_version 1 with evidence_kind hypothetical_host_scenarios.")
    hosts, cases = value.get("hosts"), value.get("row_scenarios")
    if not isinstance(hosts, list) or not isinstance(cases, list) or not hosts or not cases:
        raise AnalyticsError("invalid_scenarios", "hosts and row_scenarios must be nonempty arrays.")
    if len(hosts) * len(cases) > MAX_COMBINATIONS:
        raise AnalyticsError("invalid_scenarios", "At most 100 host/scenario combinations are allowed.")
    names = set()
    for host in hosts:
        if (not isinstance(host, dict) or not isinstance(host.get("name"), str)
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", host["name"])
                or not isinstance(host.get("inventory"), dict)):
            raise AnalyticsError("invalid_scenarios", "Each host needs a short lowercase slug name and an inventory object.")
        if host["name"] in names:
            raise AnalyticsError("invalid_scenarios", "Host names must be unique.")
        names.add(host["name"])
    for case in cases:
        if (not isinstance(case, dict) or set(case) - {"profile", "target_rows", "assumptions"}
                or not isinstance(case.get("profile"), str) or type(case.get("target_rows")) is not int
                or ("assumptions" in case and not isinstance(case["assumptions"], dict))):
            raise AnalyticsError("invalid_scenarios", "Each row scenario needs profile, integer target_rows and optional assumptions.")
    results = []
    summary = {"modeled_fit": 0, "insufficient": 0, "unknown": 0}
    for host in hosts:
        for case in cases:
            plan = plan_capacity(case["profile"], case["target_rows"], host["inventory"], case.get("assumptions"))
            summary[plan["status"]] += 1
            results.append({"host": host["name"], "profile": case["profile"], "target_rows": case["target_rows"], "plan": plan})
    return {"schema_version": 1, "kind": "capacity_scenario_report", "evidence_kind": "modeled_capacity",
            "package_version": __version__, "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_sha256": hashlib.sha256(content).hexdigest(), "input_bytes": len(content),
            "combination_count": len(results), "summary": summary, "results": results,
            "ready_for_production": False,
            "limitations": ["Authored hypothetical resource inventories; no live host or engine validation.",
                            "Only sizing arithmetic replayed; no records allocated, service launched or throughput measured.",
                            "A modeled fit does not establish per-node cluster capacity or million/billion-row correctness."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True, help="New report file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        report = run_scenarios(args.source)
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        try:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise AnalyticsError("output_exists", "Output already exists; choose a new evidence file.") from None
        except OSError:
            raise AnalyticsError("scenario_io_error", "Cannot write scenario report.") from None
        print(json.dumps({"evidence_kind": report["evidence_kind"], "combination_count": report["combination_count"],
                          "summary": report["summary"], "ready_for_production": False}))
        return 0
    except AnalyticsError as exc:
        print(json.dumps({"error": exc.as_dict()}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
