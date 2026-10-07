# Local model adapter

`graphrag_discovery/local_models.py` calls a locally running llama.cpp server using
Python's standard library. It requires no paid provider, account, API key, SDK, or
network service. Model installation and server lifecycle are separate responsibilities.
There is no remote fallback and no fabricated extraction after an inference failure.

## Server and model configuration

Use a dedicated Project 5 server/port; do not reuse another project's active inference
slot. Existing verified binaries/model files can be read without copying or modifying
them. Start an installed llama.cpp executable with an explicit alias, local GGUF file,
loopback host, and an appropriate context size. For example:

```text
llama-server --model /path/to/instruct.gguf --alias p5-extractor --host 127.0.0.1 --port 18575 --ctx-size 8192 --jinja --offline
llama-server --model /path/to/embedding.gguf --alias p5-embedding --host 127.0.0.1 --port 18576 --embedding --offline
```

Use a suitable embedding model and its supported pooling configuration. The current
[official server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
documents `/health`, `/v1/models`, `/v1/chat/completions`, and `/v1/embeddings`.
Chat responses support JSON schema constraints. The embeddings endpoint requires
pooling other than `none`; `--embedding` selects the dedicated embedding use case.
These protocol details were checked against the official documentation during this build.

The adapter accepts only HTTP loopback IPs or `localhost`, canonicalized to `127.0.0.1`.
An optional trailing `/v1` is accepted. Credentials, custom paths, queries, fragments,
remote addresses, proxies, and redirects are rejected or disabled. No authorization
header is sent. The client never downloads models, starts servers, or changes server
configuration. Optional model revision and SHA-256 are declared provenance, not proof
that a server alias resolves to those weights; verify the local files separately.
Server pooling/context are not attested by the client profile. Preserve those launch
settings with evaluations and rebuild indexes when the model or pooling changes; an
unchanged alias alone cannot establish vector compatibility.

## Python interface

```python
from graphrag_discovery.local_models import LocalModelClient

extractor = LocalModelClient("http://127.0.0.1:18575", "p5-extractor")
extractor.preflight()  # Health and exact advertised alias; no inference.
result = extractor.extract(validated_upsert_record, max_assertions=32)
assertions, provenance = result["assertions"], result["metadata"]

embedder = LocalModelClient("http://127.0.0.1:18576", "p5-embedding")
embedded = embedder.embed(["One relationship description", "Another description"])
vectors, provenance = embedded["vectors"], embedded["metadata"]
restored = LocalModelClient.from_profile(embedder.profile)
assert restored.profile == embedder.profile
```

`profile` is stable, serializable configuration; request counters are separate in
`stats`. It includes model/endpoint, declared revision/digest, prompt version/hash,
sampling, limits, and identity policy. `from_profile` rejects unknown or changed
settings, including a different prompt implementation. Extraction cache keys must also
include the source/date/context inputs and per-call `max_assertions`.

Every successful inference returns request/response fingerprints, elapsed time,
byte counts, model-call count, and available server token counters. Missing counters
remain null. Raw prompts, responses, source text, and server error bodies are not logged
or returned as diagnostic metadata. Assertions themselves retain cited source text.

## Grounding and temporal limits

The model proposes only an exact quote, endpoint labels, modality, and temporal fields.
The adapter requires a unique contiguous quote and unique literal endpoint mentions
inside that quote, then calculates Unicode offsets itself. It generates deterministic
source/mention-scoped IDs. Model-supplied IDs, offsets, corpus, supersession, tools, or
extra fields cause rejection. Separate mentions and documents are not automatically
merged; cross-document entity resolution remains a separate, unimplemented capability.

Successful proposals pass the shared assertion contract with `method=local-model-v1`.
Preparation metadata remains separate from assertions, and publication is the engine's
responsibility. One invalid proposal rejects the whole response; no partial batch is
silently accepted. An empty assertion array is explicit model abstention.

Plans and negations retain their proposed modality. Unknown bounds remain null with
`unknown` status. A known bound requires the exact timezone-aware ISO timestamp in
the quote. This version rejects inferred relative/calendar dates and invented open
endpoints. Citation, shape, and date checks do not prove that the model understood the
relationship, selected the right modality, or found every relevant statement. Independent
semantic evaluation is still necessary. Source instructions remain data; the adapter
has no tool execution path.

Embedding responses must cover every input exactly once and return finite, nonzero,
equal-dimensional vectors. Response order is restored using indices. Vectors are kept
as returned; normalization is recorded as server-provided. Dimension/model compatibility
across batches and indexes belongs to the vector index layer.

## Bounds and failure behavior

| Limit | Default | Maximum configurable |
| --- | --- | --- |
| Request deadline, including slow response reads | 120 seconds | 600 seconds |
| Extraction text / aggregate embedding batch | 12,000 Unicode characters | 250,000 |
| Generated output | 2,048 tokens | 16,384 |
| HTTP response | 2 MiB | 8 MiB |
| Embedding input count | 32 | 128 |
| Extraction assertion count | 32 | 128 per call |
| Serialized HTTP request | 1 MiB | Fixed |

No input is silently truncated. Token-context overflow can occur below the character
limit and remains a server error. Generation ending with `finish_reason=length` is
rejected. Errors use `DomainError` codes prefixed `local_model_`, including `config`,
`input_limit`, `http`, `transport`, `timeout`, `response_limit`, `truncated`, `format`,
and `grounding`. A disconnected/timed-out client does not prove server-side generation
stopped; the adapter does not issue administrative cancellation or retries.

Run `python -m unittest tests.test_local_models -v` for scripted HTTP regressions.
They cover endpoint/transport policy, deadlines, limits, malformed/truncated output,
grounding, injection-shaped data, temporal conservatism, profiles, and vectors. They
establish client behavior; only a separately recorded live-model run demonstrates
actual model inference, and neither establishes retrieval quality at scale.

The [live validation record](local-model-validation.md) preserves a real local extraction,
an initial unsupported-embedding failure, and the subsequent vector/index/query/export
smoke test after a deliberate runtime configuration change.
