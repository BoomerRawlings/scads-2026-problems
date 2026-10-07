# Riverwatch07 implementation snapshot

These six source/schema files match the run's recorded implementation hashes.
Requirements and the original runtime manifest are also preserved. This is an
inspection/reproduction snapshot, not the current implementation or an accepted
analytic result. [Hashes](snapshot.json) · [rejected run and review](../../../examples/local-riverwatch-rejected/REVIEW.md)

To reproduce, use a separate copy of the project, replace its matching root
source/schema files and requirements with these versions, and use this runtime
manifest in `docs/runtime-manifest.json`. Retain the original synthetic `data/`
whose fingerprints appear in the run metadata. Follow the recorded target,
question, limits and [launch profile](../runtime-profile-06.json). Local workloads
and nondeterministic numerical execution can still change timing/output.

Do not execute this directory as a standalone installation: it intentionally
omits dataset copies, downloaded models, environments and machine state.
