# A model is not ready until the device is

A projected validation and monitoring pipeline for resource-constrained deployment

**Status: Not started. Projected solution and research plan. Implementation and evaluation have not begun.**

Boomer Rawlings | Independent individual portfolio work | October 7, 2026

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

