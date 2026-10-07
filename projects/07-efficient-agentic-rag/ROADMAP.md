# Retrieval only when it earns its cost

A projected study of adaptive multilingual RAG and evidence-aware evaluation

**Status: Not started. Projected solution and research plan. Implementation and evaluation have not begun.**

Boomer Rawlings | Independent individual portfolio work | October 7, 2026

## 6. Roadmap, reproducibility and validity

| Phase | Planned deliverable | Exit criterion |
| --- | --- | --- |
| A: benchmark freeze | Edition, licenses, split and scoring manifest | Data access and evaluation scope verified |
| B: fixed baselines | Lexical/dense/fused retrieval plus cited generation | Reproducible runs and cost accounting |
| C: controller | Routing, translation, stopping and budget enforcement | No hidden test labels; bounded actions |
| D: judge pilot | Bilingual rubric and adjudicated development labels | Bias checks; sample-size decision |
| E: frozen comparison | Held-out runs and paired analyses | All runs included; confidence intervals |
| F: publication | Paper, manifests, scripts and demonstration | Independent reproduction of scoring |

The run manifest will pin collection version, document IDs, chunking, indexes, model revisions, prompts, seeds, language routes, budgets, hardware and cache state. A separate judge manifest will identify rubric, model, calibration split and parser version. Generated evaluation artifacts will never overwrite the original answer or source evidence.

Dataset availability, reuse terms and human judgment coverage are feasibility gates. A newer track release is not interchangeable with the 2024 English benchmark. Likewise, translation quality and document-topic imbalance may dominate nominal language effects. The analysis will report per-language sample sizes and uncertainty, and will avoid claiming typological generality from four languages.

A future product demonstration will display the retrieval route, remaining budget and source-linked answer for an authored multilingual fixture. The current publication offers this plan only. There is no working controller, judge implementation or measured quality-cost frontier in this project directory.

