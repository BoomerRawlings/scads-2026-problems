import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.ingest import _save_checkpoint, ingest_jsonl, ingestion_lease


INDEX = "nyc311-lease-test-v1"
_WORKER = """
import json, os, sys
from pathlib import Path
from analytics311.ingest import ingest_jsonl
root, pause = Path(sys.argv[1]), sys.argv[2]
index = 'nyc311-lease-test-v1'
def pause_worker():
    print('locked', flush=True)
    if sys.stdin.read() == 'crash':
        os._exit(77)
class Client:
    def request(self, method, path, body=None):
        if path.endswith('/_settings'):
            if pause == 'settings':
                pause_worker()
            return {index: {'settings': {'index': {'uuid': 'lease-test-uuid'}}}}
        if path.endswith('/_refresh'):
            return {'_shards': {'failed': 0}}
        if path.endswith('/_count'):
            return {'_shards': {'failed': 0}, 'count': 0}
        rows = [json.loads(line) for line in body.splitlines()]
        records = {rows[i]['index']['_id']: rows[i+1] for i in range(0, len(rows), 2)}
        (root / 'index-state.json').write_text(json.dumps(records), encoding='utf-8')
        if pause == 'bulk':
            pause_worker()
        return {'errors': False, 'items': [{'index': {'status': 201}} for _ in records]}
try:
    result = ingest_jsonl(root / 'source.jsonl', Client(), index, checkpoint_path=root / 'checkpoint.json')
finally:
    (root / 'worker-unwound').write_text('finally executed', encoding='ascii')
print(json.dumps(result), flush=True)
"""


class DiskClient:
    def __init__(self, root):
        self.path = root / "index-state.json"
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        if path.endswith("/_settings"):
            return {INDEX: {"settings": {"index": {"uuid": "lease-test-uuid"}}}}
        if path.endswith("/_refresh"):
            return {"_shards": {"failed": 0}}
        records = json.loads(self.path.read_text()) if self.path.exists() else {}
        if path.endswith("/_count"):
            return {"_shards": {"failed": 0}, "count": len(records)}
        rows = [json.loads(line) for line in body.splitlines()]
        for i in range(0, len(rows), 2):
            records[rows[i]["index"]["_id"]] = rows[i + 1]
        self.path.write_text(json.dumps(records), encoding="utf-8")
        return {"errors": False, "items": [{"index": {"status": 201}} for _ in rows[::2]]}


class IngestionLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.jsonl"
        self.checkpoint = self.root / "checkpoint.json"
        self.source.write_text(json.dumps({"unique_key": "1", "created_date": "2025-01-01T00:00:00Z"}) + "\n", encoding="utf-8")
        self.client = DiskClient(self.root)

    def assert_code(self, code, callback):
        with self.assertRaises(AnalyticsError) as raised:
            callback()
        self.assertEqual(code, raised.exception.code)

    def worker(self, pause):
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = subprocess.Popen([sys.executable, "-c", _WORKER, str(self.root), pause],
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
            self.fail("Ingestion worker did not acquire its lease")
        if line.strip() != "locked":
            self.fail("Ingestion worker failed: " + process.communicate(timeout=10)[1])
        return process

    def snapshot(self):
        return {path.name: path.read_bytes() for path in
                (self.source, self.checkpoint, self.client.path) if path.exists()}

    def assert_contention_untouched(self):
        before = self.snapshot()
        with patch("analytics311.ingest._fingerprint", side_effect=AssertionError("contender read source")):
            # Even a missing source must report busy before stat/hash or index I/O.
            self.assert_code("ingestion_busy", lambda: ingest_jsonl(
                self.root / "missing.jsonl", self.client, INDEX, checkpoint_path=self.checkpoint))
        self.assertEqual([], self.client.calls)
        self.assertEqual(before, self.snapshot())

    def test_actual_process_contention_precedes_source_and_index_access(self):
        process = self.worker("settings")
        self.assert_contention_untouched()
        output, error = process.communicate(input="release", timeout=10)
        self.assertEqual(0, process.returncode, error)
        self.assertTrue(json.loads(output)["complete"])
        self.assertTrue((self.root / "worker-unwound").is_file())
        # Persistent lock presence does not mean another process is alive.
        self.assertTrue(self.checkpoint.with_suffix(".json.lock").is_file())
        result = ingest_jsonl(self.source, self.client, INDEX, checkpoint_path=self.checkpoint)
        self.assertTrue(result["complete"])

    def test_process_death_releases_and_replays_pending_bulk(self):
        process = self.worker("bulk")
        saved = json.loads(self.checkpoint.read_text())
        self.assertEqual(0, saved["processed_rows"])
        self.assertIn("pending", saved)
        self.assertEqual(["1"], list(json.loads(self.client.path.read_text())))
        self.assert_contention_untouched()
        before_crash = self.checkpoint.read_bytes()
        output, error = process.communicate(input="crash", timeout=10)
        self.assertEqual(77, process.returncode, output + error)
        self.assertFalse((self.root / "worker-unwound").exists())
        self.assertEqual(before_crash, self.checkpoint.read_bytes())
        result = ingest_jsonl(self.source, self.client, INDEX, checkpoint_path=self.checkpoint)
        self.assertTrue(result["complete"])
        self.assertEqual(1, result["processed_rows"])
        self.assertEqual(["1"], list(json.loads(self.client.path.read_text())))
        self.assertNotIn("pending", result)

    def test_same_process_double_acquire_and_exception_release(self):
        with ingestion_lease(self.checkpoint):
            self.assert_contention_untouched()
        with self.assertRaises(RuntimeError):
            with ingestion_lease(self.checkpoint):
                raise RuntimeError("ingestion failed")
        with ingestion_lease(self.checkpoint):
            pass

    def test_equivalent_path_spellings_select_one_lease(self):
        alias = self.root / "unused" / ".." / self.checkpoint.name
        with ingestion_lease(self.checkpoint):
            self.assert_code("ingestion_busy", lambda: ingest_jsonl(
                self.source, self.client, INDEX, checkpoint_path=alias))
        if os.name == "nt":
            # GetShortPathName may return the long name on volumes where 8.3
            # creation is disabled. Either form must refer to the held lease.
            import ctypes
            self.checkpoint.write_text("{}", encoding="utf-8")
            buffer = ctypes.create_unicode_buffer(32768)
            function = ctypes.windll.kernel32.GetShortPathNameW
            function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
            function.restype = ctypes.c_uint32
            self.assertGreater(function(str(self.checkpoint), buffer, len(buffer)), 0)
            with ingestion_lease(self.checkpoint):
                self.assert_code("ingestion_busy", lambda: ingest_jsonl(
                    self.source, self.client, INDEX, checkpoint_path=buffer.value))
        self.assertEqual([], self.client.calls)

    def test_hardlinked_checkpoint_or_lock_rejected_without_mutation(self):
        foreign = self.root / "foreign.json"
        foreign.write_text("preserve", encoding="utf-8")
        for target in (self.checkpoint, self.checkpoint.with_suffix(".json.lock")):
            with self.subTest(target=target.name):
                os.link(foreign, target)
                try:
                    self.assert_code("unsafe_checkpoint_path", lambda: ingest_jsonl(
                        self.source, self.client, INDEX, checkpoint_path=self.checkpoint))
                    self.assertEqual("preserve", foreign.read_text())
                    self.assertEqual([], self.client.calls)
                finally:
                    target.unlink()

    def test_parent_directory_indirection_rejected(self):
        target = self.root / "actual"
        target.mkdir()
        redirect = self.root / "redirect"
        if os.name == "nt":
            env = {**os.environ, "ANALYTICS_TEST_LINK": str(redirect), "ANALYTICS_TEST_TARGET": str(target)}
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                     "New-Item -ItemType Junction -Path $env:ANALYTICS_TEST_LINK -Target $env:ANALYTICS_TEST_TARGET | Out-Null"],
                                    env=env, capture_output=True, text=True, timeout=20,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(0, result.returncode, result.stderr)
        else:
            redirect.symlink_to(target, target_is_directory=True)
        try:
            self.assert_code("unsafe_checkpoint_path", lambda: ingest_jsonl(
                self.source, self.client, INDEX, checkpoint_path=redirect / "nested" / "checkpoint.json"))
            self.assertEqual([], list(target.iterdir()))
            self.assertEqual([], self.client.calls)
        finally:
            if os.name == "nt":
                redirect.rmdir()
            else:
                redirect.unlink()

    def test_checkpoint_directory_and_windows_aliases_rejected(self):
        candidates = [self.root]
        if os.name == "nt":
            candidates.extend(self.root / name for name in ("checkpoint.json.", "checkpoint.json ", "checkpoint.json:stream", "NUL.json"))
            candidates.append(Path(r"\\example.invalid\share\checkpoint.json"))
        for candidate in candidates:
            with self.subTest(path=str(candidate)):
                self.assert_code("unsafe_checkpoint_path", lambda: ingest_jsonl(
                    self.source, self.client, INDEX, checkpoint_path=candidate))
        self.assertEqual([], self.client.calls)

    def test_fixed_temp_alias_is_never_opened_and_new_temps_cleaned(self):
        foreign = self.root / "foreign.json"
        foreign.write_text("preserve", encoding="utf-8")
        old_temp = self.checkpoint.with_suffix(".json.tmp")
        os.link(foreign, old_temp)
        result = ingest_jsonl(self.source, self.client, INDEX, checkpoint_path=self.checkpoint)
        self.assertTrue(result["complete"])
        self.assertEqual("preserve", foreign.read_text())
        self.assertEqual("preserve", old_temp.read_text())
        self.assertEqual([], list(self.root.glob(".checkpoint.*.tmp")))

    def test_failed_atomic_save_keeps_checkpoint_and_releases_lease(self):
        with ingestion_lease(self.checkpoint):
            _save_checkpoint(self.checkpoint, {"old": True})
        before = self.checkpoint.read_bytes()
        with patch("analytics311.ingest.os.replace", side_effect=OSError("disk full")):
            def save():
                with ingestion_lease(self.checkpoint):
                    _save_checkpoint(self.checkpoint, {"new": True})
            self.assert_code("io_error", save)
        self.assertEqual(before, self.checkpoint.read_bytes())
        self.assertEqual([], list(self.root.glob(".checkpoint.*.tmp")))
        with ingestion_lease(self.checkpoint):
            pass

    def test_existing_version_two_checkpoint_remains_compatible(self):
        result = ingest_jsonl(self.source, self.client, INDEX, checkpoint_path=self.checkpoint)
        self.assertEqual(2, result["checkpoint_version"])
        before = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.assertEqual(result, ingest_jsonl(self.source, self.client, INDEX, checkpoint_path=self.checkpoint))
        self.assertEqual(before, hashlib.sha256(self.checkpoint.read_bytes()).hexdigest())

    def test_distinct_checkpoints_are_independent_and_missing_parents_created(self):
        with ingestion_lease(self.checkpoint):
            other = self.root / "nested" / "other.json"
            with ingestion_lease(other) as path:
                self.assertEqual(other, path)
                self.assertTrue(other.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
