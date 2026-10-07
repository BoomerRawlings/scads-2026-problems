import { describe, expect, it } from "vitest";
import {
  activeStage,
  completedStages,
  fieldCoverage,
  formatBytes,
  initialStages,
  MAX_INTAKE_BYTES,
  planPositions,
  validatePeople,
} from "./intakeModel";
import type { IntakeJob } from "./intakeTypes";

describe("intake source validation", () => {
  it("accepts the generator bounds and rejects fractional, empty and nonfinite sizes", () => {
    for (const valid of ["72", "10000", "100000"])
      expect(validatePeople(valid)).toBeNull();
    for (const invalid of [
      "",
      " ",
      "71",
      "100001",
      "72.5",
      "Infinity",
      "people",
    ])
      expect(validatePeople(invalid)).toBeTruthy();
  });
  it("matches the 100 MiB upload boundary and distinguishes measured zero from unknown", () => {
    expect(MAX_INTAKE_BYTES).toBe(104857600);
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(null)).toBe("Measured during inspection");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(MAX_INTAKE_BYTES)).toBe("100.0 MB");
  });
});

describe("truthful stage presentation", () => {
  it("replays each completed phase without inventing unfinished build work", () => {
    const stages = initialStages();
    for (const stage of stages.slice(0, 4)) stage.status = "complete";
    expect(completedStages(stages, "prepare")).toEqual([
      "inspect",
      "profile",
      "plan",
    ]);
    expect(completedStages(stages, "build")).toEqual(["database"]);
    stages[4].status = "skipped";
    stages[5].status = "complete";
    expect(completedStages(stages, "build")).toEqual([
      "database",
      "infer",
      "ready",
    ]);
    expect(completedStages(stages)).toHaveLength(6);
  });
  it("starts with all stages queued, and never replays unperformed work", () => {
    const stages = initialStages();
    expect(stages).toHaveLength(6);
    expect(stages.every((stage) => stage.status === "queued")).toBe(true);
    expect(completedStages(stages)).toEqual([]);
    stages[0].status = "complete";
    stages[1].status = "running";
    expect(completedStages(stages)).toEqual(["inspect"]);
  });
  it("highlights the review checkpoint without claiming database work has started", () => {
    const stages = initialStages();
    for (const stage of stages.slice(0, 3)) stage.status = "complete";
    const job = { status: "ready_for_review", stages } as IntakeJob;
    expect(activeStage(job)).toBe("plan");
    expect(completedStages(stages)).toEqual(["inspect", "profile", "plan"]);
    expect(stages[3].status).toBe("queued");
    job.status = "building";
    expect(activeStage(job)).toBe("database");
    expect(stages[3].status).toBe("queued");
  });
  it("selects the actual failed/running stage, including a skipped inference on reuse", () => {
    const stages = initialStages();
    stages[3].status = "error";
    expect(activeStage({ status: "failed", stages } as IntakeJob)).toBe(
      "database",
    );
    stages[3].status = "complete";
    stages[4].status = "skipped";
    stages[5].status = "running";
    expect(activeStage({ status: "building", stages } as IntakeJob)).toBe(
      "ready",
    );
    expect(completedStages(stages)).toEqual(["database", "infer"]);
  });
});

describe("bounded source preview", () => {
  it("retains source identity while bounding diagram nodes", () => {
    const nodes = Array.from({ length: 10000 }, (_, index) => ({
      id: `person-${index}`,
      kind: "person",
    }));
    const positions = planPositions(nodes);
    expect(positions).toHaveLength(18);
    expect(positions.map((node) => node.id)).toEqual(
      nodes.slice(0, 18).map((node) => node.id),
    );
    expect(new Set(positions.map((node) => `${node.x}:${node.y}`)).size).toBe(
      18,
    );
    expect(planPositions([])).toEqual([]);
  });
  it("has finite, bounded coverage with absent fields and empty datasets", () => {
    expect(fieldCoverage(0, 0)).toBe(0);
    expect(fieldCoverage(2, 8)).toBe(25);
    expect(fieldCoverage(10, 8)).toBe(100);
    expect(fieldCoverage(-1, 8)).toBe(0);
  });
});
