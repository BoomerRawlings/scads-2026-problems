"""Offline acquisition tests; no public service requests or real dataset edits."""

from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_public_data.py"
SPEC = importlib.util.spec_from_file_location("capture_public_data", SCRIPT)
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


def body(spec):
    if spec["provider"] == "ror":
        value = {"id": "https://ror.org/" + spec["entity_id"], "admin": {"last_modified": {"date": "2026-01-01", "schema_version": "2.1"}}}
    else:
        value = {"entities": {spec["entity_id"]: {"id": spec["entity_id"], "lastrevid": spec["revision"], "modified": "2026-01-01T00:00:00Z"}}}
    return json.dumps(value, indent=2).encode()


class FakeClient:
    def __init__(self, fail=None):
        self.fail, self.calls = fail, []

    def fetch(self, spec):
        self.calls.append(spec["id"])
        if spec["id"] == self.fail:
            raise capture.CaptureError("network_error_attempts_exhausted")
        return body(spec), 1


class FakeClock:
    def __init__(self):
        self.seconds = 0

    def now(self):
        return self.seconds

    def sleep(self, seconds):
        self.seconds += seconds


class Response(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(payload)
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def geturl(self):
        return self.url


class PublicCaptureTests(unittest.TestCase):
    def test_failure_resume_preserves_sources_and_skips_network_for_completed(self):
        specs = capture.SOURCES[:2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaises(capture.CaptureError):
                capture.capture(output, specs, FakeClient(fail=specs[1]["id"]))
            first = output / capture.raw_path(specs[0])
            before = (first.read_bytes(), first.stat().st_mtime_ns)
            failed = json.loads((output / "capture-manifest.json").read_text())
            self.assertEqual(failed["status"], "partial")
            self.assertEqual(failed["failure"]["source_id"], specs[1]["id"])
            client = FakeClient()
            capture.capture(output, specs, client)
            self.assertEqual(client.calls, [specs[1]["id"]])
            self.assertEqual((first.read_bytes(), first.stat().st_mtime_ns), before)
            self.assertEqual(capture.verify_capture(output, specs)["source_count"], 2)
            manifest_before = (output / "capture-manifest.json").read_bytes()
            capture.capture(output, specs, FakeClient())
            self.assertEqual((output / "capture-manifest.json").read_bytes(), manifest_before)

    def test_pinned_revision_mismatch_is_not_saved(self):
        spec = capture.SOURCES[-1]
        wrong = json.loads(body(spec))
        wrong["entities"][spec["entity_id"]]["lastrevid"] += 1
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory, patch.object(client, "fetch", return_value=(json.dumps(wrong).encode(), 1)):
            output = Path(directory)
            with self.assertRaisesRegex(capture.CaptureError, "pinned_revision"):
                capture.capture(output, [spec], client)
            self.assertFalse((output / capture.raw_path(spec)).exists())

    def test_saved_source_corruption_blocks_resume_without_network_or_overwrite(self):
        spec = capture.SOURCES[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            capture.capture(output, [spec], FakeClient())
            path = output / capture.raw_path(spec)
            path.write_bytes(b"corrupt")
            client = FakeClient()
            with self.assertRaisesRegex(capture.CaptureError, "hash_mismatch"):
                capture.capture(output, [spec], client)
            self.assertEqual(client.calls, [])
            self.assertEqual(path.read_bytes(), b"corrupt")

    def test_unrecorded_existing_body_is_never_overwritten(self):
        spec = capture.SOURCES[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / capture.raw_path(spec)
            path.parent.mkdir()
            path.write_bytes(b"existing evidence")
            with self.assertRaisesRegex(capture.CaptureError, "refusing_overwrite"):
                capture.capture(output, [spec], FakeClient())
            self.assertEqual(path.read_bytes(), b"existing evidence")

    def test_retry_after_and_request_spacing(self):
        spec = capture.SOURCES[0]
        clock, requested_at = FakeClock(), []
        headers = Message()
        headers["Retry-After"] = "7"
        def opener(request, timeout):
            requested_at.append(clock.now())
            if len(requested_at) == 1:
                raise urllib.error.HTTPError(spec["url"], 429, "limited", headers, None)
            self.assertEqual(request.get_header("User-agent"), capture.USER_AGENT)
            return Response(body(spec), spec["url"])
        client = capture.BoundedClient(opener, clock.now, clock.sleep)
        raw, attempts = client.fetch(spec)
        self.assertEqual(raw, body(spec))
        self.assertEqual(attempts, 2)
        self.assertEqual(requested_at, [0, 7])
        client.fetch(spec)
        self.assertEqual(requested_at[-1], 8)

    def test_long_retry_after_stops_instead_of_retrying_early(self):
        spec, clock = capture.SOURCES[0], FakeClock()
        headers = Message()
        headers["Retry-After"] = "120"
        def opener(request, timeout):
            raise urllib.error.HTTPError(spec["url"], 503, "busy", headers, None)
        client = capture.BoundedClient(opener, clock.now, clock.sleep)
        with self.assertRaisesRegex(capture.CaptureError, "retry_after_outside_budget"):
            client.fetch(spec)
        self.assertEqual(client.requests, 1)
        self.assertEqual(clock.now(), 0)

    def test_attempt_budget_and_byte_budget_fail_closed(self):
        spec, clock = capture.SOURCES[0], FakeClock()
        def unavailable(request, timeout):
            raise urllib.error.URLError("offline")
        client = capture.BoundedClient(unavailable, clock.now, clock.sleep)
        with self.assertRaisesRegex(capture.CaptureError, "attempts_exhausted"):
            client.fetch(spec)
        self.assertEqual(client.requests, 3)
        client = capture.BoundedClient(lambda request, timeout: Response(b"x" * 20, spec["url"]), clock.now, clock.sleep)
        with patch.dict(capture.POLICY, {"maximum_source_bytes": 16}):
            with self.assertRaisesRegex(capture.CaptureError, "source_byte_limit"):
                client.fetch(spec)

    def test_arbitrary_source_and_redirect_rejected(self):
        spec = dict(capture.SOURCES[0], url="https://example.org/unapproved")
        with self.assertRaisesRegex(capture.CaptureError, "outside_fixed_plan"):
            capture.BoundedClient().fetch(spec)
        with self.assertRaisesRegex(capture.CaptureError, "redirect_rejected"):
            capture.NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://example.org/")


if __name__ == "__main__":
    unittest.main()
