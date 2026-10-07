import errno
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from analytics311.errors import AnalyticsError
from analytics311.metadata_io import retry_metadata_io
from analytics311.service import atomic_json, read_json


class MetadataIoTests(unittest.TestCase):
    def test_transient_windows_denial_retries_then_returns(self):
        action = Mock(side_effect=[PermissionError(errno.EACCES, "busy"), {"complete": True}])
        with patch("analytics311.metadata_io.os", SimpleNamespace(name="nt")), patch("analytics311.metadata_io.time.sleep") as sleep:
            self.assertEqual({"complete": True}, retry_metadata_io(action))
        self.assertEqual(2, action.call_count)
        sleep.assert_called_once_with(.005)

    def test_persistent_denial_stops_with_bounded_waits(self):
        failure = PermissionError(errno.EACCES, "persistent")
        action = Mock(side_effect=failure)
        with patch("analytics311.metadata_io.os", SimpleNamespace(name="nt")), patch("analytics311.metadata_io.time.sleep") as sleep, \
             self.assertRaises(PermissionError) as caught:
            retry_metadata_io(action)
        self.assertIs(failure, caught.exception)
        self.assertEqual(8, action.call_count)
        self.assertEqual(7, sleep.call_count)
        self.assertAlmostEqual(.225, sum(call.args[0] for call in sleep.call_args_list))

    def test_other_platforms_and_errors_fail_immediately(self):
        unknown_windows_error = PermissionError(errno.EACCES, "unrelated")
        unknown_windows_error.winerror = 123
        cases = [("posix", PermissionError(errno.EACCES, "denied")),
                 ("nt", PermissionError(errno.EPERM, "different permission failure")),
                 ("nt", FileNotFoundError(errno.ENOENT, "missing")),
                 ("nt", OSError(errno.ENOSPC, "full")),
                 ("nt", unknown_windows_error),
                 ("nt", json.JSONDecodeError("malformed", "x", 0))]
        for platform, failure in cases:
            with self.subTest(platform=platform, error=type(failure).__name__):
                action = Mock(side_effect=failure)
                with patch("analytics311.metadata_io.os", SimpleNamespace(name=platform)), patch("analytics311.metadata_io.time.sleep") as sleep, \
                     self.assertRaises(type(failure)):
                    retry_metadata_io(action)
                self.assertEqual(1, action.call_count)
                sleep.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Actual Windows sharing semantics")
    def test_actual_held_reader_releases_before_atomic_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "job.json"
            atomic_json(path, {"status": "running"})
            with path.open(encoding="utf-8") as reader:
                # First native rename must encounter this open reader. Release
                # it only when the bounded sharing retry asks to wait.
                with patch("analytics311.metadata_io.time.sleep", side_effect=lambda delay: reader.close()) as sleep:
                    atomic_json(path, {"status": "complete"})
                self.assertGreaterEqual(sleep.call_count, 1)
            self.assertEqual({"status": "complete"}, read_json(path))
            self.assertEqual(["job.json"], [item.name for item in Path(temporary).iterdir()])

    def test_read_retries_only_io_and_malformed_json_stays_typed(self):
        with patch("analytics311.metadata_io.os", SimpleNamespace(name="nt")), patch("analytics311.metadata_io.time.sleep") as sleep, \
             patch("analytics311.service.Path.read_text", side_effect=[PermissionError(errno.EACCES, "busy"), '{"status":"complete"}']) as read:
            self.assertEqual({"status": "complete"}, read_json("job.json"))
        self.assertEqual(2, read.call_count)
        sleep.assert_called_once_with(.005)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text("not json", encoding="utf-8")
            with patch("analytics311.metadata_io.time.sleep") as sleep, self.assertRaises(AnalyticsError) as caught:
                read_json(path)
            self.assertEqual("invalid_configuration", caught.exception.code)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
