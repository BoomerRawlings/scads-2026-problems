# VOPT discovery workflows

These workflows are provisional: the problem brief's detailed unclassified use-case mapping was not supplied. They support the stated metadata-only discovery and document-request objective.

| Workflow | Input | Required outcome |
| --- | --- | --- |
| Attribute coverage | Manuals with engine horsepower | Evidence-reviewed presence, document/model/revision and request reference; no inferred absence |
| Constrained discovery | Compressors with horsepower above 2 hp and weight below 500 kg | All approved bounds true for the same model/variant and compatible conditions; otherwise unknown/clarify |
| Exact identity | Model VG-959 QMC | Exact full identifier, including multiple words; sibling model specs cannot leak into the match |
| Ambiguous electrical query | Generators above 200 V | Clarify input/output voltage; do not silently choose a role |
| Insufficient metadata | Numeric filter against coverage-only release | Unsupported explanation; offer observed-attribute query refinement |
| Evidence conflict | Same model/revision has incompatible qualified values | Conflict surfaced; no arbitrary winner |
| Document request | Select discovered manuals | Export local versioned references, selected scopes and query; no automatic source fetch or message |
| Catalog revision | Approved new metadata snapshot | Atomic import; old snapshot recoverable only under latest policy |
| Withdrawal | Document or assertion revoked | Remove active and derived entries; prevent rollback restoring withdrawn information |
| Extraction correction | OCR or model association wrong | Show pixels/context, preserve raw candidate, append correction, invalidate stale views |

Direct specification answers, maintenance advice, semantic reasoning from unavailable source content, automated document delivery and classified-network deployment are outside this local implementation's claims.
