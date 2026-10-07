import type { IntakeJob, IntakePlan } from "./intakeTypes";

export const JOURNEY_DURATIONS = [4400, 5200, 8600, 4400, 5200, 3600];
export type JourneyPhase = "prepare" | "build";

export function journeyPhase(job: IntakeJob | null): JourneyPhase {
  return job?.status === "building" || job?.status === "ready" ||
    job?.stages.some((stage) => ["database", "infer", "ready"].includes(stage.id) && stage.status !== "queued")
    ? "build" : "prepare";
}

/** Only narrate facts from stages that actually started. */
export function journeyCeiling(job: IntakeJob | null): number {
  if (!job) return 0;
  let ceiling = 0;
  for (let index = 0; index < job.stages.length; index += 1) {
    if (job.stages[index].status !== "queued") ceiling = index;
  }
  return Math.min(5, ceiling);
}

export function advanceJourney(index: number, elapsed: number, delta: number, ceiling: number) {
  const duration = JOURNEY_DURATIONS[index] ?? JOURNEY_DURATIONS[0];
  const nextElapsed = Math.min(duration, elapsed + Math.max(0, delta));
  if (nextElapsed >= duration && index < ceiling) {
    return { index: index + 1, elapsed: 0 };
  }
  return { index, elapsed: nextElapsed };
}

/** Prefer connected records, with no invented endpoints or edges. */
export function journeySample(plan: IntakePlan | null) {
  if (!plan) return { nodes: [], edges: [] };
  const originals = new Map(plan.nodes.map((node) => [node.id, node]));
  const ids = new Set<string>();
  for (const edge of plan.edges) {
    if (!originals.has(edge.source) || !originals.has(edge.target)) continue;
    const additions = [edge.source, edge.target].filter((id, index, values) => !ids.has(id) && values.indexOf(id) === index);
    if (ids.size + additions.length <= 12) additions.forEach((id) => ids.add(id));
  }
  for (const node of plan.nodes) {
    if (ids.size >= 12) break;
    ids.add(node.id);
  }
  const nodes = [...ids].map((id, index, values) => {
    const angle = -Math.PI / 2 + index / values.length * Math.PI * 2;
    return {
      ...originals.get(id)!,
      x: values.length === 1 ? 300 : 300 + 226 * Math.cos(angle),
      y: values.length === 1 ? 164 : 164 + 126 * Math.sin(angle),
    };
  });
  return {
    nodes,
    edges: plan.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).slice(0, 16),
  };
}

export function journeyServerStatus(job: IntakeJob | null, preparing: boolean): string {
  if (!job) return preparing ? "Inspecting the source…" : "Ready to inspect · nothing saved";
  if (job.status === "ready_for_review") return "Preview ready · nothing saved";
  if (job.status === "ready") return "Workspace ready";
  if (job.status === "failed") return "Needs attention · see recovery below";
  if (job.status === "cancelled") return "Preview cancelled · choose another source";
  const active = job.stages.find((stage) => stage.status === "running");
  return active ? `${active.label}…` : job.status === "building" ? "Building the workspace…" : "Inspecting the source…";
}
