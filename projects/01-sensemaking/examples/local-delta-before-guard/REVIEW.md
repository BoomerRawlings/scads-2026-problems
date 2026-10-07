# Rejected development example

This is the unedited model report from the first completed free-local pilot.
It is **not an accepted answer**. The initial citation/shape guards accepted it,
demonstrating why those guards do not establish analytic correctness.

- Target `Delta` matches two entities. The model acknowledged ambiguity but
  arbitrarily explored `delta_team`; it should have requested clarification.
- It confused a text memo's missing media attachment with inadequate evidence.
  Text evidence does not require visual corroboration to support attributed claims.
- It called `read_media` on a memo after metadata reported no attached media.
- The final status should have been `needs_clarification`.

Model: Qwen3-VL-2B-Instruct Q4_K_M, llama.cpp b11457, temperature/seed 0.
Seven model actions, six MCP calls (one failed), 164.594 seconds after startup.
Weights and runtime were installed from the verified runtime manifest. The saved
alias alone does not independently prove the weights loaded by a remote server.

This development finding motivated an identity scope guard and stricter
clarification validation. Retesting the same fixture measures the repair;
it is not held-out evaluation. Report JSON and trace remain unchanged; Markdown
was rendered with corrected relative links after copying the saved artifacts.
