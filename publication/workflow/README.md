# Project workflow

One chronological stream interleaves the projects and the collection's publication. Each milestone pairs its purpose and recorded outcome with a labeled excerpt of the user's prompt. Concurrent project sessions can overlap; chronological order alone does not imply a dependency.

`workflow.json` is the editable Workflow Display source. Its standalone HTML presents the same paired explanations and prompts. The `projects-*.json` files contain the curated chronology used to assemble that source.

## Reading the record

- Stored timestamps use UTC. Display dates and times use `America/Los_Angeles`, including daylight-saving rules. Some October 7 UTC sessions began October 6 locally.
- Most start and completion times describe recorded chat-turn windows. The collection-publication record ends at verified deployment, as its label states. A quoted reply may occur later within its window. Duration is elapsed session time, not active human effort; overlapping sessions must not be added into a work-hours claim.
- Prompt excerpts preserve the user's words, including original spelling. Excerpts from multiple messages are labeled accordingly. Context and outcome summaries are editorial paraphrases, not additional quotations.
- Outcomes summarize historical final responses. Reported test totals belong to individual iterations and are not cumulative. They are not new test runs or guarantees about the current published feature set; later milestones can extend beyond the frozen source and paper snapshots.
- Projects 06–09 appear jointly in the collection-publication record as research proposals with plans and roadmaps. Their implementation had not begun; publication does not imply implementation completion.

Public data excludes conversation identifiers, machine paths, tool commands, reasoning traces, credentials, and runtime logs. Source identifiers used for local verification are kept outside this publication directory.

## Display contract

Use one plan, with milestones ordered by their recorded start times. Keep each explanation beside its prompt artifact, or immediately above it on narrow screens. Dependencies are optional and must reflect supported relationships rather than simple adjacency. Preserve keyboard controls, readable long prompts, and reduced-motion behavior.

The standalone source follows the Workflow Display schema: root `title`, `description`, and `plans`; each step has an `id`, `title`, `description`, and `artifact`. Timing and excerpt labels appear as readable text in supported fields; internal curation metadata is not passed as extra schema fields.

## Rebuild

Requires Node.js 18 or later. From the repository root:

```sh
node publication/workflow/build.mjs
```

This validates the curated records and generates `events.json`, `workflow.json`, and the self-contained `workflow.html`. Optional `--site /path/to/website` copies the two display files into an existing website checkout. Open `workflow.html` in a browser; it works without a server or account.

The bundled renderer is the MIT-licensed [Workflow Display skill](https://github.com/BoomerRawlings/Skills/tree/main/skills/workflow-display). The builder applies this portfolio's palette and prompt/session terminology. The website uses a scoped integration of the same paired display.
