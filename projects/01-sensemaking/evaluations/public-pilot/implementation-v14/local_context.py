"""Opt-in, text-only context admission; no transport or model inference here.

Pinned llama.cpp b11457 uses the same chat parser for /apply-template and chat
completion. Pass the entire generation payload: response_format/schema, tools,
continuation settings and chat_template_kwargs can affect template inputs.
Then /tokenize uses parse_special=true, add_special=false, with_pieces=false.
Official source contract:
https://github.com/ggml-org/llama.cpp/blob/b11457/tools/server/server-context.cpp#L4927-L4985
https://github.com/ggml-org/llama.cpp/blob/b11457/tools/server/server-common.cpp#L1205-L1332
https://github.com/ggml-org/llama.cpp/blob/b11457/tools/server/README.md#post-tokenize-tokenize-a-given-text

The supplied request(route, payload, timeout) callback must use the SAME validated
loopback server as generation, root routes (not /v1/apply-template), no redirect or
proxy, and bounded raw HTTP responses. This module bounds decoded response JSON
again; a dict callback cannot attest to original response wire bytes. Request
wire counts use json.dumps(ensure_ascii=False) with default separators; callers
using another serialization must enforce its bound separately. No callback input
or response text, token ID list, source body or rendered prompt is returned/saved.

Admission is a conservative preflight, NOT verified exact model fit. The explicit
token_limit must describe the actual serving slot. Template/tokenizer/settings
drift, model routing and special-token behavior still require comparison against
actual generation usage. Callers must generate from the same unmodified payload;
no evidence is dropped, summarized or truncated to pass this check.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Callable

POLICY = "llama-b11457-text-context-admission-v1"
DEFAULT_REQUEST_BYTES = 24 * 1024 * 1024
DEFAULT_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_INTEGER = (1 << 31) - 1


class ContextAdmissionError(ValueError):
    """Safe failure code/message and allowlisted numeric/hash metadata only."""

    def __init__(self, code: str, message: str, metadata: dict | None = None):
        super().__init__(message)
        self.code = code
        self.metadata = dict(metadata or {})


def _json_bytes(value, compact=False):
    options = {"ensure_ascii": False, "allow_nan": False}
    if compact:
        options.update(sort_keys=True, separators=(",", ":"))
    return json.dumps(value, **options).encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def admit_text_context(generation_request: dict,
                       request: Callable[[str, dict, float], dict], *,
                       timeout: float, token_limit: int, safety_margin: int = 128,
                       max_request_bytes: int = DEFAULT_REQUEST_BYTES,
                       max_response_bytes: int = DEFAULT_RESPONSE_BYTES) -> dict:
    """Return sanitized admission metadata or raise ContextAdmissionError.

    Exactly two non-inference endpoint calls on success. Both share one deadline.
    max_tokens is the actual generation cap, including any thinking allowance.
    Missing/scalar/float/bool token counts are never estimated or accepted.
    """
    metadata = {"policy": POLICY, "admitted": False, "exact_model_fit_verified": False}

    def fail(code, message):
        raise ContextAdmissionError(code, message, metadata) from None

    for name, value, minimum in (("token_limit", token_limit, 1),
                                  ("safety_margin", safety_margin, 0),
                                  ("max_request_bytes", max_request_bytes, 1),
                                  ("max_response_bytes", max_response_bytes, 1)):
        if type(value) is not int or not minimum <= value <= MAX_INTEGER:
            fail("context_invalid_limits", "Context limits must be bounded integers; booleans are not limits.")
    try:
        valid_timeout = (not isinstance(timeout, bool) and isinstance(timeout, (int, float))
                         and math.isfinite(timeout) and timeout > 0)
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        fail("context_invalid_limits", "Context timeout must be a positive finite number.")
    deadline = time.monotonic() + timeout
    if not math.isfinite(deadline):
        fail("context_invalid_limits", "Context deadline is not finite.")
    metadata.update(token_limit=token_limit, safety_margin=safety_margin,
                    max_request_bytes=max_request_bytes, max_response_bytes=max_response_bytes,
                    timeout_seconds=timeout)
    if not callable(request):
        fail("context_invalid_request", "A bounded same-server request callback is required.")
    if not isinstance(generation_request, dict):
        fail("context_invalid_request", "Generation payload must be a JSON object.")
    max_tokens = generation_request.get("max_tokens")
    if type(max_tokens) is not int or not 1 <= max_tokens <= MAX_INTEGER:
        fail("context_invalid_request", "Generation max_tokens must be a positive bounded integer.")
    metadata["max_tokens"] = max_tokens
    messages = generation_request.get("messages")
    if not isinstance(messages, list) or not messages:
        fail("context_invalid_request", "A nonempty message list is required.")
    kwargs = generation_request.get("chat_template_kwargs", {})
    if not isinstance(kwargs, dict):
        fail("context_invalid_request", "chat_template_kwargs must be a JSON object.")
    if "enable_thinking" in kwargs and type(kwargs["enable_thinking"]) is not bool:
        fail("context_invalid_request", "enable_thinking must be a boolean when supplied.")
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("role"), str):
            fail("context_invalid_request", "Each message requires a string role and text content.")
        content = message.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            fail("context_unsupported_content", "Text-only admission cannot count non-text message content.")
        for block in content:
            if (not isinstance(block, dict) or set(block) != {"type", "text"}
                    or block["type"] != "text" or not isinstance(block["text"], str)):
                fail("context_unsupported_content", "Text-only admission cannot count media or unknown content blocks.")

    def serialized(value, compact=False):
        try:
            return _json_bytes(value, compact)
        except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError):
            fail("context_invalid_json", "Context payload must be finite, UTF-8 JSON data.")

    canonical = serialized(generation_request, compact=True)
    metadata.update(canonical_request_bytes=len(canonical), canonical_request_sha256=_digest(canonical))
    if len(canonical) > max_request_bytes:
        fail("context_request_bytes", "Canonical generation payload exceeds the byte limit.")
    wire = serialized(generation_request)
    metadata["generation_request_bytes"] = len(wire)
    if len(wire) > max_request_bytes:
        fail("context_request_bytes", "Generation request wire representation exceeds the byte limit.")
    # Isolate callback mutation; preserve all actual generation fields and order.
    template_payload = json.loads(wire)

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            fail("context_preflight_timeout", "Context admission exceeded its shared deadline.")
        return value

    def call(route, payload, label):
        outgoing = serialized(payload)
        metadata[label + "_request_bytes"] = len(outgoing)
        if len(outgoing) > max_request_bytes:
            fail("context_request_bytes", "Context endpoint request exceeds the byte limit.")
        budget = remaining()
        try:
            response = request(route, payload, budget)
        except Exception as error:
            if isinstance(error, TimeoutError) or getattr(error, "code", None) == "model_timeout":
                fail("context_preflight_timeout", "Local context endpoint timed out.")
            fail("context_preflight_request_failed", "Local context endpoint request failed.")
        remaining()
        if not isinstance(response, dict):
            fail("context_invalid_response", "Local context endpoint returned a non-object response.")
        raw = serialized(response, compact=True)
        metadata[label + "_response_canonical_bytes"] = len(raw)
        if len(raw) > max_response_bytes:
            fail("context_response_bytes", "Decoded context endpoint response exceeds the byte limit.")
        return response

    applied = call("/apply-template", template_payload, "template")
    if set(applied) != {"prompt"} or not isinstance(applied["prompt"], str) or not applied["prompt"]:
        fail("context_invalid_template", "Template endpoint must return one nonempty prompt string.")
    prompt_raw = applied["prompt"].encode("utf-8")
    metadata.update(rendered_prompt_bytes=len(prompt_raw), rendered_prompt_sha256=_digest(prompt_raw))
    tokenized = call("/tokenize", {"content": applied["prompt"], "parse_special": True,
                                  "add_special": False, "with_pieces": False}, "tokenize")
    tokens = tokenized.get("tokens")
    if (set(tokenized) != {"tokens"} or not isinstance(tokens, list) or not tokens
            or any(type(token) is not int or not 0 <= token <= MAX_INTEGER for token in tokens)):
        fail("context_invalid_tokens", "Token endpoint must return a nonempty bounded integer ID list.")
    count = len(tokens)
    if count > MAX_INTEGER:
        fail("context_invalid_tokens", "Token count exceeds the supported integer bound.")
    required = count + max_tokens + safety_margin
    metadata.update(prompt_tokens=count, reserved_tokens=required,
                    remaining_tokens=token_limit - required)
    remaining()
    if required > token_limit:
        fail("context_token_limit", "Prompt, generation allowance and safety margin exceed the token limit.")
    metadata["admitted"] = True
    return metadata
