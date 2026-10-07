import type { IntakeJob, IntakeStage, IntakeStageId } from "./intakeTypes";

export const MAX_INTAKE_BYTES = 100 * 1024 * 1024;
export const MIN_SYNTHETIC_PEOPLE = 72;
export const MAX_SYNTHETIC_PEOPLE = 100_000;

export const INTAKE_STAGES: {
  id: IntakeStageId;
  label: string;
  explanation: string;
}[] = [
  {
    id: "inspect",
    label: "Inspect source",
    explanation:
      "Read the source format and size. Synthetic records are generated here; imported files are parsed in memory.",
  },
  {
    id: "profile",
    label: "Understand the data",
    explanation:
      "Count people, messages, relationships and available fields. Identify missing information and records that cannot be used.",
  },
  {
    id: "plan",
    label: "Draw the graph plan",
    explanation:
      "Preview a bounded sample of source entities and relationships, before any source records enter the database.",
  },
  {
    id: "database",
    label: "Build the workspace",
    explanation:
      "After you review the profile, save accepted records and their provenance to the workspace.",
  },
  {
    id: "infer",
    label: "Connect the evidence",
    explanation:
      "Use available communication and structural signals to propose reporting links. Missing evidence remains explicit; scores are uncalibrated.",
  },
  {
    id: "ready",
    label: "Explore the organization",
    explanation:
      "Open the chart, zoom into individual positions, inspect supporting evidence and record corrections.",
  },
];

export function formatBytes(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value))
    return "Measured during inspection";
  if (value < 1024) return `${Math.max(0, value).toLocaleString()} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function validatePeople(value: string): string | null {
  const count = Number(value);
  return !value.trim() ||
    !Number.isInteger(count) ||
    count < MIN_SYNTHETIC_PEOPLE ||
    count > MAX_SYNTHETIC_PEOPLE
    ? "Choose a whole number from 72 to 100,000 people."
    : null;
}

export function initialStages(): IntakeStage[] {
  return INTAKE_STAGES.map(({ id, label }) => ({
    id,
    label,
    status: "queued",
    detail: "",
  }));
}

export function activeStage(job: IntakeJob | null): IntakeStageId {
  if (!job) return "inspect";
  if (job.status === "ready_for_review") return "plan";
  const active = job.stages.find(
    (stage) => stage.status === "running" || stage.status === "error",
  );
  if (active) return active.id;
  if (job.status === "building") {
    const pending = job.stages.find(
      (stage) =>
        stage.status === "queued" &&
        ["database", "infer", "ready"].includes(stage.id),
    );
    if (pending) return pending.id;
  }
  return (
    [...job.stages].reverse().find((stage) => stage.status === "complete")
      ?.id ?? "inspect"
  );
}

export function completedStages(
  stages: IntakeStage[],
  phase: "all" | "prepare" | "build" = "all",
): IntakeStageId[] {
  return stages
    .filter(
      (stage) => stage.status === "complete" || stage.status === "skipped",
    )
    .filter(
      (stage) =>
        phase === "all" ||
        ["inspect", "profile", "plan"].includes(stage.id) ===
          (phase === "prepare"),
    )
    .map((stage) => stage.id);
}

export function fieldCoverage(present: number, total: number): number {
  return total > 0 ? Math.max(0, Math.min(100, (present / total) * 100)) : 0;
}

export function sourceOrigin(origin?: string): string {
  if (origin === "model") return "Imported model proposal";
  if (origin === "analyst") return "Analyst assertion";
  if (origin === "message") return "Communication record";
  if (!origin || origin === "source") return "Supplied source record";
  return `Imported ${origin.replaceAll("_", " ")} record`;
}

/** A small source sample only; no inferred layout or authority is manufactured. */
export function planPositions(nodes: { id: string; kind: string }[]) {
  const visible = nodes.slice(0, 18);
  const columns = Math.min(3, Math.max(1, visible.length));
  return visible.map((node, index) => ({
    ...node,
    x: 26 + (index % columns) * 210,
    y: 26 + Math.floor(index / columns) * 102,
  }));
}
