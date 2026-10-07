import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.ingest import freeze_index, ingest_jsonl, normalize_record, validate_normalized_record


INDEX = "nyc311-test-v1"


def raw(identifier="1", **changes):
    value = {"unique_key": identifier, "status": "Closed", "created_date": "2025-01-01T12:00:00",
             "closed_date": "2025-01-01T14:30:00", "latitude": "40.7", "longitude": "-73.9"}
    value.update(changes)
    return value


class BulkClient:
    def __init__(self, fail_batch=None):
        self.records = {}
        self.batches = 0
        self.fail_batch = fail_batch
        self.uuid = "test-uuid"

    def request(self, method, path, body=None):
        if path.endswith("/_settings"):
            return {INDEX: {"settings": {"index": {"uuid": self.uuid}}}}
        if path.endswith("/_refresh"):
            return {"_shards": {"failed": 0}}
        if path.endswith("/_count"):
            return {"_shards": {"failed": 0}, "count": len(self.records)}
        self.batches += 1
        lines = [json.loads(line) for line in body.splitlines()]
        items = []
        for i in range(0, len(lines), 2):
            identifier = lines[i]["index"]["_id"]
            failed = self.batches == self.fail_batch and i == 0
            if not failed:
                self.records[identifier] = lines[i + 1]
            items.append({"index": {"status": 400 if failed else 200}})
        return {"errors": self.batches == self.fail_batch, "items": items}


class IngestionTests(unittest.TestCase):
    def test_failed_bulk_source_collision_cannot_hide_behind_acknowledged_prefix(self):
        from analytics311.ingest import _fingerprint
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            original = "".join(json.dumps(raw(str(i), descriptor=f"row-{i}")) + "\n" for i in range(4)).encode()
            source.write_bytes(original)

            def changed_after_hash(path):
                digest = _fingerprint(path)
                # Only the failed second batch differs. A successful item from
                # that batch overwrites a previously acknowledged request ID.
                source.write_bytes(original.replace(b'"unique_key": "3"', b'"unique_key": "0"'))
                return digest

            client = BulkClient(fail_batch=2)
            with patch("analytics311.ingest._fingerprint", side_effect=changed_after_hash):
                with self.assertRaises(AnalyticsError):
                    ingest_jsonl(source, client, INDEX, batch_size=2, checkpoint_path=checkpoint)
            self.assertEqual("row-3", client.records["0"]["descriptor"])
            saved = json.loads(checkpoint.read_text())
            self.assertEqual(2, saved["processed_rows"])
            self.assertIn("pending", saved)
            source.write_bytes(original)
            client.fail_batch = None
            with self.assertRaises(AnalyticsError) as error:
                ingest_jsonl(source, client, INDEX, batch_size=2, checkpoint_path=checkpoint)
            self.assertEqual("invalid_checkpoint", error.exception.code)
            self.assertEqual(2, client.batches)

    def test_same_metadata_rewrite_is_quarantined_before_completion(self):
        from analytics311.ingest import _fingerprint
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            original = (json.dumps(raw("1")) + "\n").encode()
            source.write_bytes(original)
            original_stat = source.stat()

            def changed_after_hash(path):
                digest = _fingerprint(path)
                source.write_bytes(original.replace(b'"unique_key": "1"', b'"unique_key": "2"'))
                os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
                return digest

            with patch("analytics311.ingest._fingerprint", side_effect=changed_after_hash):
                with self.assertRaises(AnalyticsError) as error:
                    ingest_jsonl(source, BulkClient(), INDEX, checkpoint_path=checkpoint)
            self.assertEqual("source_changed", error.exception.code)
            saved = json.loads(checkpoint.read_text())
            self.assertFalse(saved["complete"])
            self.assertTrue(saved["quarantined"])
            # Restoring original bytes cannot make the already wrong index safe.
            source.write_bytes(original)
            with self.assertRaises(AnalyticsError) as error:
                ingest_jsonl(source, BulkClient(), INDEX, checkpoint_path=checkpoint)
            self.assertEqual("invalid_checkpoint", error.exception.code)

    def test_interrupted_changed_prefix_cannot_resume_against_restored_source(self):
        from analytics311.ingest import _fingerprint
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            original = "".join(json.dumps(raw(str(i))) + "\n" for i in range(3)).encode()
            source.write_bytes(original)

            def changed_after_hash(path):
                digest = _fingerprint(path)
                source.write_bytes(original.replace(b'"unique_key": "0"', b'"unique_key": "9"'))
                return digest

            client = BulkClient(fail_batch=2)
            with patch("analytics311.ingest._fingerprint", side_effect=changed_after_hash):
                with self.assertRaises(AnalyticsError):
                    ingest_jsonl(source, client, INDEX, batch_size=1, checkpoint_path=checkpoint)
            self.assertIn("9", client.records)
            source.write_bytes(original)
            client.fail_batch = None
            batches = client.batches
            with self.assertRaises(AnalyticsError) as error:
                ingest_jsonl(source, client, INDEX, batch_size=1, checkpoint_path=checkpoint)
            self.assertEqual("invalid_checkpoint", error.exception.code)
            self.assertEqual(batches, client.batches)

    def test_malformed_or_old_checkpoint_never_skips_work(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
            client = BulkClient()
            saved = ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            for changed in ([], {**saved, "checkpoint_version": 1}, {**saved, "complete": "true"},
                            {**saved, "source_lines": True}, {**saved, "quality_counts": {"x": -1}},
                            {**saved, "processed_rows": 2}, {**saved, "byte_offset": 1},
                            {**saved, "prefix_sha256": "0" * 64}):
                with self.subTest(checkpoint=changed):
                    checkpoint.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaises(AnalyticsError) as error:
                        ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
                    self.assertEqual("invalid_checkpoint", error.exception.code)
            self.assertEqual(1, client.batches)

    def test_checkpoint_requires_jsonl_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
            client = BulkClient(fail_batch=1)
            with self.assertRaises(AnalyticsError):
                ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            saved = json.loads(checkpoint.read_text())
            saved.update(byte_offset=1, prefix_sha256=hashlib.sha256(source.read_bytes()[:1]).hexdigest())
            checkpoint.write_text(json.dumps(saved), encoding="utf-8")
            client.fail_batch = None
            with self.assertRaises(AnalyticsError) as error:
                ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            self.assertEqual("invalid_checkpoint", error.exception.code)
            self.assertEqual(1, client.batches)

    def test_blank_lines_and_unterminated_last_record_are_replayable(self):
        for payload in (b"", b"\n\n", b"\n" + json.dumps(raw()).encode() + b"\n\n", json.dumps(raw()).encode()):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
                source.write_bytes(payload)
                client = BulkClient()
                saved = ingest_jsonl(source, client, INDEX, batch_size=1, checkpoint_path=checkpoint)
                self.assertTrue(saved["complete"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), saved["prefix_sha256"])
                self.assertEqual(saved, ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint))

    def test_wrong_record_or_malformed_bulk_acknowledgement_cannot_checkpoint(self):
        for item in (None, {"index": []}, {"index": {"status": 201, "_id": "wrong"}},
                     {"index": {"status": 201, "_index": "wrong-index"}}):
            with self.subTest(item=item), tempfile.TemporaryDirectory() as directory:
                source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
                source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
                client = BulkClient()
                request = client.request

                def invalid_ack(method, path, body=None):
                    if path.endswith("/_bulk"):
                        return {"errors": False, "items": [item]}
                    return request(method, path, body)

                client.request = invalid_ack
                with self.assertRaises(AnalyticsError) as error:
                    ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
                self.assertEqual("partial_ingestion", error.exception.code)
                self.assertEqual(0, json.loads(checkpoint.read_text())["processed_rows"])

    def test_timezone_duration_and_geojson_axis_order(self):
        result = normalize_record(raw(latitude=None, longitude=None, location={"type": "Point", "coordinates": [-73.9, 40.7]}))
        self.assertEqual(result["created_date"], "2025-01-01T17:00:00.000Z")
        self.assertEqual(result["closure_hours"], 2.5)
        self.assertEqual(result["location"], {"lat": 40.7, "lon": -73.9})
        self.assertEqual(result["quality_flags"], [])

    def test_ambiguous_and_nonexistent_dst_are_not_invented(self):
        for value, flag in (("2025-11-02T01:30:00", "ambiguous_created_date"),
                            ("2025-03-09T02:30:00", "nonexistent_created_date")):
            result = normalize_record(raw(created_date=value))
            self.assertNotIn("created_date", result)
            self.assertNotIn("closure_hours", result)
            self.assertIn(flag, result["quality_flags"])
            self.assertEqual(result["source_created_date"], value)

    def test_explicit_dst_offset_resolves_ambiguity(self):
        result = normalize_record(raw(created_date="2025-11-02T01:30:00-04:00", closed_date="2025-11-02T01:30:00-05:00"))
        self.assertEqual(result["closure_hours"], 1)

    def test_invalid_geometry_and_duration_excluded(self):
        result = normalize_record(raw(latitude="NaN", closed_date="2024-12-31T00:00:00"))
        self.assertNotIn("location", result)
        self.assertNotIn("closure_hours", result)
        self.assertIn("invalid_geometry", result["quality_flags"])
        self.assertIn("negative_closure_duration", result["quality_flags"])
        self.assertTrue(result["is_closed"])

    def test_non_closed_status_never_receives_closure_metric(self):
        result = normalize_record(raw(status="Open"))
        self.assertFalse(result["is_closed"])
        self.assertNotIn("closure_hours", result)
        self.assertIn("closed_date_without_closed_status", result["quality_flags"])

    def test_malformed_date_type_flagged(self):
        result = normalize_record(raw(created_date=["invalid"]))
        self.assertIn("invalid_created_date", result["quality_flags"])

    def test_timezone_overflow_is_invalid_source_data(self):
        for value in ("0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59"):
            with self.subTest(value=value):
                result = normalize_record(raw(created_date=value))
                self.assertIn("invalid_created_date", result["quality_flags"])
                self.assertNotIn("created_date", result)

    def test_missing_identifier_rejected(self):
        for identifier in (None, "", True):
            with self.assertRaises(AnalyticsError):
                normalize_record(raw(identifier))

    def test_normalized_ingestion_preserves_dst_and_enrichment_audit(self):
        record = normalize_record(raw(created_date="2025-11-02T01:30:00", latitude="NaN"))
        record["nta_join_status"] = "missing_geometry"
        record["quality_flags"].append("nta_missing_geometry")
        self.assertEqual(validate_normalized_record(record), record)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normalized.jsonl"
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")
            client = BulkClient()
            ingest_jsonl(source, client, INDEX, normalized=True)
            self.assertEqual(client.records["1"], record)

    def test_normalized_rejects_forged_metrics_source_dates_and_extra_fields(self):
        record = normalize_record(raw())
        for change in ({"closure_hours": 999}, {"closure_hours": 10 ** 1000}, {"is_closed": False}, {"unknown": 1},
                       {"created_date": "2024-01-01T17:00:00Z"}, {"quality_flags": [] , "location": {"lat": 500, "lon": 0}}):
            with self.subTest(change=change), self.assertRaises(AnalyticsError):
                validate_normalized_record({**record, **change})

    def test_normalized_non_string_invalid_date_audit_survives(self):
        record = normalize_record(raw(created_date=123))
        self.assertEqual(validate_normalized_record(record), record)

    def test_mapping_covers_only_normalized_fields(self):
        mapping_path = Path(__file__).resolve().parents[1] / "config" / "mapping.json"
        mapping = json.loads(mapping_path.read_text())
        self.assertEqual(mapping["mappings"]["dynamic"], "strict")
        self.assertTrue(set(normalize_record(raw())) <= set(mapping["mappings"]["properties"]))

    def test_failed_batch_resumes_without_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text("".join(json.dumps(raw(str(i))) + "\n" for i in range(5)), encoding="utf-8")
            client = BulkClient(fail_batch=2)
            with self.assertRaises(AnalyticsError) as caught:
                ingest_jsonl(source, client, INDEX, batch_size=2, checkpoint_path=checkpoint)
            self.assertEqual(caught.exception.code, "partial_ingestion")
            self.assertEqual(json.loads(checkpoint.read_text())["processed_rows"], 2)
            client.fail_batch = None
            result = ingest_jsonl(source, client, INDEX, batch_size=2, checkpoint_path=checkpoint)
            self.assertTrue(result["complete"])
            self.assertEqual(result["processed_rows"], 5)
            self.assertEqual(set(client.records), {"0", "1", "2", "3", "4"})
            calls = client.batches
            self.assertEqual(ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint), result)
            self.assertEqual(client.batches, calls)

    def test_checkpoint_rejects_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
            client = BulkClient()
            ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            source.write_text(json.dumps(raw("different")) + "\n", encoding="utf-8")
            with self.assertRaises(AnalyticsError) as caught:
                ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            self.assertEqual(caught.exception.code, "invalid_checkpoint")

    def test_quality_counts_and_upsert_uniqueness(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            source.write_text((json.dumps(raw(latitude=None, longitude=None)) + "\n") * 2, encoding="utf-8")
            client = BulkClient()
            result = ingest_jsonl(source, client, INDEX)
            self.assertEqual(result["processed_rows"], 2)
            self.assertEqual(result["quality_counts"]["missing_geometry"], 2)
            self.assertEqual(len(client.records), 1)

    def test_checkpoint_rejects_recreated_index(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
            client = BulkClient()
            ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            client.uuid = "replacement-index"
            with self.assertRaises(AnalyticsError) as caught:
                ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            self.assertEqual(caught.exception.code, "invalid_checkpoint")

    def test_new_job_rejects_unrelated_existing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            source.write_text(json.dumps(raw("new")) + "\n", encoding="utf-8")
            client = BulkClient()
            client.records["unrelated"] = normalize_record(raw("unrelated"))
            with self.assertRaises(AnalyticsError) as caught:
                ingest_jsonl(source, client, INDEX)
            self.assertIn("empty index", caught.exception.message)
            self.assertEqual(client.batches, 0)

    def test_failed_first_batch_has_replayable_zero_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            source, checkpoint = Path(directory) / "source.jsonl", Path(directory) / "checkpoint.json"
            source.write_text("".join(json.dumps(raw(str(i))) + "\n" for i in range(2)), encoding="utf-8")
            client = BulkClient(fail_batch=1)
            with self.assertRaises(AnalyticsError):
                ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            self.assertEqual(len(client.records), 1)
            self.assertEqual(json.loads(checkpoint.read_text())["processed_rows"], 0)
            client.fail_batch = None
            result = ingest_jsonl(source, client, INDEX, checkpoint_path=checkpoint)
            self.assertEqual(result["processed_rows"], 2)
            self.assertEqual(set(client.records), {"0", "1"})

    def test_freeze_checks_shards_and_exact_unique_count(self):
        class Client:
            def request(self, method, path, body=None):
                if path.endswith("/_block/write"):
                    return {"acknowledged": True, "shards_acknowledged": True,
                            "indices": [{"name": INDEX, "blocked": True}]}
                if path.endswith("/_refresh"):
                    return {"_shards": {"failed": 0}}
                if path.endswith("/_settings"):
                    return {INDEX: {"settings": {"index": {"uuid": "test-uuid"}}}}
                return {"count": 2, "_shards": {"failed": 0}}
        self.assertEqual(freeze_index(Client(), INDEX, 2), {"index": INDEX, "row_count": 2, "immutable": True, "index_uuid": "test-uuid"})
        with self.assertRaises(AnalyticsError) as caught:
            freeze_index(Client(), INDEX, 3)
        self.assertEqual(caught.exception.code, "count_mismatch")


if __name__ == "__main__":
    unittest.main()
