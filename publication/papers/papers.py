"""Editable, evidence-linked prose for the five SCADS research case studies.

All numeric claims come from the listed repository sources. Publication date is
October 7, 2026; experiment dates are stated only when needed and documented.
"""

PAPERS = [
{
 'number':'01','slug':'01-sensemaking','short':'ORGANIZATIONAL SENSEMAKING',
 'title':'Evidence across an organization',
 'subtitle':'An auditable agent workflow for organizational sensemaking',
 'refs':[
   ('Project overview and implemented system','README.md'),
   ('Riverwatch14 independent AI source review','examples/local-riverwatch-guidance-accepted/REVIEW.md'),
   ('Original Riverwatch14 report','examples/local-riverwatch-guidance-accepted/report.md'),
   ('Original run metadata','examples/local-riverwatch-guidance-accepted/run-metadata.json'),
   ('Frozen v12 reproduction instructions','evaluations/local-pilot/implementation-v12/README.md'),
   ('Source-package reproduction','docs/package-reproduction.md'),
   ('Evidence catalog contract','docs/evidence-catalog.md'),
 ],
 'pages':[
 {'title':'','blocks':[
   ('h','Abstract'),
   ('p','An organization is a collection of related teams, projects, records and external dependencies. A useful assessment must follow those relationships without turning every connected fact into a claim about the entire organization. This implementation equips an agent with six evidence tools, a directed graph, structured retrieval and direct media inspection. The agent chooses its investigative path and produces cited findings, qualifications and unresolved conflicts. [1]'),
   ('p','A recorded local-model investigation of the fictional Riverwatch project retrieved nine sources through 15 MCP calls and inspected an image plus sampled video frames. A separate AI source review accepted the bounded development case. The case demonstrates traceable tool use and careful treatment of competing claims; it is neither independent human validation nor a statistical estimate of reliability. [2-4]'.replace('[2-4]','[2] [3] [4]')),
   ('h','Problem and design objective'),
   ('p','The SCADS task concerns sensemaking for nonatomic entities: entities whose properties depend on connected parts. Evidence is distributed across representations, names can be ambiguous, and dates can disagree. The design objective is an inspectable path from an analyst question to source-supported conclusions, with the subject and evidential scope preserved at every step. [1]'),
   ('h','Implemented contribution'),
   ('p','The working contribution combines identity resolution, bounded relationship traversal, source retrieval, multimodal evidence access and a recorded synthesis workflow. A local llama.cpp model supplies the free execution path; an optional Codex harness uses the same MCP interface. A static case explorer exposes saved reports, sources and tool sequences for inspection without running inference. [1]'),
   ('note','Evidence class: authored synthetic investigation, recorded local inference, separate AI source review and deterministic software checks. The paper reports the implemented method and its observed behavior.'),
 ]},
 {'title':'1. Method and architecture','blocks':[
   ('p','The architecture separates decisions made by the model from evidence supplied by the host. The model selects tools and writes findings. Retrieval returns identified records and graph proofs; declared host fields provide the overview and run limitations. This distinction lets a reader inspect which statements were generated and which were assembled from verified run facts. [1] [2]'),
   ('table',['Stage','Operation','Preserved evidence'],[
      ['Resolve','entity_search','Canonical IDs and ambiguous alternatives'],
      ['Connect','traverse_relationships','Typed directed paths, depth and supporting sources'],
      ['Read','search_evidence + read_evidence','Full records, dates and locators'],
      ['Inspect','inspect_media + read_media','Availability, original pixels and decoded frame times'],
      ['Synthesize','Recorded agent run','Cited findings, conflicts, qualifications and trace'],
   ],[65,171,252]),
   ('p','Structured records are queried through SQLite; source text and supplied assertion triples are indexed locally. The graph is a directed JSON edge-list representation. Relationship expansion has a declared depth, and every relevant edge keeps its supporting source IDs. A dependency edge is distinct from organizational containment or managerial control. [1] [12]'),
   ('h','Retrieve before citing'),
   ('p','The bounded catalog exposes metadata pages for selective discovery. Discovering an evidence ID is not equivalent to reading the source. Inventory coverage and fully retrieved, citable evidence therefore have separate records. This reduces the chance that an agent cites a promising title as though it had inspected the underlying statement. [7]'),
   ('h','Reconcile rather than overwrite'),
   ('p','Competing assertions retain subject, date, predicate, value and provenance. A more recent record can suggest an update, but recency alone does not prove that an earlier assertion was corrected. Reports preserve unresolved differences, distinguish plans from observed events and label inferences. Repeated fixture content across media is shared-origin evidence, not independent corroboration. [1] [2]'),
   ('note','Figure 1. The table follows the implemented investigative sequence. It is a method diagram, not a claim that every run visits all stages or that the model follows a fixed script.'),
 ]},
 {'title':'2. Worked case: Riverwatch','blocks':[
   ('p','The fictional Cedar Basin Research Institute contains divisions, teams and projects. Riverwatch depends on the Silt Sensor Batch supplied by Northline Instruments. A register records readiness, later material records delay, and supplier records contain different expected-arrival dates. The task is to explain readiness and dependencies while keeping the conclusion scoped to Riverwatch. [1] [2]'),
   ('table',['Evidence pattern','Supported interpretation'],[
      ['September 3 ready register; September 5 delayed material','Retain the dated readiness disagreement; do not declare current truth from chronology alone.'],
      ['Riverwatch  ->  sensor batch  ->  Northline','Preserve the dependency and supply relations; the path does not establish organizational control.'],
      ['Expected arrival September 14; later September 19','These are planning claims. Neither establishes shipment or receipt.'],
      ['Pending acceptance and required calibration','Describe release conditions without asserting an exclusive cause or proving the sensors defect-free.'],
      ['PNG and video caption boards','Inspect actual pixels, while retaining their authored synthetic origin.'],
   ],[190,298]),
   ('p','The accepted report contains four findings and two conflicts. Its review checked the source IDs, values, dated disagreements, supplier path and uncertainty wording. Original report bytes were preserved; a cosmetic color description and imprecise shipping terminology remain disclosed in the review. The analysis still distinguished expected arrival from delivery. [2] [3]'),
   ('h','Media and absence'),
   ('p','The run inspected the supplied PNG and decoded video frames returned at 0, 15 and 29 seconds. Those are caption fixtures without audio. An inspection-tag annotation had no declared attachment; the tool reported unavailable pixels. Treating that absence explicitly is part of the result, rather than replacing it with a model-generated visual description. [2]'),
   ('note','The unrelated arts event mentioning Riverwatch was excluded. The final report did not propagate project-level concern to an institute-wide shutdown or infer supplier misconduct. [2]'),
 ]},
 {'title':'3. Recorded evidence and interpretation','blocks':[
   ('table',['Measure','Observed result','Interpretation'],[
      ['MCP calls / sources','15 / 9','One known synthetic investigation'],
      ['Agent actions','21','Includes finish checks, observations and synthesis'],
      ['Elapsed time','2,538.563 seconds','Shared CPU host; not an isolated speed benchmark'],
      ['Findings / conflicts','4 / 2','Counts do not establish factual reliability'],
      ['Separate source review','Accepted with caveats','AI review; no human-gold or held-out estimate'],
      ['Implementation checks','268 tests passed','Software behavior, separate from analytic acceptance'],
   ],[131,130,227]),
   ('p','Run counts, timing and review scope are preserved in the original metadata and review. The latest overview records the implementation test total separately. The local case used frozen implementation v12 and a pinned Qwen3.5-9B Q3_K_M configuration; later implementation checks do not retroactively change that execution. [1] [2] [4] [5]'),
   ('h','What the evidence supports'),
   ('p','The trace establishes that tools were actually called and that their returned records supported an inspectable investigation. The source review establishes that this particular report preserves the crucial distinctions in the authored case: unresolved readiness, a full supplier path, planned dates and nonexclusive explanations. Mechanical citation validation alone would not establish those semantic properties. [2]'),
   ('h','Scope of inference'),
   ('p','The corpus has ten entities, 16 authored evidence records and seven retrieval regression cases. Its image and video repeat authored information. This makes it useful for controlled behavioral inspection while restricting any inference about natural scenes, audio, source independence or organizational truth. The development case is known and tuned; its acceptance cannot estimate general performance on unseen organizations. [1] [2]'),
   ('p','The most useful result is methodological: uncertainty can remain attached to a claim even when the agent produces a concise answer. A readable answer and a detailed audit trail serve different purposes, and the implementation retains both. This interpretation follows the demonstrated case rather than claiming measured analyst-time savings.'),
 ]},
 {'title':'4. Reproducibility and sources','blocks':[
   ('p','Start at the project directory in the public source repository. The README provides dependencies, local-model setup and the static case explorer. To inspect the exact analytic result, begin with the original report, trace, ledger and run metadata; use the frozen v12 instructions when reproducing the accepted model configuration. [1] [2] [5]'),
   ('code','python sensemaking.py entities\npython sensemaking.py investigate riverwatch --max-hops 2\npython sensemaking.py evaluate\npython scripts/build_showcase.py'),
   ('p','The deterministic investigate command creates an evidence packet; it is not the end-to-end agent analysis. Media inspection requires the documented ffmpeg/ffprobe tools. The local inference path requires separately installed model assets. Source-package reproduction checks bind file hashes and viewer contents without treating a same-host extraction as independent model validation. [1] [6]'),
   ('h','Evidence-linked references'),('refs',),
   ('note','Citation links point to the nested project source. The publication evidence manifest records hashes of the source files used for this paper; editable prose and the PDF builder accompany the publication.'),
 ]},
 ]
},
{'number': '02',
 'slug': '02-311-analytics',
 'short': 'NYC 311 ANALYTICS',
 'title': 'Reproducible agentic analytics for civic records',
 'subtitle': 'Verified million-record backend, failed local-agent evaluation',
 'local_revision': False,
 'evidence_scope': {'kind': 'actual_empirical_backend_qualification_and_negative_agent_evaluation',
                    'version': '0.7.0',
                    'real_core_runs': [{'run': 37705537519,
                                        'commit': '40a52917373bc54a0685b3b8ae35d261967c504f',
                                        'index_uuid': 'JVlj8cmQQWmf-7R8ESy3IA',
                                        'review_sha256': 'ed6d24e55253ae1044ce11b70c0dfaa6abcd37b1d3cf7ef7635bd685e199556a'},
                                       {'run': 38004540380,
                                        'commit': '78bae7eac0e33d28deb0cb404295f6f900a85db7',
                                        'index_uuid': '7FQfb9nTR2S2JB0E7tIsmQ',
                                        'review_sha256': '49d6c24af71db65a54662fa68b9176df23a4558b54cb6401b3a72a1c5c101c21'},
                                       {'run': 38025638157,
                                        'commit': '03fd0c094f99396f9af1106823811c3a5c5d1c55',
                                        'index_uuid': '_U8LIYhTRiSH69BdO3yTBw',
                                        'review_sha256': '22de2939dd977b9eb5ff4fad670e248f5194b8fe6c87c9abd81e6b88d5f44c68'},
                                       {'run': 38027551047,
                                        'commit': '6c39592ab00c2271203141ede36a25c98104e6da',
                                        'index_uuid': 'WiMgFvI_Sp2pbTgsL05Zhw',
                                        'review_sha256': 'c735eebbb972346bd38d73891a1c432c9a8240a48c926af99c263e4eaec3f9ec'},
                                       {'run': 38028955870,
                                        'commit': '868168ef480bd0574bc2440fa8a3f0d4aea5c62f',
                                        'index_uuid': '2R2S_pEhRtqPpjj2dM8ZsQ',
                                        'review_sha256': '5e2a4f59e4a4fab3f63595428dfb5f2081a8b2516b6d57f60feba3e2dd059ebc'},
                                       {'run': 38029812736,
                                        'commit': '663a5b16fa8ddeec08970bc5cf71f0eb2e71582e',
                                        'index_uuid': 'YX0M5BTATcGCaHqCfJXxfQ',
                                        'review_sha256': 'f39228d178e27bfd7470bfbc39ba1fe41d8f9c869b59a8ae4626b77dca2904d4'},
                                       {'run': 38030378224,
                                        'commit': '8c692cb13565a62a18782302eb1d4c82ca26c8a1',
                                        'index_uuid': 'EPAp0NR1SSW4bMFNLedg0g',
                                        'review_sha256': 'c6d9f21d1c57823d45a3d65d777517d5d3e0bcc06ff5730661f8e3c3afce435e'},
                                       {'run': 38031560273,
                                        'commit': '2ab96473fd927d5a5bae4bc48e2c50e372150ab4',
                                        'index_uuid': 'QDCkdPdnQLK_QEB5bzFUvQ',
                                        'review_sha256': '975c2315c7f408ec0c86cb2d3735da37cd317b33d06c609dfabf0da928f1f3ee'},
                                       {'run': 38083900641,
                                        'commit': 'b20a06e166e65f71d6aaf4cc1a0c1220c55853c5',
                                        'index_uuid': 'PQndJQDUQb2LV_upGfu0pQ',
                                        'review_sha256': '778c76a818bab6ce0f0c0affc986a1aaff7ec01c83a505d137c3504f0c66f0bd'}],
                    'performance_table_run': 38031560273,
                    'software_regression_current': 'examples/evidence/test-report-v0.7-matrix.json',
                    'software_regression_final': 'examples/evidence/test-report-v0.7-matrix.json',
                    'offline_bundle_revision': 'r4',
                    'model_development_run': 38028703734,
                    'model_development_commit': 'ffbbd5811c2b6ca949417b926dd56e3807e1e34d',
                    'zero_trial_startup_campaign': 38029812736,
                    'prospective_matrix_protocol_sha256': '9194c713896130a598c160d3ffe5b541b21ac40f467d5454c3cf6f2e9a33c8d6',
                    'scope': 'Nine archived pre-study cores reconcile 2,133,268 captured requests; the ninth '
                             'passes all three Maps checks. Four sixth-run exports pass independent '
                             'raw-to-nine-column reconstruction for one 9,728-row cohort. Three additional '
                             'matrix core preflights pass. All 120 model trials execute and receive semantic '
                             'review; one passes both automatic and semantic checks (0.8333%), so agent '
                             'quality and overall release fail. Eight earlier core failures and three '
                             'zero-question startup failures remain retained. Qualification is bounded to the '
                             'observed corpus, cohorts, workloads and runtime tested.',
                    'final_maps_run': 38083900641,
                    'csv_cell_audit': {'path': 'examples/evidence/csv-cell-audit-38029812736.json',
                                       'sha256': 'd644bfe6bc1250bd15046242255264ea4bf6071f222c737601e382036f848c53',
                                       'original_export_run': 38029812736,
                                       'logical_rows': 9728,
                                       'logical_cells': 87552,
                                       'artifact_cells': 350208,
                                       'passed': True},
                    'software_regression_platform': {'os': 'Windows',
                                                     'tests': 576,
                                                     'passed': 575,
                                                     'skipped': 1,
                                                     'seconds': 66.672,
                                                     'skipped_test': 'test_jobs.JobLeaseTests.test_symlink_lock_is_refused',
                                                     'reason': 'Windows unprivileged symbolic-link creation '
                                                               'denied; not the Linux CI skip'},
                    'maps_ci_regression': {'run': 38083900641,
                                           'commit': 'b20a06e166e65f71d6aaf4cc1a0c1220c55853c5',
                                           'os': 'Linux',
                                           'tests': 559,
                                           'passed': 558,
                                           'skipped': 1,
                                           'seconds': 7.174,
                                           'source': 'examples/evidence/real-core-38083900641/maps-independent-review.json',
                                           'skip_identity': 'Not named in retained quiet CI summary; do not '
                                                            'relabel it as Windows symlink denial'},
                    'matrix_core_preflight': {'run': 38084773557,
                                              'actual_core_receipts': [{'replica': 1,
                                                                        'path': 'runs/agent-campaign-38084773557/corpus-r1/real-v1/acceptance.json',
                                                                        'sha256': 'f250d4f1687bd20a48f65a4ce56ae3a86a416d3ea8430d8b6c2b56c334ddd604',
                                                                        'passed': True,
                                                                        'index_uuid': '0PWTIqhOTJuVbFYt8kC_lg',
                                                                        'overall_release_verified': False},
                                                                       {'replica': 2,
                                                                        'path': 'runs/agent-campaign-38084773557/corpus-r2/real-v1/acceptance.json',
                                                                        'sha256': '9215d1873b1f5734f59491c34adeed88e7f07469bf0008a8182a0357e228aa07',
                                                                        'passed': True,
                                                                        'index_uuid': 'q5_UOUK2Qry44_FXGkueAQ',
                                                                        'overall_release_verified': False},
                                                                       {'replica': 3,
                                                                        'path': 'runs/agent-campaign-38084773557/corpus-r3/real-v1/acceptance.json',
                                                                        'sha256': '62aecf4bc0b3354e48cbf99856cb58549ebbd925259fc6d0b43b0375211e1ef5',
                                                                        'passed': True,
                                                                        'index_uuid': 'bt3nXTUPT6uH-HQOwbDoEg',
                                                                        'overall_release_verified': False}],
                                              'excluded_from_nine_pre_study_core_count': True,
                                              'all_three_passed': True},
                    'prepared_date_utc': '2026-10-11',
                    'agent_matrix': {'run': 38084773557,
                                     'commit': 'd3be88e72cf5e7920f2861eaa7c21f6dd26abdb3',
                                     'execution_complete': True,
                                     'required_trials': 120,
                                     'executed_trials': 120,
                                     'reviewed_trials': 120,
                                     'automatic_passes': 1,
                                     'end_to_end_passes': 1,
                                     'pass_rate': 0.008333333333333333,
                                     'passing_trial': 'Q38-r1',
                                     'semantic_only_passes': 2,
                                     'semantic_only_passing_trials': ['Q38-r1', 'Q38-r2'],
                                     'semantic_unsupported_claim_or_false_completion_trials': 32,
                                     'automatic_numeric_evidence_hard_failure_trials': 8,
                                     'chained_trial_passes': 0,
                                     'chained_trials': 9,
                                     'delivered_finals': 56,
                                     'timeouts': 52,
                                     'repeated_invalid_tool_call_failures': 11,
                                     'invalid_final_answer_failures': 1,
                                     'trial_elapsed_seconds': {'samples': 120,
                                                               'minimum': 14.539215,
                                                               'median': 126.15948900000001,
                                                               'maximum': 160.006379,
                                                               'sum': 14018.248296},
                                     'latency_scope': 'Whole trial including model/tool/adapter and failed '
                                                      'attempts; excludes startup/download/build; not '
                                                      'generation-only or successful-answer latency.',
                                     'warmup_by_replica': [{'repetition': 1, 'seconds': 295.781533},
                                                           {'repetition': 2, 'seconds': 256.060538},
                                                           {'repetition': 3, 'seconds': 289.675959}],
                                     'final_report': {'path': 'examples/evidence/agent-campaign-38084773557/final-review.json',
                                                      'sha256': '81cd4cec6118c6a4b67519ca919a470ce3cd7ac0b38c08d06bd06fcf88a3c8e7'},
                                     'diagnostics': {'path': 'examples/evidence/agent-campaign-38084773557/actual-diagnostics.json',
                                                     'sha256': '217365f6d8a41366a6745cc11fd5978d6f8546a7eb6a3ee7ad6c5fead61c8011'},
                                     'archive_diagnostics_review_sha256': 'aa19af3e57879df4de839a829e101c0b9da5372dcd827c96214636a7e5d6270a',
                                     'agent_quality_gate_passed': False,
                                     'overall_release_verified': False,
                                     'semantic_review_scope': 'Three AI infrastructure contributors reviewed a '
                                                              'separate answering-model session; exact trial '
                                                              'hashes; initial cards hid automatic grades. Not '
                                                              'independent human gold or blinded model '
                                                              'selection.'}},
 'refs': [('Implemented service and version', 'IMPLEMENTATION.md'),
          ('Analytical and artifact contract', 'docs/tool-contract.md'),
          ('Actual capture: local streaming verification',
           'examples/evidence/captured-local-verification.json'),
          ('Ninth real-corpus execution: independent Maps and core review',
           'examples/evidence/real-core-38083900641/independent-review.json'),
          ('Eighth Elasticsearch workload: actual measurements',
           'examples/evidence/real-core-38031560273/measurements.json'),
          ('Final v0.7 software regression: 575 passed, one Windows skip',
           'examples/evidence/test-report-v0.7-matrix.json'),
          ('Verified offline distributions and transfer limits', 'docs/distribution.md'),
          ('Actual local-model development quality failure',
           'examples/evidence/model-smoke-38028703734/independent-review.json')],
 'pages': [{'title': '',
            'blocks': [('h', 'Abstract'),
                       ('p',
                        'Natural-language civic questions hide choices about time boundaries, complaint '
                        'families, geography and missing values. This implementation places those choices in a '
                        'strict analytical contract. An agent handles conversation; a Python service validates '
                        'specifications, computes results and derives artifacts through JSON CLI and seven MCP '
                        'tools. [1] [2]'),
                       ('p',
                        'Version 0.7 acquired 2,133,268 unique NYC 311 requests. Nine pre-study executions '
                        'reconciled that count through normalization, immutable Elasticsearch 9.5.5 indexes '
                        'and independent SQLite references. Five analytical families and complete CSV '
                        'selections agreed. The eighth finite workload measured query medians of 29-77 ms and '
                        'a 9,728-row export in 1.060 s. These are backend observations, not conversational '
                        'latency or maximum capacity. [3] [4] [5]'),
                       ('h', 'Contribution and result boundary'),
                       ('p',
                        'The ninth run verified all three Maps cases after eight retained failures. An '
                        'independent raw-capture audit matched every cell in four 9,728-row exports. However, '
                        'the frozen Qwen3-1.7B candidate passed only one of 120 executed and reviewed trials '
                        '(0.83%); all nine chained analyses failed. Three additional study core preflights '
                        'passed, isolating backend qualification from agent reliability. [4] [15] [16] [17]'),
                       ('note',
                        'Backend and Maps checks passed within the measured scope. Agent quality FAILED the '
                        'fixed 90% and every-question requirements; the sole passing answer was an '
                        'unsupported-request refusal. The conversational release is unqualified. '
                        'Billion-record capacity remains a design target.')]},
           {'title': '1. Analytical contract',
            'blocks': [('p',
                        'A request selects records, aggregate or compare_periods and binds it to a dataset '
                        'version. Bounded Boolean filters, category families, geographic predicates and '
                        'explicit time ranges are supported. Unsupported combinations return typed errors. A '
                        'saved result carries the normalized specification, exact index identity and execution '
                        'flags. [2]'),
                       ('table',
                        ['Phase', 'Service responsibility'],
                        [['Discover',
                          'Expose catalog, field meanings, observed scope, limits and request examples.'],
                         ['Validate',
                          'Resolve time boundaries; reject unsupported operations and unqualified '
                          'comparisons.'],
                         ['Execute',
                          'Compile filters and aggregations; persist result, provenance and completeness.'],
                         ['Inspect',
                          'Return bounded previews with full matching totals and approximation labels.'],
                         ['Derive artifact',
                          'Preserve saved cohort and selected groups; record excluded geography and hashes.']],
                        [100, 388]),
                       ('h', 'Time, coverage and missingness'),
                       ('p',
                        'Intervals are start-inclusive and end-exclusive. The captured window covers April 1 '
                        'to November 1, 2025 in America/New_York. Reconciled capture, normalization and '
                        'frozen-index counts qualify comparison periods within that observed corpus; no '
                        'captured records were dropped. The certificate explicitly retains '
                        'population_complete=false and transactional_source_snapshot=false; a provider '
                        'revision match is not proof of either stronger property. [3] [4]'),
                       ('p',
                        'Administrative closure is elapsed creation-to-closure time, not first response or '
                        'verified resolution. Missing or invalid durations remain null and are excluded from '
                        'duration means while affected requests remain counted. Status and closure values '
                        'reflect the October 2026 capture, not reconstructed status at the historical question '
                        'date. [2] [11]'),
                       ('h', 'Resource-aware execution'),
                       ('p',
                        'Exact row admission precedes CSV-worker reservation. Streaming still enforces byte, '
                        'row, deadline and identity limits. Normalization bounds output and checks free disk; '
                        'these observations are not resource reservations. A preview never silently becomes '
                        'the full export population. [2]')]},
           {'title': '2. Real-corpus analysis',
            'blocks': [('p',
                        'Capture run 37700939902 retained 1,306,911,416 raw JSONL bytes for 2,133,268 unique '
                        'requests. Nine core executions reproduced the same 1,582,275,376 normalized bytes and '
                        'full hash. Captured, normalized, ingested, frozen-index and independent-reference '
                        'counts all equal 2,133,268. Each execution retains its own index UUID, timings and '
                        'failures; no records were dropped. [3] [4] [11]'),
                       ('table',
                        ['Real-data case', 'Observed selection', 'Independent agreement'],
                        [['Brooklyn residential noise, October 1',
                          '242 requests',
                          'Count, ordered preview and full CSV IDs'],
                         ['All October, borough / agency',
                          '336,612 requests; 81 groups',
                          'Complete group counts and status totals'],
                         ['October rodent closure, agency',
                          '1,935 requests',
                          'Count, closed count and valid-duration mean'],
                         ['October, 1 km downtown radius',
                          '3,286 requests',
                          'Radius selection count and grouping'],
                         ['June / October residential-NTA rodent',
                          '3,680 / 1,928 requests; 196 groups',
                          'Counts, 30/31-day rates, closure means and ranking']],
                        [151, 141, 196]),
                       ('h', 'Official geography and analytical scope'),
                       ('p',
                        'The pinned NTA2020 release 26b supplies 262 polygons and 197 residential codes. The '
                        'comparison contains 196 represented residential areas. Across the full corpus, 32,843 '
                        'requests lack geometry and 474 coordinates match no supplied polygon. Those records '
                        'remain visible in quality counts instead of being silently assigned a neighborhood. '
                        '[4] [12]'),
                       ('p',
                        'The SQL reference shares normalized records and NTA assignments. A separate '
                        'raw-capture reconstruction additionally verified 9,705 official-polygon assignments '
                        'and 23 missing locations in the 9,728-row export cohort, using all 262 original '
                        'polygons. This shares GEOS and timezone libraries, and does not independently qualify '
                        'every corpus assignment. The ninth run verified all 196 and three selected rendered '
                        'trend groups; model-led chaining remains a separate outcome. [4] [15]'),
                       ('note',
                        'Table 1. These are observations of the captured public-request corpus. Reporting '
                        'growth is not incident prevalence, statistical significance or proof that '
                        'neighborhood conditions worsened.')]},
           {'title': '3. Recorded engineering results',
            'blocks': [('p',
                        'Run 38031560273 used Elasticsearch 9.5.5 on a Linux host with four logical CPUs and '
                        '16.77 GB RAM. Normalization took 282.763 s; ingestion and freeze took 337.796 s. '
                        'Query timings include service initialization and saved results, excluding model and '
                        'browser work. Other retained runs used different host conditions; their timings are '
                        'not a controlled optimization comparison. [5] [11]'),
                       ('table',
                        ['Query family', 'Median / maximum', 'Serial repetitions'],
                        [['Filter and preview', '28.574 / 31.957 ms', '5'],
                         ['Borough / agency aggregation', '53.787 / 109.474 ms', '5'],
                         ['Administrative closure mean', '32.736 / 57.581 ms', '5'],
                         ['Geographic radius', '33.002 / 41.906 ms', '5'],
                         ['Neighborhood period comparison', '77.207 / 141.573 ms', '5']],
                        [208, 172, 108]),
                       ('p',
                        'Five-query batches took 0.201 s at concurrency one and 0.157 s at concurrency two. A '
                        'full-month Brooklyn residential-noise CSV held 9,728 rows, nine columns and 1,139,937 '
                        'bytes: 1.060 s individually and 1.112 s for two exports together. Separately, four '
                        'retained sixth-run exports matched 350,208 exact cells against independently selected '
                        'raw records, with zero closure error. The files are byte-identical: 87,552 unique '
                        'logical cells, not four independent samples. [5] [15]'),
                       ('p',
                        'An actual worker exited 86 at first-row streaming. Recovery protected its live lease, '
                        'then removed abandoned partial output and allowed exact re-export. The recovery call '
                        'took 0.0181 s; fresh re-export took 0.770 s. This covers one local export-worker '
                        'failure, not Elasticsearch node or mid-ingestion recovery. [5]'),
                       ('p',
                        'Six samples observed runner RSS up to 127.6 MB, combined worker RSS 58.7 MB and '
                        'Elasticsearch heap use 1,474.3 MB within a configured 2 GiB heap. These are sampled '
                        'observations, not guaranteed peaks; node virtual memory is not RSS. Kibana and '
                        'ingestion peak memory remain unmeasured. [5]'),
                       ('note',
                        'Table 2. This workload lasted 5.034 s after prior index queries, with uncontrolled '
                        'caches. Five repeats and two short batches establish neither tail latency, sustained '
                        'throughput, maximum scale nor an SLA.')]},
           {'title': '4. Reproducibility and sources',
            'blocks': [('p',
                        'Nine archived pre-study cores retain separate commits, index identities and failures; '
                        'Table 2 fixes run 38031560273 as its measured condition. Three additional matrix '
                        'cores, later regression, r4 installations and agent receipts bind their own sources. '
                        'Published 488c57c remains the historical edition. Final citations bind the evidence '
                        "commit recorded in this paper's provenance. [4] [6] [7] [11] [16]"),
                       ('p',
                        'The final Windows suite collected 576 tests: 575 passed, one unprivileged-symlink '
                        'test skipped, in 66.672 s. Fresh offline core/MCP/geometry r4 installations checked '
                        '36 wheels, 3,959 RECORD entries, 23 modules and five resources. Target: CPython 3.12 '
                        'Windows x64 on an ARM64 host; other-device qualification is unclaimed. [6] [7]'),
                       ('p',
                        'Default-five previews preserve explicit larger requests, exact totals and full CSV '
                        'membership. The r4 wheels pin packaged core; later repository-only Maps and study '
                        'tools are separate. Local installation success does not establish million-record '
                        'laptop performance or agent quality. [7] [8]'),
                       ('code',
                        'python -m analytics311 describe\n'
                        'python -m analytics311 mcp\n'
                        'python tools/run_real_acceptance.py --help\n'
                        'python -m tools.agent_campaign --help'),
                       ('p',
                        'Transfer ZIPs include core and five historical harness files. New evaluation scripts '
                        'require the matching repository plus separate data, browser, model and server '
                        'runtimes. [7]')]}],
 'external_source_dates': {'https://arxiv.org/abs/1809.08887': '2026-10-09',
                           'https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results': '2026-10-09'},
 'evidence_commit': '4668139874139b597157d01daf475eeacbededfe'},
{
 'number':'03','slug':'03-semantic-discovery','short':'TECHNICAL DOCUMENT DISCOVERY',
 'title':'Search the released knowledge',
 'subtitle':'Offline technical-manual discovery across a controlled metadata boundary',
 'refs':[
   ('Implemented system and architecture','README.md'),
   ('Extraction development diagnostics','reports/extraction-development.md'),
   ('Retrieval development evaluation','reports/retrieval-development.md'),
   ('Guided interface verification','reports/interface-verification.md'),
   ('Build and portable-runtime verification','reports/build-verification.json'),
   ('Operating and reproduction guide','RUNBOOK.md'),
   ('Measured acceptance and evidence scope','reports/acceptance-status.md'),
 ],
 'pages':[
 {'title':'','blocks':[
   ('h','Abstract'),
   ('p','Technical discovery has two distinct tasks: interpreting a scanned manual and searching what is permitted to leave the source workspace. Vintage Overseas Power Tools (VOPT) implements both as an offline pipeline. Original PDFs, OCR and evidence remain private to extraction and review; discovery receives a validated metadata snapshot with either coverage or approved values. [1]'),
   ('p','The development corpus contains five admitted historical manuals and 616 pages. Layout-aware rules matched 13 of 17 selected reference fields, compared with four for a line baseline. Retrieval over reviewed values recorded recall@10 of 0.912 on 17 authored positive queries. These are development diagnostics with agent-inspected references, not held-out accuracy or human-gold estimates. [2] [3]'),
   ('h','Problem and design objective'),
   ('p','The SCADS task asks for technical attribute extraction from scanned documentation and natural-language document discovery. The implemented objective is discovery with inspectable constraints: identify the relevant document and model without inventing values or leaking source content into the released index. Numerical filtering requires released values; coverage-only metadata can establish that a topic is covered but cannot satisfy a threshold. [1]'),
   ('h','Implemented contribution'),
   ('p','A private extraction workspace, append-only review, strict release profiles and a separate discovery process form the core. The query compiler preserves model, variant, units and conditions. A guided Equipment  ->  Specification  ->  Results interface helps users express the bounded grammar while exposing unknowns and partial processing. [1] [4]'),
   ('note','Evidence class: authentic historical scans used during development; agent-reviewed observations; authored queries; local packaging and interface verification. Source interpretation and retrieval are evaluated separately.'),
 ]},
 {'title':'1. Architecture and release boundary','blocks':[
   ('table',['Workspace','Implemented method','Output'],[
      ['Extraction','PyMuPDF geometry/native text; local RapidOCR ONNX for image pages','Page records, model-scoped candidates and evidence coordinates'],
      ['Review','Append-only decisions bound to extraction fingerprints','Accepted/corrected assertions with reviewer provenance'],
      ['Release','Field allowlists and separate coverage/value profiles','Validated versioned metadata bundle'],
      ['Discovery','SQLite, exact predicates and BM25; TF-IDF comparator','Ranked document/model scopes and request references'],
   ],[79,225,184]),
   ('p','Every candidate must preserve document revision, model, attribute, value or range, unit and rating/operating qualifiers. A correctly read number can still be attached to the wrong component or configuration. Review therefore examines factual scope rather than treating OCR confidence as a probability that a specification is true. [1] [2]'),
   ('h','Coverage is a separate product'),
   ('p','Coverage exports describe verified attribute presence. Value exports may additionally include approved typed values and conditions. A coverage query such as which manuals discuss voltage differs from a request for equipment above a voltage threshold. The discovery service rejects unsupported numeric filtering under a coverage-only profile rather than dropping the constraint. [1] [5]'),
   ('h','Exact predicates precede ranking'),
   ('p','The query plan is inspectable: identifiers, attribute roles, operators, units, Boolean structure and conditions are explicit. Hard predicates enforce same-model and compatible-variant scope before ranking. BM25 is the default ranker. The semantic comparator is ontology-normalized TF-IDF, not a pretrained embedding system. Both share the same predicate compiler. [1] [3]'),
   ('p','Atomic catalog import and full index replacement support controlled release changes. Review and extraction fingerprints detect stale decisions, while monotonic withdrawal handling prevents a rollback from simply restoring removed metadata. The separate discovery installation has neither source files nor extraction dependencies in its verified profile. [1] [5] [7]'),
 ]},
 {'title':'2. Worked discovery: HR-28','blocks':[
   ('p','A verified browser journey asks for model HR-28 with output power at least 1.4 kW, output voltage at least 30 V and DC operation. The guided interface returns one confirmed match in the Homelite manual, along with the partial-processing notice. Supporting assertion IDs and the source revision remain attached to the request reference. [4]'),
   ('table',['User intent','Interpretation','Observed behavior'],[
      ['Generator manuals covering output voltage','Coverage; no threshold','M7 and HR-28 confirmed; incomplete scopes shown separately.'],
      ['Output voltage at least 125 V','Value constraint','No confirmed matches; six records require more detail.'],
      ['HR-28, >=30 V, >=1.4 kW, DC','Same model and compatible conditions','One confirmed match with provenance and partial-processing notice.'],
      ['Voltage above 100 V','Input/output role ambiguous','Clarification required.'],
   ],[151,154,183]),
   ('p','This example illustrates why model and qualifier association matter more than matching a keyword. Input voltage is not output voltage, and electrical input power must not become mechanical output power through a unit conversion. A compendium containing several models cannot satisfy a conjunction by joining one model\'s voltage to another model\'s power. [1] [4]'),
   ('h','A request, not an invented document answer'),
   ('p','The exported JSON stores a document/version reference, catalog identity, query and supporting assertion IDs. A verified journey saved HR-28 from a coverage query, then ran a different numeric query; the actual downloaded request still retained the originating query. It contained released metadata rather than original PDF or OCR content. [4]'),
   ('h','Unknowns remain visible'),
   ('p','An unobserved field means unknown, not absent or zero. Partial page processing is retained with matches, and ambiguous operating conditions are not converted into broad ranges. A discovery result therefore describes what the approved catalog can support, while document acquisition remains a separate action. [1] [3] [4]'),
   ('note','Table 1. These are agent-operated browser checks on the frozen development catalog. They verify specific interface behavior, not independent usability or generalized extraction accuracy. [4]'),
 ]},
 {'title':'3. Development results','blocks':[
   ('table',['Measure','Observed value','Denominator / scope'],[
      ['Admitted scans','5 manuals; 616 pages','610 processed pages; 6 explicit failures. [2]'],
      ['Selected field matches','Layout 13/17; line 4/17','Document, page, model, attribute, unit, value and qualifier. [2]'],
      ['Reviewed-values retrieval','Macro recall@10 0.912; macro MRR@10 0.941','17 positive authored queries; 22 known scopes. [3]'],
      ['Reference-values retrieval','Macro recall@10 1.000; macro MRR@10 1.000','Same known positives; diagnostic reference metadata. [3]'],
      ['Plan status checks','33/33','Authored source-reference queries. [3]'],
      ['Recorded regression suite','151 passed','Build-verification snapshot; separate from later UI checks. [5]'],
   ],[136,151,201]),
   ('p','Selected field matches are not exhaustive recall or full-assertion precision. The extraction report notes that conditions and component meaning need additional review. The retrieval reference condition is also deliberately separate from reviewed extraction: perfect reference-metadata retrieval cannot conceal omissions in the actual catalog. Both rankers produced equal reported results in these development comparisons. [2] [3]'),
   ('h','An informative failure distinction'),
   ('p','A preserved first M18 audit supported all 17 numeric transcriptions but only five candidates with essential factual scope. Nine needed scope repair and three named the wrong entity. A repaired seven-candidate record was source-inspected as supported, but suppressed observations and a known development manual prevent a recall or generalization claim. The lesson is that number recognition and technical truth are different evaluation targets. [2]'),
   ('h','Offline evidence'),
   ('p','The recorded portable discovery and extraction profiles cold-started on the existing Windows host using packaged assets, with Python network attempts blocked. Discovery operated without private source files. These checks support the tested packaging boundary; they are not OS-level network isolation or independent clean-target certification. [5]'),
 ]},
 {'title':'4. Reproducibility and sources','blocks':[
   ('p','Use the operating guide for the private extraction/review and released discovery workflows. Frozen evaluation records preserve the processing versions that produced them; do not silently reprocess them and present new results as the original experiment. Source and review provenance are part of the research artifact. [6] [7]'),
   ('code','python -m vopt doctor\npython -m pytest -q\npython scripts/evaluate_extraction.py --skip-ingest'),
   ('p','Run these commands from the environment described in the implementation guide and RUNBOOK. Exact historical extraction replay requires the separately retained frozen runs/real-workspace or research-evidence bundle; a Git-only checkout is not a self-contained copy of that workspace. Fresh corpus acquisition and OCR constitute a new run. For discovery reproduction, use a versioned released catalog and inspect its query plan. Package hashes and later UI checks identify their respective snapshots. [1] [4-6]'.replace('[4-6]','[4] [5] [6]')),
   ('h','Evidence-linked references'),('refs',),
   ('note','Publication reproduces recorded measurements, not a new OCR evaluation. No human-gold, untouched-family, labor-savings or classified-deployment claim is made.'),
 ]},
 ]
},
{
 'number':'04','slug':'04-org-knowledge-graphs','short':'ORGANIZATIONAL KNOWLEDGE GRAPHS',
 'title':'An organization chart with evidence',
 'subtitle':'Conservative relationship inference and navigable organizational knowledge',
 'refs':[
   ('Implemented workbench and synthetic corpus','README.md'),
   ('Canonical data and API contract','docs/implementation-contract.md'),
   ('Recorded software and browser verification','docs/verification.md'),
   ('10,000-person communication-corpus result','docs/synthetic-10000-results.json'),
   ('Synthetic storage benchmark','docs/benchmark-results.json'),
   ('Inference research and evaluation distinctions','research/inference.md'),
   ('Completion evidence and acceptance scope','docs/acceptance.md'),
 ],
 'pages':[
 {'title':'','blocks':[
   ('h','Abstract'),
   ('p','Communication records can suggest authority, collaboration and membership, but these are different relationships. This workbench keeps their types and provenance separate while building an inspectable organization graph. The implementation combines staged intake, conservative local inference, immutable SQLite snapshots, reversible analyst review and a React interface with bounded semantic zoom. [1] [2]'),
   ('p','A deterministic synthetic corpus with 10,000 people and 76,680 messages was imported and analyzed in a recorded local run. It produced 7,489 selected reporting links and retained 2,511 unresolved people. Read-only traversal reached every person through formal and inferred groupings. These results demonstrate workflow and navigability on authored data, without treating raw scores as probabilities or generated labels as independent accuracy evidence. [3] [4]'),
   ('h','Problem and design objective'),
   ('p','The SCADS problem concerns deriving organizational knowledge from partial evidence and supporting exploration as the graph grows. The implemented objective is to preserve the distinction between what a source states, what the baseline infers and what an analyst reviews. A visually complete tree must not conceal unresolved managers or convert communication frequency into direct supervision. [1] [2] [6]'),
   ('h','Implemented contribution'),
   ('p','The working system integrates evidence spans, typed authority relations, sparse candidate generation, revision-aware review and scalable navigation. Intake profiles the proposed corpus before saving it. The graph can be explored through departments, communication groups, reporting branches and individual connections without drawing every person at once. [1] [2]'),
   ('note','Evidence class: fictional communications and source hierarchies, engineering checks and recorded local timings. Ranking scores are explicitly uncalibrated; synthetic labels are excluded from inference inputs.'),
 ]},
 {'title':'1. Inference and durable review','blocks':[
   ('table',['Layer','Implemented responsibility'],[
      ['Intake','Parse canonical JSON, message/roster CSV and mail formats; profile quality and preview a bounded source graph.'],
      ['Inference','Generate sparse candidates from communications and explicit self-report language; retain unresolved people.'],
      ['Evidence','Keep message spans, communication aggregates, source assertions and analyst references distinct.'],
      ['Persistence','Store immutable snapshots, durable jobs and append-only review events in SQLite.'],
      ['Exploration','Serve snapshot-bound pages and bounded graphs through FastAPI to React/TypeScript.'],
   ],[90,398]),
   ('p','The canonical assertion includes subject, relation, object, origin, evidence IDs, review status and temporal bounds. Primary and matrix reporting can be represented separately. Raw scores and calibration status are distinct fields, and a reviewed replacement does not acquire a model probability merely because it appears in the same chart. [2]'),
   ('h','Isolate labels from inference'),
   ('p','The inference service strips evaluation labels, existing assertions and source evidence before sending entities and messages to its baseline engine. The fixture labels can describe authored structure without becoming hidden inputs. This is necessary for a meaningful software check, although shared organization and language templates still limit any accuracy interpretation. [1] [2] [4]'),
   ('h','Review is a versioned action'),
   ('p','Accept, reject, replace and undo operations require the current workspace revision and preserve their history. Rejecting a relation continues to matter across refreshed inference. Exported canonical packages can preserve historical projections and evidence; package restoration requires an empty workspace. Snapshot comparison evaluates semantic relationships instead of merely comparing assertion IDs. [2] [3]'),
   ('p','Intake inspection is staged in memory before an explicit build. The preview reports accepted records, missing-field coverage and a bounded source graph. It does not portray imported proposals as established authority. Exact inventory counts and visible processing stages let a user understand what will be saved. [2] [3]'),
 ]},
 {'title':'2. Worked exploration journey','blocks':[
   ('p','The synthetic entry path defaults to 10,000 people. Its reviewed preview measured 76,680 messages, 45 units, two shared mailboxes and 60,657 directed communication links. Evaluation labels remained separate. The workflow draws inspect  ->  profile  ->  plan  ->  database  ->  infer  ->  ready; explanatory replay is labeled and does not perform another inference run. [3]'),
   ('table',['Interaction','Recorded behavior','Analytical purpose'],[
      ['Enter a department','Move from aggregate scope to reporting branches','Keep organization-wide navigation readable.'],
      ['Focus a person','Display selected manager, alternatives and evidence','Connect the chart to its claims.'],
      ['Continue zooming','Expand from 29 to 79 to 199 links','Reveal context without shifting existing card positions.'],
      ['Inspect a reporting marker','Show source/model origin and review/calibration state','Avoid reading visual certainty as statistical confidence.'],
      ['Return to a prior scope','Restore camera and expanded context','Preserve the analyst\'s place in the investigation.'],
   ],[114,196,178]),
   ('h','Bound the display, preserve reachability'),
   ('p','The interface retains a rolling metadata window of at most 240 cards and renders at most 200 nearby cards. A bounded response cache supports return navigation. Reporting branches are presentation groups derived from selected links, not new formal teams. Explicit unassigned buckets keep unresolved people reachable. [1] [3]'),
   ('p','Read-only traversal of the live synthetic snapshot reached all 10,000 people through both chart lenses: 476 formal scopes over 501 pages, and 1,077 inferred scopes over 1,082 pages. Edge closure was checked so every displayed link referred to displayed people. These are coverage and consistency observations rather than browser frame-rate measurements. [3]'),
   ('note','Figure 1. The interaction sequence reflects recorded browser checks. Formal units, inferred communication groups and reporting branches remain differently labeled throughout the journey. [3]'),
 ]},
 {'title':'3. Recorded measurements','blocks':[
   ('table',['10,000-person communication run','Observed value'],[
      ['Messages / entities','76,680 / 10,047'],
      ['Generation / import','0.711 s / 9.199 s'],
      ['Inference and publication','46.979 s'],
      ['Selected / unresolved people','7,489 / 2,511'],
      ['Formal and inferred groups','107'],
   ],[279,209]),
   ('p','These values describe one local Windows run, with source and corpus fingerprints preserved. The synthetic generator uses deterministic templates and authored labels; the outcome is not an accuracy, calibration or unlabeled-transfer result. Unresolved people are an explicit output rather than nodes forced into a complete tree. [4]'),
   ('table',['Separate source-only benchmark','10,000 mixed','100,000 mixed'],[
      ['Import','2.749 s','77.945 s'],
      ['List page warm p95','27.311 ms','120.228 ms'],
      ['Substring search warm p95','45.378 ms','754.730 ms'],
      ['Focused graph warm p95','40.723 ms','42.893 ms'],
   ],[258,115,115]),
   ('p','The second table measures Python/SQLite reads on source-only hierarchies, using seven warm repetitions and a 200-node graph budget. Its nearest-rank p95 is descriptive for that small sample; caches were not flushed. HTTP, browser rendering, dense communication processing and inference quality are outside this benchmark. [5]'),
   ('h','Verification and interpretation'),
   ('p','The recorded current intake build passed 144 Python tests, 99 frontend checks and the production build. Browser verification covered source preview, saved-workspace reuse, isolated import/build, cancellation and responsive layout. The evidence supports a durable, inspectable workflow and bounded navigation; it does not establish that communications reveal real managerial authority with calibrated confidence. [3] [7]'),
 ]},
 {'title':'4. Reproducibility and sources','blocks':[
   ('p','Use a separate database for each reproduced corpus. The default small fixture offers a quick review/export workflow; the deterministic generator also supports the documented 10,000-person case. Save source fingerprints and record environment and load when comparing timings. [1] [4]'),
   ('code','python -m orggraph demo --people 10000 --output runs/demo/corpus.json --generate-only\npython -m orggraph --db runs/demo.sqlite3 demo --people 10000\npython -m pytest -q\nnpm --prefix frontend test'),
   ('p','Run from the nested project directory after the documented dependency setup. The benchmark script and raw result file specify workload shapes, read methods and cache assumptions. The verification report links the browser evidence and distinguishes successive software milestones; test totals should always be attributed to the corresponding snapshot. [1] [3] [5]'),
   ('h','Evidence-linked references'),('refs',),
   ('note','No raw score is presented as a probability. Software tests, graph reachability, storage timing and real-world inference quality remain separate quantities in this publication.'),
 ]},
 ]
},
{
 'number':'05','slug':'05-graphrag-discovery','short':'TEMPORAL GRAPHRAG DISCOVERY',
 'title':'What changed, and when did we know?',
 'subtitle':'Local graph-assisted discovery with temporal provenance',
 'refs':[
   ('Current application and execution policy','README.md'),
   ('Implemented retrieval, history and interface','docs/implementation-status.md'),
   ('Authored temporal pump fixture','fixtures/pump/README.md'),
   ('Expected temporal states and comparisons','fixtures/pump/gold.json'),
   ('Actual local-model and vector smoke test','docs/local-model-validation.md'),
   ('Installation and package reproduction','docs/installation.md'),
   ('Temporal design and comparison semantics','docs/temporal-workflow.md'),
 ],
 'pages':[
 {'title':'','blocks':[
   ('h','Abstract'),
   ('p','A new search result can reflect a changed world, a late-arriving document, a correction or a different ranking. This GraphRAG discovery application preserves those distinctions through immutable source history, published knowledge snapshots, assertion validity intervals and saved baselines. It runs locally with a Python/SQLite core, a browser workspace and optional llama.cpp extraction and embeddings. [1] [2]'),
   ('p','A five-batch fictional pump history exercises plans, late corrections, conflicts and withdrawal. Its authored expectations specify eight historical states and two fixed-knowledge comparisons. A separate actual local-model smoke test extracted two source-grounded assertions and indexed three vectors. These are temporal consistency and integration observations, not a retrieval-quality or scale benchmark. [3-5]'.replace('[3-5]','[3] [4] [5]')),
   ('h','Problem and design objective'),
   ('p','The SCADS problem motivates discovery over connected evidence as a corpus changes. The implemented objective is to make each finding inspectable at a selected knowledge and world-time scope. A relationship must retain its source version and exact passage, while a baseline comparison must survive changes in top-ranked search results. [1] [2] [7]'),
   ('h','Implemented contribution'),
   ('p','The working system combines lexical, exact dense, hybrid and graph-assisted retrieval with eligibility checks before scoring. It saves investigations and scoped baselines, supports source-linked graph exploration and exports verifiable evidence bundles. Typing previews are a separate bounded keyword path that highlights evidence without calling a model or replacing committed results. [1] [2]'),
   ('note','Evidence class: manually authored temporal expectations, actual local-model development smoke tests and fixture/interface verification. Local inference uses no paid API dependency.'),
 ]},
 {'title':'1. Method: provenance before scoring','blocks':[
   ('table',['Concern','Implemented representation'],[
      ['Source identity','Immutable revisions, exact UTF-8 hashes and Unicode code-point spans'],
      ['System knowledge','Separate source availability, receipt, preparation and atomic publication'],
      ['World claims','Half-open validity intervals, known/open/unknown bounds and reported/planned/negated modality'],
      ['Retrieval','Lexical scoring, exact cosine, reciprocal-rank fusion and bounded graph expansion'],
      ['Comparison','Saved findings or fixed neighborhood seeds, paired before/after evidence and scoped coverage'],
   ],[113,375]),
   ('p','Eligibility is established before vector scoring. An index cannot justify retrieving future evidence into an earlier knowledge view. Immutable vector artifacts bind profile and text hashes; missing eligible vectors fail explicitly. The graph mode expands assertion seeds within declared candidate, hop and evidence limits. [2]'),
   ('h','Extraction is a proposal boundary'),
   ('p','The local model proposes assertions. The client validates exact quotations and endpoint mentions, creates mention-scoped identities and stages proposals before publication. Unknown dates remain unknown unless explicitly supported. Exact-span validation establishes mechanical grounding, while semantic correctness still depends on what the quoted language actually means. [2] [5]'),
   ('h','Three different comparisons'),
   ('p','A saved baseline can track selected findings or a fixed entity neighborhood. Knowledge comparisons inspect newly available support, corrections and withdrawals. Fixed-knowledge world comparisons hold the evidence cutoff constant while changing the claimed validity time. These answer different questions: what was learned versus what the sources say happened. [2] [7]'),
   ('p','The implementation uses SQLite and exact vectors. Its limits are explicit guardrails rather than benchmarked capacity promises. A displayed neighborhood is a bounded evidence projection, and a net comparison concerns endpoint states in its declared scope; neither implies semantic completeness over the corpus. [2]'),
 ]},
 {'title':'2. Worked temporal history','blocks':[
   ('p','The authored Pump P case uses controlled clocks and explicit one-operator-at-a-time semantics. Every assertion endpoint and interval is stated in its source sentence. The fixture isolates the difference between planned, reported, conflicting and withdrawn support. [3]'),
   ('table',['Published batch','Evidence meaning','Correct interpretation'],[
      ['January 5','A operates Pump P from January 1','Reported A, with no stated end.'],
      ['January 20','Plan: A ends and B starts February 1','Passing February 1 does not confirm B.'],
      ['February 10','Late correction: handover occurred February 3','Availability February 4 differs from receipt/publication February 10.'],
      ['February 12','Independent report names C from February 3','B and C coexist as disputed claims under fixture exclusivity.'],
      ['February 15','C source withdrawn','B support survives; withdrawal is not a physical handover.'],
   ],[93,186,209]),
   ('h','The same world date, different knowledge'),
   ('p','At a February 5 knowledge cutoff, the February 2 world-time view returns B as planned. At a February 11 cutoff, the corrected retrospective February 2 view returns reported A. The question\'s world date has not changed; the available evidence has. At the February 3 boundary, the later corrected history returns B because validity intervals are half-open. [4]'),
   ('h','Compare without future leakage'),
   ('p','Holding knowledge fixed at the February 10 publication allows a reported A-to-B comparison between January 31 and February 4. Holding knowledge fixed at the January 20 publication produces a planned transition instead. The later correction must not leak into the earlier answer. [4]'),
   ('note','Table 1. All dates and operator claims are fictional test values. The expected-state file was manually specified rather than generated from engine outputs; agreement tests authored semantics, not an actual pump history. [3] [4]'),
 ]},
 {'title':'3. Local-model and software evidence','blocks':[
   ('table',['Recorded observation','Value / result','Interpretation'],[
      ['Local extraction source','73 authored characters','Two simple fictional sentences.'],
      ['Validated assertions','2: reported and planned','Exact spans; unknown dates retained.'],
      ['Extraction/publication/query','29.39 s','One local run, excludes model startup.'],
      ['Vector index','3 vectors  x  2,048 components','One source chunk and two assertions.'],
      ['Vector-phase elapsed','2.44 s','Excludes restart/loading; integration smoke.'],
      ['Version 0.3.2 checks','138 Python + 30 frontend','Fixture and interface behavior.'],
   ],[161,158,169]),
   ('p','The actual local source states that Mira Labs operates Harbor Station and plans to lease Willow Annex. Qwen3-VL-2B-Instruct Q4_K_M through a dedicated llama.cpp server produced two grounded proposals. The queries preserved reported versus planned modality and null temporal bounds. Eight extraction-phase checks and eight vector-phase checks were recorded. [5]'),
   ('p','An initial embedding request on the chat-configured server returned HTTP 501; that attempt is preserved. After a separate embedding/pooling configuration, real vectors and query embeddings supported hybrid and graph queries with source-resolving exports. The same decoder weights demonstrate integration only; three exact-index rows do not establish semantic ranking quality or approximate-nearest-neighbor performance. [5]'),
   ('h','Interactive evidence without hidden inference'),
   ('p','The version 0.3.2 preview debounces typing for 300 ms and uses a separate bounded keyword/prefix endpoint. It creates no model calls or saved runs. Stale responses cannot replace newer scope or committed analysis; Escape, clearing or pausing restores the previous evidence state. Recorded desktop and 390  x  844 mobile checks exercised source tracing and restoration. [2]'),
   ('p','The evidence supports a reproducible local system that makes temporal and source distinctions visible. Whether graph expansion improves discovery over lexical or hybrid retrieval remains a separate empirical question; this publication reports no comparative quality uplift. [1] [2]'),
 ]},
 {'title':'4. Reproducibility and sources','blocks':[
   ('p','The authored demo needs only the application runtime and creates a new database, report and evidence bundles. Use fresh paths: the demo refuses to overwrite existing output. Local extraction and embeddings require the separately configured llama.cpp model service documented in the source. [1] [2] [6]'),
   ('code','python -m graphrag_discovery --db runs/demo.sqlite3 demo --output runs/demo\npython -m graphrag_discovery --db runs/demo.sqlite3 serve --port 8765\npython -m unittest discover -s tests -v'),
   ('p','Run from the nested project directory or an installed environment. The service binds to loopback; the authored demo uses simulated time and does not make model requests. Wheel/sdist installation instructions distinguish the application from separately installed model assets. Evidence bundles preserve source spans and hashes for inspection. [2] [6]'),
   ('h','Evidence-linked references'),('refs',),
   ('note','The static publication does not execute new model or performance experiments. Recorded development observations, authored temporal semantics and measured software behavior remain explicitly separate.'),
 ]},
 ]
}
]
