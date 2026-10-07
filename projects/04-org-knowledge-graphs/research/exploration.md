# Exploration track: evidence and build recommendation

Research checked 2026-10-06. Recommendations and performance targets below are proposals, not measured results. No implementation performed.

## Recommendation

Build a searchable, virtualized hierarchy sidebar, a bounded graph context view, and an evidence/editor panel. Use React/TypeScript, TanStack Virtual, Sigma.js/Graphology, and D3's tree layout; serve paged graph projections through Python/FastAPI and SQLite. Keep full-corpus inference and indexing outside the browser. Validate the renderer with a short spike before committing to richer styling.

The core contribution should be **usable navigation and correction under uncertainty at scale**. Semantic zoom alone is established prior art. GraphMaps already combines stable geometry, zoom-dependent layers, viewport filtering, and a bound on displayed entities. Its design directly supports this project's separation between corpus size and visible scene size. [GraphMaps, 2015](https://www.microsoft.com/en-us/research/publication/graphmaps-browsing-large-graphs-interactive-maps/)

## What the “10,000-node limit” actually means

Do not present it as a universal technical limit. Bloom documents a configurable **per-query** node limit of 100–10,000; selective expansion and grouping are supported. This describes a viewer's retrieval/display policy, not the graph database's maximum capacity. [Bloom settings](https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/settings-drawer/), [scene interactions](https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/bloom-scene-interactions/)

Separate five bottlenecks: database query cost, payload/parsing/memory, layout, rendering, and human comprehension. Node count alone ignores edges, label density, style, display resolution, and hardware. Cytoscape explicitly identifies edges, rich styles, and pixel ratio as performance factors. [Cytoscape performance](https://js.cytoscape.org/#performance)

Large-graph work predates this project: Carina explored million-node graphs without retaining the full graph in RAM. A May 2026 MSAGLJS preprint describes browser tile pyramids and routing with a benchmark suite up to 32,768 nodes/236,978 edges. These establish precedents, **not guarantees for this application's hardware or editing workload**. The newer paper is a preprint; do not mistake its workload size for an interactive FPS result. [Carina, 2017](https://arxiv.org/abs/1702.07099), [MSAGLJS, 2026](https://arxiv.org/abs/2605.17498)

## Renderer decision

| Candidate | Relevant capability | Project decision |
|---|---|---|
| Sigma.js + Graphology | WebGL graph rendering; graph model supports directed and parallel edges; labels use separate Canvas layers. | Default for bounded context/relationship view. Supply hierarchy coordinates; build evidence/editor controls in HTML. |
| Cytoscape.js | Graph interaction, styling, layouts; official January 2025 WebGL preview reports style limitations, including missing dashed edges in that preview. | Comparator if rich diagram interactions outweigh scale. Verify the pinned release's renderer support; do not assume all Canvas styling works in WebGL. |
| PixiJS | General 2D rendering, WebGL/WebGPU, culling and flexible graphics. | Defer. Would require building graph interaction/layout integration. Consider only if Sigma cannot satisfy a demonstrated design requirement. |

Sources: [Sigma introduction](https://www.sigmajs.org/docs/), [layers](https://www.sigmajs.org/docs/advanced/layers/), [Graphology](https://graphology.github.io/), [Cytoscape WebGL preview](https://blog.js.cytoscape.org/2025/01/13/webgl-preview/), [Pixi application](https://pixijs.com/8.x/guides/components/application). Sigma's documentation currently labels v4 alpha: pin a stable release and record versions in benchmarks. Pixi's maintainers explicitly caution that WebGPU does not automatically outperform WebGL; CPU work can dominate. [Pixi v8 launch](https://pixijs.com/blog/pixi-v8-launches)

Spike: same fixed coordinates, viewport, labels, uncertainty indicators, and interaction script; compare Sigma with Cytoscape at 500/2,000/5,000 visible nodes. Include edge picking, alternate parents, and selected labels. Choose by task fidelity and measured latency/memory, not headline node counts. Do not implement three production renderers.

Use D3 tidy-tree layout for a selected primary reporting forest; its implementation uses a linear-time tree algorithm. It cannot directly lay out arbitrary multiple-parent graphs. Keep alternate reporting/influence edges as overlays. Consider ELK only for bounded matrix-reporting views needing directional routing; its worker support avoids blocking the UI but does not eliminate layout cost. [D3 tree](https://d3js.org/d3-hierarchy/tree), [ELK.js](https://github.com/kieler/elkjs)

## Interaction and level of detail

- **Find:** search names, aliases, role, team, dates, review status. Results show disambiguating metadata and a direct route into context.
- **Navigate:** ancestor breadcrumb; one-level children; direct reports; jump to manager; explicit expand/collapse. Paginate very broad teams and long ancestry paths.
- **Zoom:** overview shows labeled teams/subtrees and counts; closer views reveal people; details appear only for selected/nearby entities. Preserve selected entities and stable positions across updates.
- **Compare:** keep formal reporting, inferred team membership, and communication/influence layers independently selectable. A communication community is not automatically a formal department.
- **Investigate:** show alternative managers, unresolved identities, and unknown parent groups. Never force every person into a seemingly complete tree.

Start with a proposed budget of 500 visible nodes/1,000 edges and at most 100 labels; allow experimentally validated expansion to 2,000 nodes. These are engineering hypotheses. Budget exhaustion produces an explicit aggregate/count or pagination control, never silent disappearance. Display “500 of 37,000 people; 42 relationships hidden by filters.” Keep collapse, confidence filtering, missing data, and access restrictions semantically distinct.

The sidebar flattens only expanded branches into a virtual list. TanStack Virtual mounts the visible window; it does not implement hierarchy semantics or accessibility for us. Stable entity keys preserve selection and scrolling. Never render or flatten all million nodes on each keystroke. [TanStack Virtual](https://tanstack.com/virtual/latest/docs/introduction)

API responses should include graph revision, time window, node/edge totals, returned counts, truncation reasons, and cursors. Index parent/child lookups, entity search, and effective dates. Cache bounded subtrees; precompute counts and overview aggregates. Cancel stale requests and reject responses from an obsolete snapshot. Loading evidence bodies is a separate action from loading graph metadata.

## Uncertainty, time, and analyst corrections

Show separate fields for **relationship type**, **model estimate/calibration applicability**, **evidence provenance**, and **review status**. Example: “Reports to; estimated probability 0.78; calibration evaluated on source corpus; unreviewed.” For transfer data lacking supporting calibration evidence, label the estimate accordingly instead of implying a guaranteed probability. Analyst confirmation never silently changes the model score to 1.0.

Use a persistent legend, explicit status badges, and numeric detail. Do not rely solely on opacity or color: uncertain edges may become invisible, and combined visual encodings can interfere. A graph-edge experiment found encoding effectiveness depends on both the paired visual variables and task. [Guo et al., 2015](https://ieeexplore.ieee.org/document/7089294/), [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)

Do not call an average edge score “team confidence,” or multiply marginal edge probabilities into path confidence without a justified joint model. Summaries may report counts of reviewed/unreviewed/conflicting edges and score distributions, clearly labeled. NetHOPs provides precedent for sampled network uncertainty, but animation is a later experiment requiring a valid joint graph distribution; independent edge samples could violate reporting constraints. [NetHOPs, 2021](https://arxiv.org/abs/2108.09870)

Every edge needs effective dates, evidence dates, run/model ID, source references, and review history. Let users select an “as of” date and compare snapshots with added/removed/changed relationships. Distinguish when a relationship held from when the system learned it. Keep time and filters visible in exports.

Edits use a form, not drag-only reparenting: select relationship/date, inspect consequences, save an auditable revision, support undo. Store append-only assertions with actor, reason, evidence, prior revision, and effective interval. Detect concurrent edits, self-reporting, cycles, and forbidden simultaneous parents; matrix relationships have a separate type. Preserve conflicting assertions for adjudication. Model refreshes cannot overwrite analyst decisions. Corrections export as a review dataset, not automatic ground truth or automatic retraining. W3C PROV supplies useful entity/activity/agent and derivation concepts without requiring an RDF stack. [PROV overview](https://www.w3.org/TR/prov-overview/)

## Accessibility and evaluation

Provide a keyboard-operable sidebar and paginated semantic table with the same search, evidence, and editing functions. A canvas cannot be the sole interaction surface. Follow tree keyboard behavior; dynamically loaded/virtualized items need correct `aria-level`, `aria-setsize`, and `aria-posinset`. Keep focus mounted, announce loading/results, and test screen readers manually. Prefer native table semantics for the alternative view. [W3C tree pattern](https://www.w3.org/WAI/ARIA/apg/patterns/treeview/), [table pattern](https://www.w3.org/WAI/ARIA/apg/patterns/table/)

| Logical graph | Test purpose | Visible scene |
|---|---|---|
| 10,000 people | End-to-end baseline; compare full load with paged approach | 100/500/2,000 nodes |
| 100,000 people | Search/indexing, wide/deep hierarchies, cache pressure | Same fixed budgets |
| 1,000,000 people | Stretch test of paging and bounded browser memory | Same fixed budgets; no full browser load |

Synthetic fixtures should include forests, deep chains, broad teams, disconnected identities, conflicting parents, reorganizations, and optional dense influence edges. Synthetic scale proves system behavior, not inferred hierarchy accuracy.

Proposed baseline: a documented 16-GB laptop with integrated graphics, 1080p viewport, DPR 1 and 2; repeat on another browser and lower-memory device. Record exact CPU/GPU/OS/browser, versions, edge counts, cache state, and network shaping. Aspirational acceptance: p95 local interactions ≤100 ms; p95 paged expansion ≤500 ms; first useful view ≤2 s; pan/zoom p95 frame time ≤33 ms; bounded memory under repeated navigation. Measure heap/process memory, payload size, layout time, cold/warm queries, dropped frames, and failures. No target is currently demonstrated.

Finally test analysts on finding a manager, explaining an uncertain edge, locating a disconnected employee, correcting a dated reporting line, and detecting disagreement. Compare completion accuracy/time and unjustified trust against a simple tree/table baseline. Reduced latency alone cannot establish interpretability or analytic trust.
