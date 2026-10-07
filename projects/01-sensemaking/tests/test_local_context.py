"""No server/inference: scripted root-route responses test admission only.

Pinned endpoint behavior: llama.cpp b11457 server-context.cpp:4927-4985.
Full response_format/schema propagation: server-common.cpp:1205-1332.
These fixtures do not establish agreement with live model prompt-token usage.
"""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from local_context import ContextAdmissionError, MAX_INTEGER, admit_text_context


class LocalContextTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "model": "local-alias", "stream": False,
            "messages": [{"role": "system", "content": "PRIVATE_SYSTEM_雪"},
                         {"role": "user", "content": [{"type": "text", "text": "PRIVATE_SOURCE_é"}]}],
            "temperature": 0.6, "seed": 0, "max_tokens": 100,
            "reasoning_budget_tokens": 30,
            "chat_template_kwargs": {"enable_thinking": True},
            "response_format": {"type": "json_object", "schema": {"type": "object", "properties": {
                "private": {"type": "string", "const": "PRIVATE_SCHEMA_VALUE"}}}},
        }
        self.prompt = "<|im_start|>PRIVATE_RENDERED_雪<|im_end|><|im_start|>assistant"
        self.calls = []

    def callback(self, route, payload, timeout):
        self.calls.append((route, copy.deepcopy(payload), timeout))
        if route == "/apply-template":
            return {"prompt": self.prompt}
        if route == "/tokenize":
            return {"tokens": [0, 1, 10, 100, 1000]}
        self.fail("Unexpected route, possibly inference: " + route)

    def admit(self, callback=None, payload=None, **options):
        return admit_text_context(self.payload if payload is None else payload,
                                  callback or self.callback, **{"timeout": 10, "token_limit": 1000, **options})

    def error(self, code, **options):
        with self.assertRaises(ContextAdmissionError) as caught:
            self.admit(**options)
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(caught.exception.metadata.get("admitted", False))
        return caught.exception

    def test_exact_payload_settings_schema_root_routes_and_special_token_flags(self):
        original = copy.deepcopy(self.payload)
        result = self.admit()
        self.assertEqual([call[0] for call in self.calls], ["/apply-template", "/tokenize"])
        self.assertEqual(self.calls[0][1], original)
        self.assertEqual(self.calls[1][1], {"content": self.prompt, "parse_special": True,
                                          "add_special": False, "with_pieces": False})
        self.assertEqual(self.payload, original)
        self.assertTrue(result["admitted"])
        self.assertFalse(result["exact_model_fit_verified"])
        self.assertEqual(result["prompt_tokens"], 5)
        self.assertEqual(result["reserved_tokens"], 5 + 100 + 128)
        self.assertEqual(result["remaining_tokens"], 1000 - 233)
        # max_tokens already includes thinking; reasoning budget is not added twice.
        self.assertEqual(result["max_tokens"], 100)

    def test_exact_limit_passes_and_one_token_overflow_fails(self):
        self.assertTrue(self.admit(token_limit=233)["admitted"])
        error = self.error("context_token_limit", token_limit=232)
        self.assertEqual(error.metadata["prompt_tokens"], 5)
        self.assertEqual(error.metadata["remaining_tokens"], -1)

    def test_metadata_contains_only_counts_hashes_limits_and_fixed_flags(self):
        result = self.admit()
        self.assertEqual(set(result), {
            "policy", "admitted", "exact_model_fit_verified", "token_limit", "safety_margin",
            "max_request_bytes", "max_response_bytes", "timeout_seconds", "max_tokens",
            "canonical_request_bytes", "canonical_request_sha256", "generation_request_bytes",
            "template_request_bytes", "template_response_canonical_bytes", "rendered_prompt_bytes",
            "rendered_prompt_sha256", "tokenize_request_bytes", "tokenize_response_canonical_bytes",
            "prompt_tokens", "reserved_tokens", "remaining_tokens"})
        raw = json.dumps(result)
        for secret in ("PRIVATE_SYSTEM", "PRIVATE_SOURCE", "PRIVATE_SCHEMA", "PRIVATE_RENDERED",
                       self.prompt, "local-alias", '"tokens"', '"messages"'):
            self.assertNotIn(secret, raw)
        canonical = json.dumps(self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(result["canonical_request_sha256"], hashlib.sha256(canonical).hexdigest())
        self.assertEqual(result["canonical_request_bytes"], len(canonical))
        self.assertEqual(result["rendered_prompt_sha256"], hashlib.sha256(self.prompt.encode()).hexdigest())
        self.assertEqual(result["rendered_prompt_bytes"], len(self.prompt.encode()))

    def test_failure_metadata_never_contains_response_prompt_or_source(self):
        error = self.error("context_token_limit", token_limit=1)
        self.assertEqual(error.metadata["prompt_tokens"], 5)
        combined = str(error) + json.dumps(error.metadata)
        for secret in ("PRIVATE_SYSTEM", "PRIVATE_SOURCE", "PRIVATE_SCHEMA", "PRIVATE_RENDERED"):
            self.assertNotIn(secret, combined)

    def test_canonical_and_actual_wire_bytes_have_separate_measurements(self):
        canonical = json.dumps(self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        wire = json.dumps(self.payload, ensure_ascii=False).encode()
        self.assertLess(len(canonical), len(wire))
        error = self.error("context_request_bytes", max_request_bytes=len(wire) - 1)
        self.assertEqual(error.metadata["canonical_request_bytes"], len(canonical))
        self.assertEqual(error.metadata["generation_request_bytes"], len(wire))
        self.assertEqual(self.calls, [])
        self.error("context_request_bytes", max_request_bytes=len(canonical) - 1)
        self.assertEqual(self.calls, [])

    def test_template_and_tokenize_wire_requests_bounded_independently(self):
        wire_size = len(json.dumps(self.payload, ensure_ascii=False).encode())
        self.prompt = "x" * wire_size
        self.error("context_request_bytes", max_request_bytes=wire_size)
        self.assertEqual([call[0] for call in self.calls], ["/apply-template"])

    def test_template_response_bound(self):
        self.prompt = "雪" * 100
        self.error("context_response_bytes", max_response_bytes=200)
        self.assertEqual(len(self.calls), 1)

    def test_token_response_bound(self):
        def oversized(route, payload, timeout):
            return {"prompt": "ok"} if route == "/apply-template" else {"tokens": [1234567] * 100}
        self.error("context_response_bytes", callback=oversized, max_response_bytes=200)

    def test_media_unknown_blocks_and_nontext_content_fail_before_request(self):
        contents = ([{"type": "image_url", "image_url": {"url": "data:image/png;base64,PRIVATE_IMAGE"}}],
                    [{"type": "input_audio", "input_audio": {"data": "PRIVATE_AUDIO"}}],
                    [{"type": "text", "text": "ok", "unknown": True}],
                    [{"type": "text", "text": 1}], [{"type": "future", "text": "ok"}],
                    ["text"], None, 1, {"text": "ok"})
        for content in contents:
            with self.subTest(content_type=type(content).__name__):
                payload = copy.deepcopy(self.payload)
                payload["messages"][1]["content"] = content
                error = self.error("context_unsupported_content", payload=payload)
                self.assertNotIn("PRIVATE_IMAGE", str(error) + json.dumps(error.metadata))
                self.assertEqual(self.calls, [])

    def test_malformed_generation_requests_fail_before_request(self):
        cases = ([], {}, {"messages": []}, {"messages": "text"},
                 {"messages": [{"role": 3, "content": "text"}]},
                 {"chat_template_kwargs": None}, {"chat_template_kwargs": {"enable_thinking": "true"}})
        for change in cases:
            payload = {**self.payload, **change} if isinstance(change, dict) else change
            if change == {}: payload = {}
            with self.subTest(change=change):
                self.error("context_invalid_request", payload=payload)
                self.assertEqual(self.calls, [])

    def test_invalid_integer_limits_and_generation_allowance_fail(self):
        for name in ("token_limit", "safety_margin", "max_request_bytes", "max_response_bytes"):
            for value in (True, False, -1, 1.5, "100", None, MAX_INTEGER + 1):
                with self.subTest(name=name, value=value):
                    self.error("context_invalid_limits", **{name: value})
        for name in ("token_limit", "max_request_bytes", "max_response_bytes"):
            self.error("context_invalid_limits", **{name: 0})
        for value in (True, False, 0, -1, 1.5, None, "100", MAX_INTEGER + 1):
            payload = {**self.payload, "max_tokens": value}
            with self.subTest(max_tokens=value):
                self.error("context_invalid_request", payload=payload)
        self.assertEqual(self.calls, [])

    def test_timeout_validation_including_nonfinite_and_huge_integer(self):
        for timeout in (True, False, 0, -1, "10", None, float("inf"), float("nan"), 10 ** 1000):
            with self.subTest(timeout_type=type(timeout).__name__):
                self.error("context_invalid_limits", timeout=timeout)
        self.assertEqual(self.calls, [])

    def test_nonfinite_unserializable_and_invalid_utf8_generation_fails_safely(self):
        for value in (float("nan"), float("inf"), object(), "\ud800"):
            payload = {**self.payload, "unknown": value}
            self.error("context_invalid_json", payload=payload)
        self.assertEqual(self.calls, [])

    def test_invalid_template_responses_have_no_count_fallback(self):
        for response in ({}, {"prompt": ""}, {"prompt": None}, {"prompt": []},
                         {"prompt": "text", "prompt_tokens": 1}, {"count": 5}, {"error": "PRIVATE_ERROR"}):
            with self.subTest(response=response):
                self.error("context_invalid_template", callback=lambda *_: response)

    def test_unknown_malformed_and_noninteger_token_results_fail(self):
        responses = ({}, {"count": 5}, {"tokens": []}, {"tokens": 5}, {"tokens": None},
                     {"tokens": [True]}, {"tokens": [-1]}, {"tokens": [1.5]}, {"tokens": ["1"]},
                     {"tokens": [{"id": 1, "piece": "PRIVATE_PIECE"}]},
                     {"tokens": [MAX_INTEGER + 1]}, {"tokens": [1], "count": "unknown"})
        for response in responses:
            def malformed(route, payload, timeout):
                return {"prompt": "text"} if route == "/apply-template" else response
            with self.subTest(response=response):
                self.error("context_invalid_tokens", callback=malformed)

    def test_non_object_response_and_invalid_response_json(self):
        self.error("context_invalid_response", callback=lambda *_: [])
        self.error("context_invalid_json", callback=lambda *_: {"prompt": "\ud800"})
        self.error("context_invalid_json", callback=lambda *_: {"prompt": "text", "count": float("nan")})

    def test_one_shared_deadline_passes_only_remaining_budget_to_each_request(self):
        clock = [100.0]
        def timed(route, payload, timeout):
            self.calls.append((route, copy.deepcopy(payload), timeout))
            clock[0] += 3 if route == "/apply-template" else 1
            return {"prompt": "text"} if route == "/apply-template" else {"tokens": [1]}
        with patch("local_context.time.monotonic", side_effect=lambda: clock[0]):
            self.assertTrue(self.admit(callback=timed, timeout=5)["admitted"])
        self.assertEqual([call[2] for call in self.calls], [5.0, 2.0])

    def test_elapsed_deadline_stops_before_second_call_or_admission(self):
        for slow_route in ("/apply-template", "/tokenize"):
            clock = [100.0]
            calls = []
            def late(route, payload, timeout):
                calls.append(route)
                if route == slow_route: clock[0] += 6
                return {"prompt": "text"} if route == "/apply-template" else {"tokens": [1]}
            with self.subTest(route=slow_route), patch("local_context.time.monotonic", side_effect=lambda: clock[0]):
                self.error("context_preflight_timeout", callback=late, timeout=5)
            self.assertEqual(len(calls), 1 if slow_route == "/apply-template" else 2)

    def test_callback_failures_are_sanitized_and_never_trigger_generation(self):
        for exception, code in ((RuntimeError("PRIVATE_SERVER_PROMPT"), "context_preflight_request_failed"),
                                (TimeoutError("PRIVATE_SERVER_PROMPT"), "context_preflight_timeout")):
            def broken(*_): raise exception
            error = self.error(code, callback=broken)
            self.assertNotIn("PRIVATE_SERVER_PROMPT", str(error) + json.dumps(error.metadata))

    def test_callback_mutation_does_not_modify_generation_payload(self):
        original = copy.deepcopy(self.payload)
        def mutating(route, payload, timeout):
            if route == "/apply-template":
                payload["messages"][0]["content"] = "altered"
                return {"prompt": "text"}
            return {"tokens": [1]}
        self.admit(callback=mutating)
        self.assertEqual(self.payload, original)

    def test_large_reserved_sum_fails_without_integer_wraparound(self):
        payload = {**self.payload, "max_tokens": MAX_INTEGER}
        error = self.error("context_token_limit", payload=payload, token_limit=MAX_INTEGER, safety_margin=MAX_INTEGER)
        self.assertEqual(error.metadata["reserved_tokens"], MAX_INTEGER * 2 + 5)
        self.assertLess(error.metadata["remaining_tokens"], 0)

    def test_zero_safety_margin_is_explicit_and_count_still_required(self):
        self.assertTrue(self.admit(token_limit=105, safety_margin=0)["admitted"])
        self.error("context_token_limit", token_limit=104, safety_margin=0)


if __name__ == "__main__":
    unittest.main()
