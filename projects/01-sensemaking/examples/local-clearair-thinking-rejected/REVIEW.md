# ClearAir04: accepted by software, rejected by source review

This is an independent AI review of a known, authored development fixture—not
human gold labeling, a held-out evaluation, or evidence of general accuracy.
Review followed the [local protocol](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).

The original [report JSON](report.json), [trace](tool-trace.json),
[ledger](evidence-ledger.json), and [metadata](run-metadata.json) are copied
byte-for-byte from `runs/local-clearair-04/`. Only Markdown source links were
rerendered for this directory. The model's analytic claims remain unchanged.

## Why rejected

- The summary changes the transcript's “not evidence” of ClearAir delay into
  “unrelated to delay.” Lack of evidence does not establish causal unrelatedness.
- Finding 2 calls the agreement “verified by synthetic transcript text.” These
  authored sources support a consistency check, not independent verification.
  The report identifies the transcript as synthetic but omits the register's
  shared synthetic provenance.
- The follow-up seeks “independent record entries” to verify an invented case.
  Appropriate next work is fixture consistency testing or applying the workflow
  to a separately qualified real organization—not externally verifying ClearAir.

## What passed

- Both sources report readiness as `ready` on 2026-09-05. The finding about
  Northline correctly says no dependency is *recorded*. Finding 3 retains the
  source's “not evidence of delay” wording.
- No invented teams or coordination roles. Empty conflict and media-observation
  arrays are correct. Narrative length: 107 whitespace-separated words, excluding
  title, IDs, and field labels; within the requested 200-word limit.
- Five successful MCP calls: identity search, rooted traversal, unfiltered scoped
  inventory, and both source reads. ClearAir's returned scope has one node and
  no outgoing edges. Both linked records were inventoried and retrieved.
- Source locators, dates, text hashes, and dataset fingerprint match the corpus.
  There was no `inspect_media` or `read_media` call and no attached raw video.
  This run does not demonstrate media inspection.

The run used the [v7 snapshot](../../evaluations/local-pilot/implementation-v7/README.md)
and Qwen3.5-4B candidate profile, with a requested 1,024-token report thinking
budget. It completed seven actions in 287.781 seconds with no software report
rejections. Private reasoning was not saved. Runtime acceptance checks provenance
and workflow conditions; it does not establish factual interpretation.
