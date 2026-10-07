# A model is not ready until the device is

A projected validation and monitoring pipeline for resource-constrained deployment

**Status: Not started. Projected solution and research plan. Implementation and evaluation have not begun.**

Boomer Rawlings | Independent individual portfolio work | October 7, 2026

### Abstract

A model that meets quality targets in a development environment can fail after quantization, runtime conversion or deployment to a constrained device. This proposal specifies a core-to-edge validation pipeline that treats the deployable artifact, runtime and hardware profile as a single versioned unit. It will compare optimized models with a frozen reference, evaluate quality and resource gates, and monitor deployed behavior within a bounded overhead budget. [1]

The projected study asks which core measurements predict device-level failures, how much calibration and validation data is necessary, and whether lightweight telemetry detects actionable degradation without erasing the resource savings of optimization. Physical-device trials will remain distinct from simulation. The planned output is an auditable release decision with reproducible measurements and rollback evidence, rather than a claim that compression alone makes a model edge-ready.

### Status and scope

> NOT STARTED. This is a projected solution, validation protocol and implementation roadmap. No model has been optimized, no hardware experiment has been run and no monitoring system has been deployed. All numerical budgets and thresholds are proposed study parameters.

The project is planned as independent individual work by Boomer Rawlings after the original submission and grading dates. The initial scope is one modest classification workload and one compact language workload on explicitly identified device classes. Broader edge generalization would require additional tasks, devices and environmental conditions.

## 1. Research questions and methodological context

The transition to edge deployment changes more than model weights. Kernel availability, operator fusion, memory allocation, precision, thermal limits, storage and input preprocessing can alter both correctness and resource use. The proposed unit of analysis is therefore a release tuple: model hash, tokenizer/preprocessor hash, runtime build, configuration and device profile. Comparing only model names would confound these factors.

MLPerf Tiny motivates measuring accuracy, latency and energy together for resource-constrained inference. Its tasks and measurement discipline are useful references, while its results cannot be transferred directly to a compact language workload or a different device. SmoothQuant motivates one post-training quantization candidate for suitable language models; the availability of a method does not guarantee that a selected runtime has efficient kernels for it. [2] [3]

Knowledge distillation motivates a student model trained to preserve useful behavior of a larger teacher. It will be treated as a separate optimization family with its own training-data and compute costs. Dataset documentation will record calibration, training and evaluation partitions, preventing a small calibration set from being mistaken for independent validation. [4] [5]

### Research questions

RQ1: Which core measurements predict quality or resource gate failures on physical devices? RQ2: How do quantization, distillation and runtime conversion affect different task slices? RQ3: How does calibration-set size and diversity change quality retention? RQ4: What monitoring signal provides useful detection under a fixed compute, memory and telemetry budget?

The principal hypothesis is that a release gate combining slice-level quality, tail latency, memory headroom and artifact checks predicts successful device execution better than mean accuracy alone. This is a projected hypothesis. A second hypothesis is that stratified calibration data reaches a given quality target with fewer samples than an unstratified subset; neither outcome is assumed.

## 2. Proposed release architecture and contracts

| Tier | Planned responsibility | Retained evidence |
| --- | --- | --- |
| Core training | Train or select reference; optimize candidates | Data splits; weights; optimizer configuration |
| Core validation | Quality tests, conversion checks and stress profiles | Paired outputs; failure slices; gate decisions |
| Device qualification | Physical execution under declared conditions | Latency/energy traces; runtime and device IDs |
| Edge inference | Run approved artifact; enforce local budgets | Bounded summaries; local error counters |
| Core operations | Aggregate telemetry; review drift; authorize updates | Version lineage; rollout and rollback records |

The release manifest will identify model and auxiliary file hashes, compatible operator/runtime versions, input schema, expected output schema, supported hardware and measured gates. A device will reject an incompatible or incomplete bundle before activation. Integrity verification and an atomic activation record will distinguish downloading a candidate from making it the active model.

The initial projected design uses a signed manifest, a staged candidate slot and a known-good rollback slot. An interrupted download can resume without activating partial files. Activation occurs only after local integrity and smoke checks. The rollback decision preserves the prior working artifact and the failed candidate evidence. These are proposed mechanisms requiring implementation and fault-injection verification.

Training, label adjudication and full evaluation remain at the core. The edge performs inference, budget enforcement and bounded monitoring. Telemetry is queued locally during disconnection with a fixed retention cap; aggregation records missing intervals rather than infer that silence means healthy operation. The proposed policy favors summary metrics and sampled diagnostics over uploading unrestricted raw inputs.

> The deployable artifact is the entire release tuple. A weight file passing a core test is necessary evidence, but it is not a device qualification result.

## 3. Optimization study and data requirements

The initial experiment will compare a frozen reference with several admissible candidates: lower-precision conversion, post-training quantization, a distilled student and combinations supported by the runtime. Each candidate must preserve the input and output contracts or document the changed task. A conversion that changes preprocessing will be evaluated as a distinct system, not a pure precision change.

### Separate data roles

Data will be partitioned into training, optimization/calibration, development validation and a locked final test set. For the language workload, prompts and documents from the same task family will stay together. For classification, repeated measurements from the same subject or device will remain in one partition where applicable. Calibration subsets will never be sampled from final test data.

A proposed calibration-size sweep uses 32, 128, 512 and 2,048 examples when the dataset supports those counts, with three fixed subset seeds. Counts are planning parameters, not asserted minima. Random and stratified selection will be compared at equal size. Stratification will cover task labels, input length or complexity and stress slices without using final outcomes to choose the subset.

Quality retention will be measured against both reference predictions and independent task labels. Agreement with an incorrect reference is not task accuracy. Language evaluation will include exact or executable checks where suitable and separately audited support/faithfulness labels for generated text. Distillation cost includes teacher inference and student training, while quantization cost includes calibration and conversion.

### Selecting a minimum

The minimum-data estimate will be the smallest prespecified calibration condition whose confidence interval satisfies the quality gate on an independent validation set, followed by one locked-test confirmation. If intervals overlap the threshold, the answer is insufficient evidence, not an interpolated exact minimum. Curves and uncertainty will be reported by task slice; one global count cannot guarantee coverage of rare failures.

## 4. Physical-device evaluation and release gates

Core resource limits and emulation will screen candidates, but final qualification requires actual target hardware. The proposed initial hardware matrix includes a CPU-only laptop-class device and a low-power ARM device, selected before measurement. Hardware model, RAM, operating system, runtime, power mode, ambient conditions and thermal state will be recorded. Simulator and device results will be presented separately.

| Gate | Proposed measurement | Release interpretation |
| --- | --- | --- |
| Task quality | Paired accuracy/support change and slice failures | Noninferiority margin fixed before testing |
| Latency | Cold start, warm median and p95/p99 | Meets declared interactive or batch budget |
| Memory | Peak resident/device memory; allocator failures | Headroom remains under worst tested input |
| Energy | External meter or qualified device counter | Report baseline subtraction and uncertainty |
| Reliability | Repeated runs, restart, offline and update faults | No silent corruption; verified recovery |

An example planning gate is no more than a two-percentage-point task-quality loss with at least 15% memory headroom. These values are not universal acceptance standards; the actual task owner must choose them before evaluation. Latency and energy limits require a concrete device and use case. Passing a mean latency target while repeatedly missing the tail budget will count as failure.

Trials will distinguish cold initialization, warmed steady state and sustained operation under thermal stress. Candidate order will be randomized or counterbalanced across repeated sessions. Input order, batch size and concurrency will be fixed within a comparison. Measurements from a single loop are correlated, so uncertainty will use session/device blocks rather than treat every inference as independent.

The predictive analysis will compare core-only release decisions with physical-device outcomes on held-out candidate/device combinations. False acceptance is a core gate pass followed by device failure; false rejection is the reverse. Thresholds will be tuned on development combinations and assessed once on held-out combinations, preserving the distinction between fitting a rule and validating it.

## 5. Lightweight monitoring and disconnected operation

The planned monitor will track inference latency histograms, input schema violations, memory pressure, exception categories, model/runtime versions and a bounded sample of confidence or disagreement proxies. It will have explicit CPU, memory, storage and telemetry caps. A proposed starting overhead budget is at most 2% added median latency, subject to task-specific revision before testing.

### Accuracy is not directly observable without labels

Confidence changes, input drift and teacher disagreement may indicate a problem, but they do not establish a drop in task accuracy. The monitor will name them as proxies. Confirmed quality measurements require delayed labels or a controlled local canary set whose coverage is known. A detector that sees only the model output cannot be assumed to distinguish a new valid input distribution from a harmful shift.

The study will inject documented changes into authored or licensed test streams: input-scale shifts, missing fields, length changes, runtime failures and resource contention. Detection delay, false-alert rate and overhead will be measured separately. Detector thresholds will be selected on development streams and frozen for a held-out sequence containing both benign changes and harmful degradation.

### Escalation and rollback

A local hard fault, such as incompatible artifacts or repeated inference crashes, can trigger a bounded fallback or rollback according to the release policy. A soft drift alert queues evidence for core review; it does not automatically retrain or replace the model. Centralized review will determine whether more labels, a new calibration set or a new model is appropriate.

During disconnection, telemetry will use bounded queues and sequence numbers. Reconnection merges summaries idempotently and records dropped intervals. Fault-injection trials will cover interruption during download, activation and telemetry transfer. Successful recovery must preserve the active version record and avoid duplicate aggregation. A future monitor demonstration will use a simulated stream explicitly labeled as such; no deployed fleet exists in the present project.

## 6. Roadmap, statistics and reproducibility

| Phase | Planned work | Exit evidence |
| --- | --- | --- |
| A: task/device contract | Select workloads, hardware and owner-approved gates | Frozen task, device and measurement protocols |
| B: reference harness | Pin artifacts; implement paired quality/resource tests | Reproducible baseline and measurement checks |
| C: optimization matrix | Quantize/distill; sweep calibration subsets | Hashes, cost records and validation curves |
| D: device qualification | Run physical trials and held-out gate prediction | Session-level confidence intervals; failure matrix |
| E: edge operations | Build monitor, update slots and bounded telemetry | Overhead, alert and fault-recovery evidence |
| F: release package | Publish source, protocol, measurements and paper | Independent artifact verification/reproduction |

All candidate failures will remain in the optimization matrix, including conversion errors and unsupported operators. The analysis will report quality-resource Pareto frontiers without cherry-picking only successful models. Repeated comparisons across precision, data size and hardware will be identified as a family; confirmatory hypotheses and exploratory slices will be distinguished.

The planned reproduction record contains artifact hashes, source revisions, build commands, calibration/test splits, preprocessing, device identity, measurement scripts, trial order, seeds, thermal/power conditions and raw aggregate observations. Energy measurement precision and baseline subtraction will be stated. Estimated energy from a software counter will not be presented as an external-meter measurement.

The strongest validity risks are narrow hardware coverage, nonrepresentative calibration data and delayed or unavailable deployment labels. The first study will therefore make claims only for the tested release tuples and workload distributions. A successful classifier experiment will not validate language generation on a microcontroller, and a core simulator pass will not be labeled physical-device certification.

## 7. References and expected contribution

Primary sources consulted October 7, 2026. The methods below motivate candidate optimizations and measurement practice. Published speedups or accuracy results from those papers are not predictions for this project.

1. SCADS 2026 Problem Book, Project 9, p. 12. User-supplied research brief.
2. [Banbury et al. (2021). MLPerf Tiny Benchmark. NeurIPS Datasets and Benchmarks.](https://arxiv.org/abs/2106.07597)
3. [Xiao et al. (2023). SmoothQuant: Accurate and Efficient Post-Training Quantization for Large Language Models. ICML.](https://arxiv.org/abs/2211.10438)
4. [Hinton, Vinyals and Dean (2015). Distilling the Knowledge in a Neural Network.](https://arxiv.org/abs/1503.02531)
5. [Gebru et al. (2021). Datasheets for Datasets. Communications of the ACM.](https://arxiv.org/abs/1803.09010)

### Expected research artifact

The planned contribution is a documented path from a core experiment to a defensible device release decision: versioned artifact contracts, paired quality/resource gates, a study of calibration-data requirements and a monitor whose overhead and detection behavior are measured. Negative findings, such as a core metric that fails to predict thermal tail latency, would be valuable evidence about the limits of the pipeline.

A future public interface will let readers inspect the release tuple, compare candidate tradeoffs and replay an authored update/rollback scenario. Until implementation begins, the repository and website expose the projected architecture and roadmap. The present paper contains no trained student, quantized artifact, qualified runtime or measured edge result.

> Current status: Not started. This is an independently authored research proposal, with no implementation or empirical completion claim.

