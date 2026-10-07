"""Contract checks: source integrity, explicit time, and fixture grounding."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from graphrag_discovery.records import (
    DomainError, cache_key, canonical_hash, now_utc, text_hash, utc,
    validate_assertion, validate_record,
)


def source(text="A operates Pump P."):
    return {
        "schema_version": "1", "event_id": "doc-v1", "document_id": "doc",
        "version_id": "v1", "operation": "upsert", "text": text,
        "processing_version": "plain-text-v1", "source_sha256": text_hash(text),
        "content_sha256": text_hash(text), "source_uri": "fixture://doc/v1",
        "source_version_ref": "v1", "language": "en", "rights_ref": "authored",
        "access_scope": "public", "source_available_at": "2025-01-05T10:00:00+02:00",
    }


def claim(record):
    return {
        "assertion_id": "a-1", "document_id": "doc", "version_id": "v1",
        "processing_version": "plain-text-v1", "subject_id": "operator-a",
        "subject_label": "A", "object_id": "pump-p", "object_label": "Pump P",
        "text": record["text"], "start": 0, "end": len(record["text"]),
        "modality": "reported", "valid_from": "2025-01-01T00:00:00Z",
        "valid_to": None, "temporal_status": {"from": "known", "to": "open"},
        "method": "authored-fixture",
    }


class TimestampAndHashTests(unittest.TestCase):
    def test_utc_normalizes_offsets_and_preserves_precision(self):
        self.assertEqual(utc("2025-01-01T00:30:00.123456+01:00"), "2024-12-31T23:30:00.123456+00:00")
        self.assertEqual(utc("2024-02-29T01:02:03Z"), "2024-02-29T01:02:03.000000+00:00")
        current = now_utc()
        self.assertEqual(utc(current), current)

    def test_ambiguous_invalid_or_lossy_timestamps_are_rejected(self):
        for value in (None, 123, "2025-01-01", "2025-01-01T00:00:00",
                      "2025-02-29T00:00:00Z", "2025-01-01 00:00:00Z",
                      "2025-01-01T00:00:00-00:00", "2025-01-01T00:00:00.1234567Z",
                      "2025-01-01T00:00:00+24:00", "2025-01-01T00:00:60Z",
                      "2025-01-01T00:00:00+00:60", "2025-01-01T00:00:00-00:99"):
            with self.subTest(value=value), self.assertRaises(DomainError) as caught:
                utc(value)
            self.assertEqual(caught.exception.code, "invalid_timestamp")

    def test_canonical_json_is_order_independent_but_text_is_exact(self):
        self.assertEqual(canonical_hash({"a": [1, "é"], "b": True}), canonical_hash({"b": True, "a": [1, "é"]}))
        self.assertNotEqual(text_hash("é\n"), text_hash("é\r\n"))
        self.assertNotEqual(text_hash("é"), text_hash("e\u0301"))
        for invalid in ({1: "integer key"}, {"a": float("nan")}, (1, 2), {"a": float("inf")}):
            with self.subTest(value=invalid), self.assertRaises(DomainError):
                canonical_hash(invalid)

    def test_error_envelope_is_machine_readable(self):
        error = DomainError("bad_input", "Invalid input.", {"field": "text"})
        self.assertEqual(error.to_dict(), {"code": "bad_input", "message": "Invalid input.", "details": {"field": "text"}})
        self.assertEqual(str(error), "Invalid input.")


class RecordTests(unittest.TestCase):
    def test_upsert_normalizes_without_mutating_input(self):
        record = source()
        record["context"] = {"reference": ["January"]}
        before = deepcopy(record)
        normalized = validate_record(record, "corpus")
        self.assertEqual(normalized["source_available_at"], "2025-01-05T08:00:00.000000+00:00")
        self.assertEqual(normalized["corpus_id"], "corpus")
        self.assertIsNone(normalized["supersedes_version_id"])
        normalized["context"]["reference"].append("changed")
        self.assertEqual(record, before)

    def test_withdrawal_does_not_require_or_replace_source_text(self):
        record = {"schema_version": "1", "event_id": "withdraw-1", "document_id": "doc",
                  "version_id": "v1", "operation": "withdraw", "reason": "Publisher withdrawal",
                  "access_scope": "public"}
        normalized = validate_record(record, "corpus")
        self.assertNotIn("text", normalized)
        self.assertIsNone(normalized["source_available_at"])
        for field, value in (("text", "replacement"), ("ingested_at", "2025-01-01T00:00:00Z")):
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_record({**record, field: value}, "corpus")

    def test_scope_identity_and_first_adapter_are_strict(self):
        changes = [("corpus_id", "other"), ("event_id", ""), ("document_id", "bad/id"),
                   ("event_id", "é"), ("event_id", "a" * 129), ("schema_version", 1),
                   ("processing_version", "html-v1"), ("language", "fr"),
                   ("access_scope", "private"), ("supersedes_version_id", "v1"),
                   ("extra", "unknown"), ("text", "  ")]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_record({**source(), field: value}, "corpus")

    def test_missing_required_upsert_fields_rejected(self):
        for field in ("schema_version", "event_id", "document_id", "version_id", "operation",
                      "access_scope", "text", "processing_version", "content_sha256",
                      "source_sha256", "source_uri", "source_version_ref", "language", "rights_ref"):
            record = source()
            del record[field]
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_record(record, "corpus")

    def test_both_hashes_bind_exact_utf8_text(self):
        record = source("🧭 A operates Pump P.\n")
        self.assertEqual(validate_record(record, "corpus")["text"], record["text"])
        for field in ("source_sha256", "content_sha256"):
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_record({**record, field: "0" * 64}, "corpus")
        with self.assertRaises(DomainError):
            validate_record({**record, "text": record["text"].strip()}, "corpus")

    def test_context_and_request_limits(self):
        deep = None
        for _ in range(10):
            deep = {"next": deep}
        for context in (deep, {"items": [0] * 129}, {"label": "x" * 16385}, {"n": float("nan")}):
            with self.subTest(context_type=type(context).__name__), self.assertRaises(DomainError):
                validate_record({**source(), "context": context}, "corpus")
        with self.assertRaises(DomainError) as caught:
            validate_record({**source(), "context": "x" * 1_048_576}, "corpus")
        self.assertEqual(caught.exception.code, "request_too_large")


class AssertionTests(unittest.TestCase):
    def setUp(self):
        self.record = validate_record(source(), "corpus")

    def test_fixture_claim_keeps_planned_modality_and_explicit_unknowns(self):
        assertion = claim(self.record)
        assertion.update(modality="planned", valid_from=None,
                         temporal_status={"from": "unknown", "to": "open"})
        normalized = validate_assertion(assertion, self.record)
        self.assertEqual(normalized["modality"], "planned")
        self.assertIsNone(normalized["valid_from"])
        self.assertEqual(normalized["supersedes"], [])
        self.assertEqual(normalized["corpus_id"], "corpus")

    def test_unicode_offsets_are_code_points_not_utf8_bytes(self):
        record = validate_record(source("🧭 A operates Pump P. More text."), "corpus")
        assertion = claim(record)
        assertion.update(start=2, end=20, text=record["text"][2:20])
        self.assertEqual(validate_assertion(assertion, record)["text"], "A operates Pump P.")
        with self.assertRaises(DomainError):
            validate_assertion({**assertion, "start": 5}, record)

    def test_offsets_labels_and_source_identity_cannot_be_invented(self):
        changes = [("start", True), ("start", 0.0), ("start", -1), ("end", 0),
                   ("end", 100), ("text", "A owns Pump P."), ("subject_label", "B"),
                   ("object_label", "Pump Q"), ("version_id", "v2"),
                   ("processing_version", "other"), ("corpus_id", "other"),
                   ("method", "llm"), ("modality", "confirmed"), ("confidence", 1)]
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_assertion({**claim(self.record), field: value}, self.record)

    def test_temporal_status_and_intervals_are_consistent(self):
        cases = [
            {"valid_from": None},
            {"valid_to": "2025-01-02T00:00:00Z"},
            {"temporal_status": {"from": "open", "to": "open"}},
            {"temporal_status": {"from": [], "to": "open"}},
            {"temporal_status": {"from": "unknown", "to": "open"}},
            {"temporal_status": {"from": "known", "to": "known"}, "valid_to": "2025-01-01T00:00:00Z"},
            {"temporal_status": {"from": "known", "to": "known"}, "valid_to": "2024-12-31T00:00:00Z"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(DomainError):
                validate_assertion({**claim(self.record), **overrides}, self.record)
        valid = {**claim(self.record), "valid_from": "2025-01-02T00:00:00+02:00",
                 "valid_to": "2025-01-01T23:00:00Z", "temporal_status": {"from": "known", "to": "known"}}
        self.assertEqual(validate_assertion(valid, self.record)["valid_from"], "2025-01-01T22:00:00.000000+00:00")

    def test_supersession_ids_are_valid_unique_and_not_self(self):
        for supersedes in (["a-1"], ["previous", "previous"], ["bad/id"], "previous", [False]):
            with self.subTest(supersedes=supersedes), self.assertRaises(DomainError):
                validate_assertion({**claim(self.record), "supersedes": supersedes}, self.record)

    def test_qualifiers_are_objects_with_explicit_boolean_exclusivity(self):
        for qualifiers in ([], None, "exclusive", True, {"exclusive": "false"}, {"exclusive": 1}):
            with self.subTest(qualifiers=qualifiers):
                with self.assertRaises(DomainError) as caught:
                    validate_assertion({**claim(self.record), "qualifiers": qualifiers}, self.record)
                self.assertEqual(caught.exception.code, "invalid_assertion")
                self.assertEqual(caught.exception.details["field"], "qualifiers")
                with self.assertRaises(DomainError):
                    validate_record({**source(), "qualifiers": qualifiers}, "corpus")
        for qualifiers in ({}, {"exclusive": False}, {"exclusive": True, "authored_note": ["fixture"]}):
            with self.subTest(qualifiers=qualifiers):
                result = validate_assertion({**claim(self.record), "qualifiers": qualifiers}, self.record)
                self.assertEqual(result["qualifiers"], qualifiers)

    def test_cache_context_and_model_changes_invalidate_reuse(self):
        config = {"model": "fixture", "temperature": 0}
        key = cache_key(self.record, config)
        self.assertEqual(key, cache_key(self.record, {"temperature": 0, "model": "fixture"}))
        for record, model, options in (
            ({**self.record, "source_available_at": "2025-02-05T08:00:00.000000+00:00"}, config, {}),
            ({**self.record, "context": {"reference_month": "February"}}, config, {}),
            (self.record, {**config, "model": "other"}, {}),
            (self.record, config, {"identity_map_version": "v2"}),
            (self.record, config, {"prompt_version": "v2"}),
        ):
            with self.subTest(options=options):
                self.assertNotEqual(key, cache_key(record, model, **options))

    def test_json_schemas_are_closed_and_document_runtime_constraints(self):
        schema_dir = Path(__file__).resolve().parents[1] / "schemas"
        for name, example in (("record", source()), ("assertion", claim(self.record))):
            schema = json.loads((schema_dir / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])
            self.assertTrue(set(example).issubset(schema["properties"]))
            self.assertTrue(set(schema["required"]).issubset(example))
            self.assertTrue(schema["x-runtime-validation"])


if __name__ == "__main__":
    unittest.main()
