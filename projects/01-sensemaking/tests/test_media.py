"""Verify actual media payloads and media-specific failure boundaries."""

from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from sensemaking import Workspace

try:
    from PIL import Image
    from media_tools import inspect_media, read_media
except ImportError:
    Image = None


@unittest.skipUnless(Image is not None, "Install requirements.txt to test media decoding")
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace(PROJECT / "data")
        self.addCleanup(self.workspace.close)

    def decode_image(self, block):
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["mimeType"], "image/png")
        raw = base64.b64decode(block["data"], validate=True)
        decoded = Image.open(BytesIO(raw))
        self.addCleanup(decoded.close)
        decoded.load()
        self.assertEqual(decoded.format, "PNG")
        self.assertEqual(decoded.mode, "RGB")
        self.assertEqual(decoded.size, (1280, 720))
        return decoded

    def test_png_returns_source_pixels_and_media_hash(self):
        blocks = read_media(self.workspace, "img-note-001")
        self.assertEqual(len(blocks), 2)
        header = json.loads(blocks[0]["text"])
        self.assertEqual(header["evidence_id"], "img-note-001")
        source = self.workspace._safe_path(header["media_path"])
        self.assertEqual(header["media_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertIn("not independent corroboration", header["provenance"])
        decoded = self.decode_image(blocks[1])
        with Image.open(source) as original:
            self.assertEqual(decoded.tobytes(), original.convert("RGB").tobytes())

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test actual MP4 decoding")
    def test_video_returns_three_distinct_timestamped_source_frames(self):
        timestamps = [0, 14, 27]
        blocks = read_media(self.workspace, "video-tx-001", timestamps)
        self.assertEqual(len(blocks), 7)
        header = json.loads(blocks[0]["text"])
        self.assertEqual(header["evidence_id"], "video-tx-001")
        source = self.workspace._safe_path(header["media_path"])
        self.assertEqual(header["media_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertIn("Sampled frames", header["note"])
        decoded_frames = []
        for position, timestamp in enumerate(timestamps):
            locator = blocks[1 + position * 2]["text"]
            self.assertIn(f"sampled source frame at {timestamp:.6f} seconds", locator)
            self.assertIn(f"requested seek offset {timestamp:.3f} seconds", locator)
            self.assertIn("video-tx-001", locator)
            self.assertIn("no audio processing", locator)
            image = self.decode_image(blocks[2 + position * 2])
            # Compare the content region, excluding the changing timestamp footer.
            decoded_frames.append(image.crop((40, 235, 1240, 600)).tobytes())
        self.assertEqual(len(set(decoded_frames)), 3)

    def test_annotations_without_media_do_not_masquerade_as_pixels(self):
        for evidence_id in ("img-note-002", "video-tx-002", "memo-001"):
            with self.subTest(evidence_id=evidence_id), self.assertRaisesRegex(ValueError, "No raw media attached"):
                read_media(self.workspace, evidence_id)

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test video timestamp validation")
    def test_invalid_video_timestamps_are_rejected_before_decode(self):
        invalid = [[], [-1], [3601], [True], ["14"], [float("nan")], [float("inf")], [0, 1, 2, 3, 4]]
        with patch("media_tools.subprocess.run") as decoder:
            for timestamps in invalid:
                with self.subTest(timestamps=timestamps), self.assertRaisesRegex(ValueError, "finite timestamps"):
                    read_media(self.workspace, "video-tx-001", timestamps)
            decoder.assert_not_called()

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test video bounds")
    def test_timestamp_beyond_source_duration_reports_no_frame(self):
        with self.assertRaisesRegex(ValueError, "Could not decode video frame"):
            read_media(self.workspace, "video-tx-001", [31])

    def test_missing_ffmpeg_reports_actionable_failure(self):
        with patch("media_tools.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "ffmpeg is required"):
                read_media(self.workspace, "video-tx-001", [0])

    def test_media_source_paths_and_formats_are_checked(self):
        record = self.workspace.read("img-note-001")
        for path, message in (
            ("../outside.png", "within data directory"),
            ("media/not-present.png", "does not exist"),
            ("records.csv", "Supported source formats"),
        ):
            record["media_path"] = path
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
                read_media(self.workspace, "img-note-001")

    @unittest.skipUnless(shutil.which("ffprobe"), "Install ffprobe to test source duration")
    def test_video_metadata_probes_duration_and_safe_source_hash(self):
        metadata = inspect_media(self.workspace, "video-tx-001")
        self.assertTrue(metadata["available"])
        self.assertAlmostEqual(metadata["duration_seconds"], 30.0, places=1)
        timestamps = metadata["suggested_timestamps"]
        self.assertLessEqual(len(timestamps), 3)
        self.assertEqual(timestamps[0], 0.0)
        self.assertGreater(timestamps[-1], timestamps[1])
        self.assertLess(timestamps[-1], metadata["duration_seconds"])
        self.assertEqual(metadata["media_sha256"], hashlib.sha256(self.workspace._safe_path(metadata["media_path"]).read_bytes()).hexdigest())
        self.assertIn("not independent corroboration", metadata["provenance"])
        self.assertNotIn("local_path", metadata)

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test duration-derived decoding")
    def test_default_video_samples_follow_duration_not_fixture_times(self):
        with patch("media_tools._video_duration", return_value=12.0):
            blocks = read_media(self.workspace, "video-tx-001")
        self.assertEqual(len(blocks), 7)
        header = json.loads(blocks[0]["text"])
        self.assertEqual(header["duration_seconds"], 12.0)
        self.assertEqual(header["sample_selection"], "duration-derived")
        for index, timestamp in enumerate((0, 5.5, 11)):
            self.assertIn(f"requested seek offset {timestamp:.3f} seconds", blocks[1 + 2 * index]["text"])
        self.assertEqual([sample["source_timestamp_seconds"] for sample in header["samples"]], [0, 6, 11])

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test decoded source timestamps")
    def test_fractional_seek_reports_actual_source_frame_and_audit_locator(self):
        from run_agent import collect_audit

        fractional = read_media(self.workspace, "video-tx-001", [14.5])
        exact = read_media(self.workspace, "video-tx-001", [15])
        self.assertEqual(fractional[2]["data"], exact[2]["data"])
        header = json.loads(fractional[0]["text"])
        self.assertEqual(header["samples"], [{"requested_seek_seconds": 14.5, "source_pts": 245760,
                                            "source_time_base": "1/16384", "source_timestamp_seconds": 15.0}])
        stream = json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call",
                            "server": "sensemaking", "tool": "read_media", "status": "completed",
                            "arguments": {"evidence_id": "video-tx-001", "timestamps": [14.5]},
                            "result": {"content": fractional}}})
        _, _, media_reads = collect_audit(stream, {"video-tx-001"})
        self.assertEqual(media_reads, {"video-tx-001": {15.0}})

    @unittest.skipUnless(shutil.which("ffmpeg"), "Install ffmpeg to test missing timestamp handling")
    def test_missing_decoded_timestamp_does_not_relabel_pixels_with_seek_time(self):
        from subprocess import CompletedProcess

        with patch("media_tools.subprocess.run", return_value=CompletedProcess([], 0, stdout=b"pixels", stderr=b"no timestamps")):
            with self.assertRaisesRegex(ValueError, "no usable source presentation timestamp"):
                read_media(self.workspace, "video-tx-001", [14.5])

    def test_missing_duration_is_explicit_and_metadata_paths_are_safe(self):
        with patch("media_tools.shutil.which", return_value=None):
            metadata = inspect_media(self.workspace, "video-tx-001")
        self.assertIsNone(metadata["duration_seconds"])
        self.assertEqual(metadata["suggested_timestamps"], [0.0])
        self.assertIn("Duration unavailable", metadata["note"])
        self.workspace.read("video-tx-001")["media_path"] = "../outside.mp4"
        with self.assertRaisesRegex(ValueError, "within data directory"):
            inspect_media(self.workspace, "video-tx-001")


if __name__ == "__main__":
    unittest.main()
