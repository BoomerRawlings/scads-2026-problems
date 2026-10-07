import type { Workspace } from "./types";

export type IntakeMode = "import" | "synthetic";
export type IntakeStageId =
  | "inspect"
  | "profile"
  | "plan"
  | "database"
  | "infer"
  | "ready";
export type IntakeStage = {
  id: IntakeStageId;
  label: string;
  status: "queued" | "running" | "complete" | "skipped" | "error";
  detail: string;
  started_at?: string;
  finished_at?: string;
};
export type IntakeProfile = {
  counts: {
    entities: number;
    people: number;
    units: number;
    shared_mailboxes: number;
    messages: number;
    assertions: number;
    evidence: number;
    labels: number;
    data_points: number;
    communication_links: number;
  };
  fields: {
    id: string;
    label: string;
    present: number;
    missing: number;
    total: number;
  }[];
  relations: { relation: string; count: number }[];
  quality: {
    read: number;
    accepted: number;
    duplicate: number;
    quarantined: number;
    unsupported: number;
    issues: { code: string; reason: string }[];
    issue_count: number;
  };
  notes: string[];
  timestamp_start: string | null;
  timestamp_end: string | null;
};
export type IntakePlan = {
  nodes: { id: string; label: string; kind: string }[];
  edges: {
    source: string;
    target: string;
    relation: string;
    origin?: string;
  }[];
  sampled: boolean;
  sample_nodes: number;
  total_nodes: number;
  sample_edges: number;
  total_source_relations: number;
  note: string;
};
export type IntakeJob = {
  id: string;
  mode: IntakeMode;
  status:
    | "profiling"
    | "ready_for_review"
    | "building"
    | "ready"
    | "failed"
    | "cancelled";
  stages: IntakeStage[];
  source: {
    name: string;
    format: string;
    bytes: number | null;
    requested_people?: number;
  };
  profile: IntakeProfile | null;
  plan: IntakePlan | null;
  workspace: {
    base_revision: number;
    occupied: boolean;
    same_dataset: boolean;
    requires_replacement: boolean;
    can_reuse: boolean;
    package_requires_empty: boolean;
  };
  result: Workspace | null;
  error: string | null;
  retryable: boolean;
};
