# A model is not ready until the device is

**Status: Not started.** Projected solution and research plan; implementation and evaluation have not begun.

A projected validation and monitoring pipeline for resource-constrained deployment.

[Project overview](https://boomerrawlings.com/work/scads-2026/09-core-to-edge/) · [Research proposal PDF](https://boomerrawlings.com/documents/scads-2026/09-core-to-edge.pdf) · [Full proposal](PROPOSAL.md) · [Roadmap](ROADMAP.md) · [All projects](../../README.md)

A model that meets quality targets in a development environment can fail after quantization, runtime conversion or deployment to a constrained device. This proposal specifies a core-to-edge validation pipeline that treats the deployable artifact, runtime and hardware profile as a single versioned unit. It will compare optimized models with a frozen reference, evaluate quality and resource gates, and monitor deployed behavior within a bounded overhead budget. [1]

This directory contains the proposed architecture, hypotheses, methodology, evaluation design, references and implementation roadmap. It contains no runnable implementation or demo. Numeric targets are projected study choices, not observed results.

Planned independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission.
