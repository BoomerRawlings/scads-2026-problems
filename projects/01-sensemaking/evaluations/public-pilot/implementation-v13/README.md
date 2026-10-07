# v13 public catalog snapshot

Thirteen exact implementation, schema, dependency, runtime-manifest and importer
files are preserved here. [snapshot.json](snapshot.json) binds their hashes and
overlay destinations, the statement dataset, import manifest, fixed question,
[review protocol](../PROTOCOL.md) and [9B text profile](../runtime-profile-qwen35-9b-text-01.json).
This is a known, source-inspected development case; freezing does not establish
public analytic acceptance.

The opt-in catalog exposes bounded metadata pages for selective full-source
retrieval. Metadata cannot support citations or relationship proofs. Actual
complete cursor chains establish returned inventory, not full reading or
analytical completeness. Text-only local requests undergo template/tokenizer
preflight and post-generation usage checks, with byte limits and HTTP deadlines.
The existing whole-memory workspace is not a scalable storage implementation.
Legacy media behavior and v12 synthesis guidance remain unchanged.

Before freezing, 245 implementation tests passed, zero skips, in 77.415 seconds.
Five descriptive metadata labels changed afterward and received independent
review; executable behavior did not. The saved Riverwatch14 legacy synthesis
context reconstructs byte-for-byte. Tests do not measure model accuracy.

For reproduction, copy the project to a separate directory without environments,
runs or caches. Overlay each saved file at its `file_origins` destination.
Reconstruct `datasets/public-research/imported-statements/` from the unchanged
bundled raw capture using [the documented offline importer](../../../docs/public-statements.md).
Verify the dataset and import-manifest hashes before running. Install the pinned
dependencies and verified `candidate-9b` runtime using
[local runtime setup](../../../docs/local-runtime.md). Launch the recorded text
profile: no projector, no optional saved-prompt cache, one 16,384-token slot.
This snapshot contains neither a runtime nor model weights.

Load `question`, `target`, budgets and flags directly from `snapshot.json`; do
not send the reviewer-only protocol map to the model. From the project directory:

```python
import json, subprocess, sys
from pathlib import Path
frozen = json.loads(Path('evaluations/public-pilot/implementation-v13/snapshot.json').read_text())
subprocess.run([
    sys.executable, 'local_agent.py', frozen['target'],
    '--data-dir', 'datasets/public-research/imported-statements',
    '--question', frozen['question'],
    '--base-url', 'http://127.0.0.1:18571/v1', '--model', 'Qwen3.5-9B-Q3_K_M',
    '--max-steps', '40', '--timeout', '3600', '--request-timeout', '1200',
    '--report-thinking-budget', '1024', '--grounded-media', '--compact-synthesis',
    '--evidence-summary', '--retrieval-profile', 'catalog',
    '--context-token-limit', '16384', '--catalog-context-bytes', '131072',
    '--output-dir', 'runs/reproduced-public-nci-v13',
], check=True)
```

Use a fresh output directory. Planning uses disabled thinking, temperature 0 and
seed 0. Synthesis requests 1,024 thinking tokens within its 4,096-token output
cap, temperature 0.6 and seed 0. Private reasoning is not saved. Repeated settings
do not guarantee identical or correct output. Preserve failures and subject any
completed report to the frozen review protocol.
