# Vulkan 9B bounded probe review

Outcome: **shared-host resource gate stopped startup; compatibility unqualified**.
This is a separate AI review of operator-recorded configuration, numeric memory samples
and bounded startup evidence, not a model inference or performance evaluation.

- [Original result](context-probe-vulkan-9b-8k-01.json): `low_physical_memory`,
  22.734 seconds total including verification/startup; owned child exited, no
  cleanup errors. Context admission and response metadata are null.
- [Original profile](runtime-profile-vulkan-9b-8k-01.json): pinned b11457 ARM64
  Vulkan and Qwen3.5-9B-Q3_K_M; one requested GPU layer, 8,192 context,
  one slot, four CPU threads, batch 64/microbatch 16, Q8 K/V, flash attention,
  mmap/no repack, no projector/warmup/prompt RAM cache. Requested configuration
  does not attest successful allocation or layer offload.
- [Prepared request](context-probe-vulkan-9b-8k-01.request.json): exact earlier
  neutral JSON request, 32-token cap, thinking disabled. Never sent: startup
  did not reach the owned-server listening gate. No model output exists.

The first physical-memory sample, before child launch, was 2,903,584,768 free
bytes out of 16,757,260,288. Of eleven total samples, the final two reported
493,780,992 and 488,865,792 free bytes, below the 536,870,912-byte guard. The
maximum observed child working set was 2,955,362,304 bytes; its maximum reported
peak was 2,962,554,880. The separate 7 GiB working-set guard was not reached.
These are shared-host measurements: other workloads, mapped pages, driver/GPU
allocations and operating-system reclamation prevent attributing all free-memory
change to this child. Process working set is not total GPU memory consumption.

The private 684-byte startup log contains no listening marker, completed layer
offload count or model-buffer allocation summary. Its absence does not diagnose
backend failure. Logs, process identity and machine paths remain private. No
retry, model inference, throughput or minimum-memory claim follows from this run.
Prior device enumeration established only that the driver exposed Vulkan0.

Preservation and binding checks:

- All three JSON records copied byte-for-byte into this directory; originals
  unchanged. Their relative profile reference resolves; the manifest path in
  the profile is project-relative.
- Result SHA256: `8dba0acaf59ba1f4cc22b492189e6a715230e0317184ae296435be835a6361c3`.
- Profile SHA256: `db2004ecde235034f847c7d5d60c1f4ae91edfcf402f53008caa5b80890ecfc3`.
- Request-file SHA256: `b4aab8c68ebdb00733d45dff7c4f1e64c30f97238c96b213689a1bbe5eb7c082`.
- Canonical request SHA256: `4d2bf5bcf4e58e2200d1c3adf2697b4884bd27fac05a4d35f8f47b8b26c36a08`.
- Profile records helper SHA256 `1af7c144711dba28ae5f0f98dba288f8c50fab09c6e1cc82a29a463c3e42cd71`.
  All eleven recorded source-file hashes matched at this post-run review.
  The manifest matched its recorded digest; the supervisor also recorded its
  end-of-run manifest check as unchanged. The early stop bypassed its successful
  inference path's source recheck; this review supplies the later disk comparison.
- The helper remains ignored and excluded from the source archive. Its recorded
  hash does not mean the helper is archived or that reproduction is qualified;
  the published profile, pinned assets, prepared request and result document the
  operator's attempt.
- Public records contain no absolute machine paths or reasoning text. The
  prepared expected answer is not an observed model answer.

The bounded stop and owned-child cleanup worked. A future model/backend or
larger-context qualification still requires a separately recorded run with
adequate measured headroom; this result cannot select its required RAM or speed.
