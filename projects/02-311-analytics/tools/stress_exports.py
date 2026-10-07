"""Bounded local process/export recovery measurements; no engine or scale claims."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from analytics311 import __version__
from analytics311.errors import AnalyticsError
from analytics311.jobs import recover_exports
from analytics311.resources import asset_path
from analytics311.service import AnalyticsService


EXPECTED_IDS = {"FIX-021", "FIX-022", "FIX-023", "FIX-032"}
SPEC = {
    "schema_version": "1", "dataset_version": "fixture-v1", "operation": "records",
    "as_of": "2026-01-02T12:00:00-05:00", "timezone": "America/New_York",
    "time": {"field": "created_date", "gte": "2025-12-01T00:00:00-05:00", "lt": "2026-01-01T00:00:00-05:00"},
    "filters": {"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"}, {"category_family": "noise"}]},
    "preview_limit": 2,
}


class TrialFailure(Exception):
    def __init__(self, code, details=None):
        self.code, self.details = code, details or {}
        super().__init__(code)


def snapshot(job):
    """Only bounded diagnostic fields; never record paths, raw records or messages."""
    result = {}
    for key in ("status", "stage", "stopped_stage"):
        value = job.get(key)
        if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,64}", value):
            result[key] = value
    for key in ("rows_written", "bytes_written", "elapsed_seconds"):
        value = job.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            result[key] = value
    for key in ("queued_at", "started_at", "stage_started_at", "last_progress_at", "finished_at", "deadline_at"):
        value = job.get(key)
        if isinstance(value, str) and len(value) <= 40:
            try:
                datetime.fromisoformat(value)
                result[key] = value
            except ValueError:
                pass
    if type(job.get("complete")) is bool:
        result["complete"] = job["complete"]
    error = job.get("error", {})
    if isinstance(error, dict) and isinstance(error.get("code"), str) and re.fullmatch(r"[a-z_]{1,64}", error["code"]):
        result["error_code"] = error["code"]
    cleanup = job.get("cleanup_error", {})
    if isinstance(cleanup, dict) and isinstance(cleanup.get("code"), str) and re.fullmatch(r"[a-z_]{1,64}", cleanup["code"]):
        result["cleanup_error_code"] = cleanup["code"]
    return result


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def cleanup_failure(receipt, code, exception=None):
    detail = {"code": code}
    if exception is not None:
        detail["exception_type"] = type(exception).__name__
    receipt["passed"] = False
    receipt.setdefault("failure", {"phase": "cleanup", **detail})
    receipt.setdefault("cleanup_failures", []).append(detail)


@contextmanager
def temporary_workspace(receipt):
    temporary = tempfile.TemporaryDirectory(prefix="analytics311-export-stress-")
    try:
        yield Path(temporary.name)
    finally:
        try:
            temporary.cleanup()
        except Exception as exc:
            cleanup_failure(receipt, "temporary_cleanup_failed", exc)


class OwnedWorkers:
    """Track actual Popen handles, never infer process ownership from job metadata."""
    def __init__(self):
        self.start = subprocess.Popen
        self.processes = {}
        self.peak_alive = 0
        self.crash_gate = None
        self.crash_gates = []
        self.current_runs = None
        self.cancel_paths = {}

    def launch(self, command, **kwargs):
        job_id = command[-1]
        self.cancel_paths[job_id] = self.current_runs / f"{job_id}.cancel"
        if self.crash_gate is not None:
            config = command[command.index("--config") + 1]
            command = [sys.executable, str(Path(__file__).resolve()), "_crash-worker", config, job_id, str(self.crash_gate)]
            self.crash_gates.append(self.crash_gate)
            self.crash_gate = None
        process = self.start(command, **kwargs)
        self.processes[job_id] = process
        self.peak_alive = max(self.peak_alive, sum(p.poll() is None for p in self.processes.values()))
        return process

    def stop(self):
        # Windows venv launchers may own a separate interpreter. Request exit in
        # our fault child, and cooperative cancellation in normal workers first.
        failures = []
        for gate in self.crash_gates:
            try:
                gate.with_suffix(".exit").touch()
            except Exception as exc:
                failures.append(exc)
        for job_id, process in self.processes.items():
            try:
                if process.poll() is None:
                    self.cancel_paths[job_id].touch()
            except Exception as exc:
                failures.append(exc)
        deadline = time.monotonic() + 5
        for process in self.processes.values():
            try:
                if process.poll() is None:
                    process.wait(timeout=max(.01, deadline - time.monotonic()))
            except Exception as exc:
                failures.append(exc)
        # Last resort affects only owned handles. A timed-out redirected child
        # cannot be assumed dead; the receipt remains failed in that case.
        for process in self.processes.values():
            try:
                if process.poll() is None:
                    process.kill()
            except Exception as exc:
                failures.append(exc)
        for process in self.processes.values():
            try:
                process.wait(timeout=5)
            except Exception as exc:
                failures.append(exc)
        return failures


def wait_batch(service, jobs, workers, deadline):
    latest = jobs
    observed = {job["job_id"]: set() for job in jobs}
    while True:
        try:
            latest = [service.get_result(job["job_id"]) for job in latest]
        except AnalyticsError as exc:
            raise TrialFailure("job_read_failed", {"error_code": exc.code, "jobs": [snapshot(job) for job in latest]}) from exc
        for job in latest:
            stage = snapshot(job).get("stage")
            if stage:
                observed[job["job_id"]].add(stage)
        details = {"jobs": [snapshot(job) for job in latest]}
        if any(job.get("status") not in ("queued", "running", "complete") for job in latest):
            raise TrialFailure("export_failed", details)
        exits = [workers.processes[job["job_id"]].poll() for job in latest]
        if any(code is not None and code != 0 for code in exits):
            raise TrialFailure("worker_exit", {**details, "exit_codes": exits})
        if time.monotonic() >= deadline:
            raise TrialFailure("harness_timeout", details)
        if all(job.get("status") == "complete" for job in latest) and all(code == 0 for code in exits):
            for job in latest:
                job["observed_stages"] = sorted(observed[job["job_id"]])
            return latest
        time.sleep(min(.05, max(0, deadline - time.monotonic())))


def verify_export(job, runs):
    if job.get("status") != "complete" or job.get("complete") is not True or job.get("rows_written") != 4:
        raise TrialFailure("incomplete_csv", {"job": snapshot(job)})
    path = runs / f"{job['job_id']}.csv"
    if Path(job.get("file", "")).resolve() != path.resolve() or not path.is_file() or path.stat().st_size > 65536:
        raise TrialFailure("invalid_csv_artifact")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != job.get("sha256") or path.stat().st_size != job.get("bytes_written"):
        raise TrialFailure("csv_integrity_mismatch")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 4 or {row.get("unique_key") for row in rows} != EXPECTED_IDS:
        raise TrialFailure("csv_cohort_mismatch")
    if any((runs / f"{job['job_id']}{suffix}").exists() for suffix in (".csv.part", ".export", ".cancel")):
        raise TrialFailure("export_residue")
    return {"rows": 4, "exact_ids": True, "sha256": digest, "bytes": path.stat().st_size,
            "terminal": snapshot(job), "observed_stages": job.get("observed_stages", [])}


def verify_recovery(service, job_id, report):
    job = service.get_result(job_id)
    if (report.get("recovered_count") != 1 or report.get("active_count") != 0 or report.get("invalid_count") != 0
            or [entry.get("job_id") for entry in report.get("recovered", [])] != [job_id]
            or report["recovered"][0].get("removed_partial") is not True
            or report.get("released_reservations") != [job_id]
            or job.get("status") != "failed" or job.get("complete") is not False
            or job.get("error", {}).get("code") != "worker_interrupted"):
        raise TrialFailure("recovery_failed", {"job": snapshot(job)})
    if any((service.runs / f"{job_id}{suffix}").exists() for suffix in (".csv.part", ".csv", ".export", ".cancel")):
        raise TrialFailure("recovery_residue", {"job": snapshot(job)})
    return snapshot(job)


def crash_worker(config, job_id, gate):
    """Fault injection holds a real worker after its first row, while owning its lease."""
    service = AnalyticsService(config)
    original = service.backend.iter_records
    def gated(*args, **kwargs):
        source = original(*args, **kwargs)
        try:
            yield next(source)
            Path(gate).write_text("ready", encoding="ascii")
            # Exit the interpreter itself: killing a Windows venv redirector
            # need not terminate its child. No cleanup/finally runs on os._exit.
            until = time.monotonic() + 130
            while time.monotonic() < until:
                if Path(gate).with_suffix(".exit").exists():
                    os._exit(86)
                time.sleep(.05)
            raise AnalyticsError("budget_exceeded", "Fault-injection gate expired")
        finally:
            source.close()
    service.backend.iter_records = gated
    service.run_export_job(job_id)


def run_trial(*, batches=3, concurrency=2, timeout_seconds=30, total_seconds=120, recovery=True):
    for value, low, high in ((batches, 1, 20), (concurrency, 1, 2), (timeout_seconds, 1, 120), (total_seconds, 1, 600)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid bounded trial option")
    started = time.monotonic()
    overall = started + total_seconds
    receipt = {"version": __version__, "evidence_level": "measured_bounded_local_process_only",
               "recorded_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
               "platform": platform.system(), "passed": False, "batches": [],
               "options": {"batches": batches, "concurrency": concurrency, "timeout_seconds": timeout_seconds,
                           "total_seconds": total_seconds, "recovery": recovery},
               "limits": ["Authored 32-row fixture, four-row exports; no Elasticsearch, capacity or agent-accuracy evidence.",
                          "Owned process counts track Popen launches; Windows venv launchers may have separate interpreter children.",
                          "Desktop load and filesystem cache uncontrolled; finite repetitions do not establish tail latency.",
                          "Polling and process waits are bounded; a blocked filesystem or process-creation call may overrun.",
                          "Crash trial deliberately gates the iterator after one row; it does not reproduce the unexplained v0.4 timeout."]}
    workers, stores = OwnedWorkers(), []
    phase = "setup"
    with temporary_workspace(receipt) as workspace:
        try:
            config = workspace / "profile.json"
            config.write_text(json.dumps({"backend": "fixture", "fixture_path": str(asset_path("fixtures/requests.jsonl")),
                "manifest_path": str(asset_path("fixtures/manifest.json")), "catalog_path": str(asset_path("config/catalog.json")),
                "runs_dir": "explicit-runs", "budgets": {"max_concurrent_exports": concurrency,
                "export_deadline_seconds": timeout_seconds, "max_export_rows": 4, "max_export_bytes": 65536}}), encoding="utf-8")
            service = AnalyticsService(config)
            stores.append(service.runs)
            result = service.run_analysis(SPEC)

            def batch(current, result_id, name):
                nonlocal phase
                phase = name
                before = time.monotonic()
                deadline = min(overall, before + timeout_seconds)
                if before >= deadline:
                    raise TrialFailure("harness_timeout")
                workers.current_runs = current.runs
                jobs = [current.export_csv(result_id, "records", "all_matching") for _ in range(concurrency)]
                complete = wait_batch(current, jobs, workers, deadline)
                return {"profile": name, "seconds": round(time.monotonic() - before, 6),
                        "exports": [verify_export(job, current.runs) for job in complete]}

            with patch("analytics311.service.subprocess.Popen", side_effect=workers.launch):
                for index in range(batches):
                    receipt["batches"].append(batch(service, result["result_id"], f"explicit_{index + 1}"))
                phase = "bundled_default_setup"
                original, changed = workspace / "default-workspace", workspace / "changed-workspace"
                original.mkdir()
                changed.mkdir()
                with patch.dict(os.environ):
                    os.environ.pop("ANALYTICS311_CONFIG", None)
                    with working_directory(original):
                        default = AnalyticsService()
                        stores.append(default.runs)
                        default_result = default.run_analysis(SPEC)
                    with working_directory(changed):
                        receipt["batches"].append(batch(default, default_result["result_id"], "bundled_default_cwd_change"))
                if default.runs != original / "runs" or (changed / "runs").exists():
                    raise TrialFailure("workspace_changed")

                if recovery:
                    phase = "crash_gate"
                    before = time.monotonic()
                    deadline = min(overall, before + timeout_seconds)
                    gate = workspace / "crash-ready"
                    workers.crash_gate = gate
                    workers.current_runs = service.runs
                    job = service.export_csv(result["result_id"], "records", "all_matching")
                    process = workers.processes[job["job_id"]]
                    while not gate.exists():
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise TrialFailure("crash_gate_unavailable", {"job": snapshot(service.get_result(job["job_id"]))})
                        time.sleep(.05)
                    active = recover_exports(service.runs)
                    if active["active"] != [job["job_id"]] or active["recovered_count"] or active["invalid_count"]:
                        raise TrialFailure("active_worker_recovered")
                    if (service.get_result(job["job_id"])["status"] != "running"
                            or not (service.runs / f"{job['job_id']}.csv.part").is_file()
                            or not (service.runs / f"{job['job_id']}.export").is_file()):
                        raise TrialFailure("crash_partial_unavailable")
                    phase = "crash_recovery"
                    gate.with_suffix(".exit").touch()
                    process.wait(timeout=5)
                    if process.returncode != 86:
                        raise TrialFailure("unexpected_crash_exit")
                    recovered = verify_recovery(service, job["job_id"], recover_exports(service.runs))
                    receipt["recovery"] = {"active_worker_preserved": True, "worker_abrupt_exit": True,
                        "method": "parent_gate_then_worker_os._exit", "worker_exit_code": 86,
                        "partial_removed": True, "reservation_released": True, "terminal": recovered,
                        "seconds": round(time.monotonic() - before, 6)}
                    receipt["batches"].append(batch(service, result["result_id"], "after_recovery"))
            if time.monotonic() >= overall:
                raise TrialFailure("harness_timeout")
            receipt["passed"] = True
        except TrialFailure as exc:
            receipt["failure"] = {"phase": phase, "code": exc.code, **exc.details}
        except Exception as exc:
            # Exception messages may contain local paths. Record only type/code.
            receipt["failure"] = {"phase": phase, "code": "harness_error", "exception_type": type(exc).__name__}
            if isinstance(exc, AnalyticsError):
                receipt["failure"]["analytics_error_code"] = exc.code
        finally:
            try:
                for failure in workers.stop():
                    cleanup_failure(receipt, "worker_cleanup_failed", failure)
            except Exception as exc:
                cleanup_failure(receipt, "worker_cleanup_failed", exc)
            receipt["peak_owned_processes_alive"] = workers.peak_alive
            receipt["owned_processes_started"] = len(workers.processes)
            # Cleanup only this invocation's isolated temporary stores; failures keep diagnostics in the receipt.
            for store in stores:
                try:
                    cleanup = recover_exports(store)
                    if cleanup["active_count"] or cleanup["invalid_count"]:
                        cleanup_failure(receipt, "store_cleanup_failed")
                except Exception as exc:
                    cleanup_failure(receipt, "store_cleanup_failed", exc)
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return receipt


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "_crash-worker":
        crash_worker(*sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batches", type=int, default=3, choices=range(1, 21), metavar="1..20")
    parser.add_argument("--concurrency", type=int, default=2, choices=(1, 2))
    parser.add_argument("--timeout-seconds", type=int, default=30, choices=range(1, 121), metavar="1..120")
    parser.add_argument("--total-seconds", type=int, default=120, choices=range(1, 601), metavar="1..600")
    parser.add_argument("--skip-recovery", action="store_true")
    args = parser.parse_args()
    receipt = run_trial(batches=args.batches, concurrency=args.concurrency, timeout_seconds=args.timeout_seconds,
                        total_seconds=args.total_seconds, recovery=not args.skip_recovery)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("passed", "owned_processes_started", "peak_owned_processes_alive", "elapsed_seconds")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
