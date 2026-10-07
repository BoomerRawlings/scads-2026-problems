import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

from analytics311.errors import AnalyticsError
from analytics311.jobs import acquire_job, recover_exports, release_export, reserve_export


_WORKER = """
import os, sys
from pathlib import Path
from analytics311.jobs import acquire_job
try:
    with acquire_job(sys.argv[1], sys.argv[2]):
        print('locked', flush=True)
        if sys.stdin.read() == 'crash':
            os._exit(77)
finally:
    (Path(sys.argv[1]) / 'worker-unwound').write_text('finally executed', encoding='ascii')
"""


class JobLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runs = Path(self.temporary.name)
        self.job_id = uuid.uuid4().hex

    def job(self, job_id=None, status="running", **overrides):
        job_id = job_id or self.job_id
        value = {"kind": "export", "job_id": job_id, "status": status, "complete": False,
                 "result_id": "b" * 32, "dataset_identity": "old-dataset", **overrides}
        path = self.runs / f"{job_id}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def worker(self, script=_WORKER):
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = subprocess.Popen([sys.executable, "-c", script, str(self.runs), self.job_id],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=Path(__file__).resolve().parents[1], **kwargs)
        def cleanup():
            if process.poll() is None:
                try:
                    process.communicate(input="crash", timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=10)
            else:
                process.communicate(timeout=10)
        self.addCleanup(cleanup)
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
        try:
            line = ready.get(timeout=15)
        except queue.Empty:
            self.fail("Lease subprocess did not become ready")
        if line.strip() != "locked":
            self.fail("Lease subprocess failed: " + process.communicate(timeout=10)[1])
        return process

    def assert_code(self, code, callback):
        with self.assertRaises(AnalyticsError) as raised:
            callback()
        self.assertEqual(code, raised.exception.code)

    def crash_worker(self, process):
        # Windows virtualenv python.exe may be a launcher, not the interpreter
        # owning the lease. Exit inside that interpreter without any unwinding.
        output, error = process.communicate(input="crash", timeout=10)
        self.assertEqual(77, process.returncode, output + error)
        self.assertFalse((self.runs / "worker-unwound").exists())

    def test_same_process_cannot_double_acquire_and_exception_releases(self):
        with acquire_job(self.runs, self.job_id):
            self.assert_code("job_busy", lambda: acquire_job(self.runs, self.job_id).__enter__())
        with self.assertRaises(RuntimeError):
            with acquire_job(self.runs, self.job_id):
                raise RuntimeError("worker failed")
        with acquire_job(self.runs, self.job_id):
            self.assertTrue((self.runs / f"{self.job_id}.lock").is_file())

    def test_actual_process_contention_and_clean_exit_release(self):
        process = self.worker()
        self.assert_code("job_busy", lambda: acquire_job(self.runs, self.job_id).__enter__())
        process.communicate(input="release", timeout=10)
        self.assertEqual(0, process.returncode)
        self.assertTrue((self.runs / "worker-unwound").is_file())
        with acquire_job(self.runs, self.job_id):
            pass

    def test_process_death_releases_lock_and_enables_recovery(self):
        path = self.job()
        partial = self.runs / f"{self.job_id}.csv.part"
        partial.write_text("unfinished", encoding="utf-8")
        process = self.worker()
        active = recover_exports(self.runs)
        self.assertEqual([self.job_id], active["active"])
        self.assertEqual("running", json.loads(path.read_text())["status"])
        self.assertTrue(partial.exists())
        self.crash_worker(process)
        recovered = recover_exports(self.runs)
        self.assertEqual(1, recovered["recovered_count"])
        self.assertFalse(partial.exists())
        self.assertTrue((self.runs / f"{self.job_id}.lock").exists())
        self.assertEqual("worker_interrupted", json.loads(path.read_text())["error"]["code"])

    def test_recovery_preserves_published_orphan_and_ignores_stored_paths(self):
        outside = self.runs / "unrelated.csv"
        outside.write_text("keep", encoding="utf-8")
        path = self.job(file=str(outside), sha256="unverified")
        final = self.runs / f"{self.job_id}.csv"
        final.write_text("possibly published", encoding="utf-8")
        (self.runs / f"{self.job_id}.cancel").touch()
        report = recover_exports(self.runs)
        job = json.loads(path.read_text())
        self.assertEqual(1, report["orphan_count"])
        self.assertEqual("failed", job["status"])
        self.assertFalse(job["complete"])
        self.assertNotIn("file", job)
        self.assertNotIn("sha256", job)
        self.assertEqual(final.name, job["orphan_artifact"]["path"])
        self.assertFalse(job["orphan_artifact"]["verified"])
        self.assertEqual("keep", outside.read_text())
        self.assertEqual("possibly published", final.read_text())
        self.assertFalse((self.runs / f"{self.job_id}.cancel").exists())
        self.assertEqual(0, recover_exports(self.runs)["recovered_count"])

    def test_queued_recovery_needs_no_manifest_or_pid_metadata(self):
        path = self.job(status="queued", worker_pid=os.getpid())
        report = recover_exports(self.runs)
        self.assertEqual(1, report["recovered_count"])
        self.assertEqual("queued", json.loads(path.read_text())["previous_status"])

    def test_recovery_preserves_last_observed_stage_and_counters(self):
        path = self.job(stage="streaming", stage_started_at="2026-01-01T00:00:00Z",
                        last_progress_at="2026-01-01T00:00:01Z", rows_written=500,
                        bytes_written=25000, elapsed_seconds=1.25)
        recover_exports(self.runs)
        job = json.loads(path.read_text())
        self.assertEqual("streaming", job["stopped_stage"])
        self.assertEqual("failed", job["stage"])
        self.assertEqual(job["recovered_at"], job["stage_started_at"])
        self.assertEqual(job["recovered_at"], job["last_progress_at"])
        self.assertEqual((500, 25000, 1.25), (job["rows_written"], job["bytes_written"], job["elapsed_seconds"]))
        before = path.read_bytes()
        self.assertEqual(0, recover_exports(self.runs)["recovered_count"])
        self.assertEqual(before, path.read_bytes())

    def test_legacy_recovery_records_previous_status_as_stage(self):
        path = self.job(status="queued")
        recover_exports(self.runs)
        job = json.loads(path.read_text())
        self.assertEqual("queued", job["stopped_stage"])
        self.assertEqual("failed", job["stage"])

    def test_finished_exports_and_analysis_are_untouched(self):
        snapshots = {}
        for status in ("complete", "failed", "cancelled"):
            path = self.job(uuid.uuid4().hex, status=status, complete=status == "complete")
            snapshots[path] = path.read_bytes()
        path = self.job(uuid.uuid4().hex, kind="analysis")
        snapshots[path] = path.read_bytes()
        report = recover_exports(self.runs)
        self.assertEqual(0, report["recovered_count"])
        self.assertEqual(4, report["ignored_count"])
        self.assertEqual(snapshots, {path: path.read_bytes() for path in snapshots})

    def test_malformed_or_mismatched_metadata_never_triggers_cleanup(self):
        path = self.job(job_id="c" * 32)
        value = json.loads(path.read_text())
        value["job_id"] = "d" * 32
        path.write_text(json.dumps(value), encoding="utf-8")
        malformed = self.runs / f"{self.job_id}.json"
        malformed.write_text("not json", encoding="utf-8")
        self.job(uuid.uuid4().hex, rows_written=float("nan"))
        partial = self.runs / f"{self.job_id}.csv.part"
        partial.write_text("keep", encoding="utf-8")
        report = recover_exports(self.runs)
        self.assertEqual(3, report["invalid_count"])
        self.assertEqual(0, report["recovered_count"])
        self.assertEqual("keep", partial.read_text())

    def test_directory_artifact_is_not_recursively_deleted(self):
        path = self.job()
        partial = self.runs / f"{self.job_id}.csv.part"
        partial.mkdir()
        (partial / "keep").write_text("keep", encoding="utf-8")
        report = recover_exports(self.runs)
        self.assertEqual("unsafe_job_path", report["invalid"][0]["error"]["code"])
        self.assertEqual("running", json.loads(path.read_text())["status"])
        self.assertTrue((partial / "keep").exists())

    def test_identifiers_cannot_escape_the_store(self):
        for bad in ("../outside", "a" * 31, "a" * 33, "A" * 32, None, "a" * 32 + ".json"):
            with self.subTest(job_id=bad):
                self.assert_code("invalid_spec", lambda: acquire_job(self.runs, bad).__enter__())
        self.assertEqual([], list(self.runs.iterdir()))

    def test_hardlinked_artifact_is_refused_without_touching_foreign_data(self):
        self.job()
        source = self.runs / "foreign.csv"
        source.write_text("foreign", encoding="utf-8")
        partial = self.runs / f"{self.job_id}.csv.part"
        os.link(source, partial)
        report = recover_exports(self.runs)
        self.assertEqual("unsafe_job_path", report["invalid"][0]["error"]["code"])
        self.assertEqual("foreign", source.read_text())
        self.assertTrue(partial.exists())

    def test_symlink_lock_is_refused(self):
        target = self.runs / "foreign.txt"
        target.write_text("foreign", encoding="utf-8")
        link = self.runs / f"{self.job_id}.lock"
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Host disallows unprivileged symlinks: {exc}")
        self.assert_code("unsafe_job_path", lambda: acquire_job(self.runs, self.job_id).__enter__())
        self.assertEqual("foreign", target.read_text())

    def test_admission_is_bounded_until_completed_worker_releases(self):
        second, third = uuid.uuid4().hex, uuid.uuid4().hex
        with reserve_export(self.runs, self.job_id):
            self.job(status="queued")
        with reserve_export(self.runs, second):
            self.job(second, status="queued")
        self.assert_code("budget_exceeded", lambda: reserve_export(self.runs, third).__enter__())
        self.assertTrue(release_export(self.runs, self.job_id))
        self.assertFalse(release_export(self.runs, self.job_id))
        with reserve_export(self.runs, third):
            self.job(third, status="queued")
        self.assertEqual(2, len(list(self.runs.glob("*.export"))))

    def test_failed_startup_releases_reservation_and_registry(self):
        with self.assertRaises(RuntimeError):
            with reserve_export(self.runs, self.job_id, maximum=1):
                raise RuntimeError("Popen failed")
        self.assertFalse((self.runs / f"{self.job_id}.export").exists())
        with reserve_export(self.runs, self.job_id, maximum=1):
            pass

    def test_active_queue_creation_excludes_recovery(self):
        with reserve_export(self.runs, self.job_id):
            self.assert_code("job_busy", lambda: recover_exports(self.runs))

    def test_crashed_reservation_is_recovered_without_job_json(self):
        script = """
import os, sys
from pathlib import Path
from analytics311.jobs import reserve_export
try:
    with reserve_export(sys.argv[1], sys.argv[2]):
        print('locked', flush=True)
        if sys.stdin.read() == 'crash':
            os._exit(77)
finally:
    (Path(sys.argv[1]) / 'worker-unwound').write_text('finally executed', encoding='ascii')
"""
        process = self.worker(script)
        self.assert_code("job_busy", lambda: reserve_export(self.runs, uuid.uuid4().hex).__enter__())
        self.crash_worker(process)
        report = recover_exports(self.runs)
        self.assertEqual([self.job_id], report["released_reservations"])
        self.assertFalse((self.runs / f"{self.job_id}.export").exists())
        self.assertEqual(0, report["recovered_count"])

    def test_recovery_releases_finished_and_abandoned_but_not_active_markers(self):
        finished = uuid.uuid4().hex
        with reserve_export(self.runs, finished):
            self.job(finished, status="complete", complete=True)
        with reserve_export(self.runs, self.job_id):
            self.job(status="running")
        process = self.worker()
        report = recover_exports(self.runs)
        self.assertEqual([finished], report["released_reservations"])
        self.assertEqual([self.job_id], report["active"])
        self.assertTrue((self.runs / f"{self.job_id}.export").exists())
        self.crash_worker(process)
        report = recover_exports(self.runs)
        self.assertEqual([self.job_id], report["released_reservations"])
        self.assertEqual(1, report["recovered_count"])

    def test_admission_does_not_read_large_analysis_files(self):
        # Invalid JSON models a huge result: admission must inspect markers only.
        (self.runs / f"{uuid.uuid4().hex}.json").write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
        with reserve_export(self.runs, self.job_id):
            self.job(status="queued")
        report = recover_exports(self.runs)
        self.assertEqual(1, report["ignored_count"])
        self.assertEqual(1, report["recovered_count"])
        self.assertEqual(0, report["invalid_count"])

    def test_admission_configuration_and_linked_marker_rejected(self):
        for maximum in (0, -1, True, 1.0, 1001):
            with self.subTest(maximum=maximum):
                self.assert_code("invalid_configuration", lambda: reserve_export(self.runs, self.job_id, maximum).__enter__())
        target = self.runs / "foreign-marker"
        target.write_text("keep", encoding="utf-8")
        os.link(target, self.runs / f"{uuid.uuid4().hex}.export")
        self.assert_code("unsafe_job_path", lambda: reserve_export(self.runs, self.job_id).__enter__())
        self.assertEqual("keep", target.read_text())


if __name__ == "__main__":
    unittest.main()
