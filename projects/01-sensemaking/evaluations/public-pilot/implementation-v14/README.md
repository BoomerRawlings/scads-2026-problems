# v14 public capacity experiment

This experiment preserves the v13 harness byte-for-byte. Twelve code, schema,
dependency and importer files match v13; the thirteenth saved file is the existing
pinned 4B runtime manifest. [snapshot.json](snapshot.json) records all hashes,
overlay destinations, the unchanged question/data/protocol and new budgets.

NCI01 reached 16,823 prompt tokens before its tenth decision. Together with the
512-token generation allowance and 128-token margin, this exceeded its 16,384-token
slot. Admission refused the request; no evidence was truncated and no report
was produced. See [the original failure review](../public-nci-01/REVIEW.md).

The [new text profile](../runtime-profile-qwen35-4b-text-48k-01.json) uses
Qwen3.5-4B Q4_K_M, no projector, a 49,152-token serving slot, a 262,144-byte
serialized request ceiling, 60 actions, 7,200 seconds overall and 1,200 seconds
per request. Report generation retains its 1,024-token thinking allowance within
4,096 total tokens. Model, quantization and budgets change together; this is not
a controlled causal comparison, a quality pass or a scalable-storage result.

The [review protocol](../PROTOCOL.md) and source-inspected question remain fixed.
Do not supply the reviewer source map or previous outputs to the model. The
source capture/import and all evidence semantics remain unchanged. Prior failures
stay preserved. Other than the runtime manifest, this is a profile experiment,
not a new harness implementation or an independently rerun full test suite.

Reproduce from a separate project copy, overlaying the saved `file_origins` files.
Reconstruct the statement dataset from its bundled raw capture as documented in
[public statements](../../../docs/public-statements.md), and verify the snapshot
bindings. Use the verified `candidate-4b` runtime from
[runtime setup](../../../docs/local-runtime.md). Its server flags match the recorded
9B text launch except the model/alias and `--ctx-size 49152`.

From the project directory and its environment:

```python
import json, subprocess, sys
from pathlib import Path
s = json.loads(Path('evaluations/public-pilot/implementation-v14/snapshot.json').read_text())
b = s['budgets']
subprocess.run([
    sys.executable, 'local_agent.py', s['target'],
    '--data-dir', 'datasets/public-research/imported-statements',
    '--question', s['question'], '--base-url', 'http://127.0.0.1:18571/v1',
    '--model', 'Qwen3.5-4B-Q4_K_M', '--max-steps', str(b['max_steps']),
    '--timeout', str(b['timeout_seconds']),
    '--request-timeout', str(b['request_timeout_seconds']),
    '--report-thinking-budget', str(b['report_thinking_budget']),
    '--grounded-media', '--compact-synthesis', '--evidence-summary',
    '--retrieval-profile', 'catalog',
    '--context-token-limit', str(b['context_token_limit']),
    '--catalog-context-bytes', str(b['catalog_context_bytes']),
    '--output-dir', 'runs/reproduced-public-nci-v14',
], check=True)
```

Use a fresh output directory. The snapshot contains no model weights or runtime.
Repeated settings do not guarantee identical outputs or correct analysis.
