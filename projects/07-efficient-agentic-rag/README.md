# Retrieval only when it earns its cost

**Status: Not started.** Projected solution and research plan; implementation and evaluation have not begun.

A projected study of adaptive multilingual RAG and evidence-aware evaluation.

[Project overview](https://boomerrawlings.com/work/scads-2026/07-efficient-agentic-rag/) · [Research proposal PDF](https://boomerrawlings.com/documents/scads-2026/07-efficient-agentic-rag.pdf) · [Full proposal](PROPOSAL.md) · [Roadmap](ROADMAP.md) · [All projects](../../README.md)

Retrieval-augmented generation must balance evidence quality against retrieval, reasoning and translation cost. This proposal studies a compact controller that chooses among no retrieval, single-pass retrieval and bounded iterative retrieval, with multilingual query expansion when the available evidence warrants it. The projected evaluation separates the contribution of adaptive retrieval from the contribution of an improved automatic judge. Both are measured against frozen, non-adaptive baselines. [1]

This directory contains the proposed architecture, hypotheses, methodology, evaluation design, references and implementation roadmap. It contains no runnable implementation or demo. Numeric targets are projected study choices, not observed results.

Planned independently by Boomer Rawlings after the original submission and grading dates, as individual portfolio work rather than a group submission.
