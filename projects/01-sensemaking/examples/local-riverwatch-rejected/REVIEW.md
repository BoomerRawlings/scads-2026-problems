# Riverwatch07: runtime accepted, analytic review rejected

**Do not present this report as a successful analysis.** The original model JSON,
trace, ledger and metadata are unchanged. Markdown links were rerendered for this
location. Separate AI review checked source text, hashes and actual frame pixels;
this is not independent human labeling or a held-out evaluation.

Qwen3-VL-2B-Instruct Q4_K_M used 14 successful MCP calls and 17 actions in
1,044.422 seconds: one rejected finish intent, one accepted intent, one synthesis.
It inspected the PNG and MP4 frames at actual source timestamps 0/15/29 seconds.
No report-shape rejection occurred. Runtime acceptance did not establish truth.

## Rejection reasons

- **Inverted uncertainty:** at `00:29`, the report says other institute activities
  “are not delayed.” The caption says their delay has **not been established**.
  Absence of evidence for delay does not prove absence of delay.
- **Incomplete dependency coverage:** never retrieved `memo-003`, `memo-004`,
  `tbl-005`, `tbl-006` or `img-note-002`. The full Northline supplier path,
  September 14/19 planned-arrival disagreement and absent inspection-tag media
  are missing. Keyword searches over reached nodes were not a source inventory.
- **Weak reconciliation:** two conflict entries repeat the same issue without
  both dated values. Findings repeat and promote delayed readiness despite the
  unresolved ready register. One finding does correctly preserve the disagreement.
- **Media attribution:** the 0/15-second caption meanings are supported, but
  coordinator roles come from the authored transcript, not visible speakers or
  processed audio. The sampled-video limitation is omitted. PNG pixels were read
  without an explicit image observation in the report.
- **Unhelpful follow-up:** proposes authenticating fictional events despite the
  stated synthetic provenance. Future work should test fixture coverage and
  qualified real data.

The four retrieved text-source hashes and both inspected media hashes match.
The report correctly acknowledges synthetic, non-independent sources. These
strengths do not cure the false assertion or incomplete investigation.

The trial motivates actual-result inventory/edge-proof coverage checks and a
stronger local model trial. Neither change retroactively validates this result.
Exact code: [v6 snapshot](../../evaluations/local-pilot/implementation-v6/snapshot.json).
Protocol: [source review](../../evaluations/local-pilot/REVIEW-PROTOCOL.md).
