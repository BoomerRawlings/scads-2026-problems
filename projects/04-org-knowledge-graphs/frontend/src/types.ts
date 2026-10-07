export type Metrics = {
  breadth?: number;
  sent?: number;
  received?: number;
  cross_unit?: number;
};
export type Entity = {
  id: string;
  name: string;
  type: string;
  email?: string;
  aliases?: string[];
  role?: string;
  unit_id?: string;
  status?: string;
  manager_id?: string | null;
  manager_name?: string | null;
  children_count?: number;
  metrics?: Metrics;
};
export type Evidence = {
  id: string;
  kind: string;
  source_ref: string;
  text?: string;
  available: boolean;
  details?: Record<string, unknown>;
  message_ids?: string[];
};
export type Assertion = {
  id: string;
  subject: string;
  object: string;
  object_name?: string;
  subject_name?: string;
  relation: string;
  origin: string;
  reporting_type?: string;
  raw_score: number | null;
  candidate_probability?: number | null;
  selected_probability?: number | null;
  calibration_status: string;
  review_status: string;
  evidence_ids: string[];
  evidence?: Evidence[];
  selected?: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
  reason?: string;
};
export type Review = {
  id?: string;
  event_id?: string;
  action: string;
  subject?: string;
  object?: string;
  reason?: string;
  created_at?: string;
  assertion_id?: string;
  undone?: boolean;
  [key: string]: unknown;
};
export type Workspace = {
  corpus: {
    id: string;
    name: string;
    synthetic: boolean;
    description?: string;
  } | null;
  active_snapshot: string | null;
  revision: number;
  counts: {
    entities: number;
    people: number;
    assertions: number;
    selected: number;
    unresolved: number;
    reviewed: number;
    groups: number;
  };
  snapshots: {
    id: string;
    created_at: string;
    reason: string;
    as_of: string | null;
    revision: number;
  }[];
  model?: {
    name?: string;
    id?: string;
    calibration_status?: string;
    [key: string]: unknown;
  } | null;
  capabilities?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
  jobs?: Record<string, unknown>[];
};
export type Page = {
  items: Entity[];
  total: number;
  offset: number;
  limit: number;
  snapshot?: string;
};
export type Detail = {
  entity: Entity;
  manager: Assertion | null;
  alternatives: Assertion[];
  evidence: Evidence[];
  ancestors: Entity[];
  children: Entity[];
  history: Review[];
  metrics: Metrics;
  unresolved_reason?: string | null;
  snapshot: string;
  revision: number;
};
export type GraphNode = Entity & { depth?: number };
export type Graph = {
  nodes: GraphNode[];
  edges: {
    id: string;
    source: string;
    target: string;
    origin: string;
    review_status: string;
    raw_score: number | null;
    calibration_status: string;
  }[];
  total_nodes: number;
  returned_nodes: number;
  omitted_nodes: number;
  snapshot?: string;
};
export type Group = {
  id: string;
  name: string;
  kind: string;
  members: string[];
  member_names?: Record<string, string>;
  [key: string]: unknown;
};
export type Comparison = {
  before: string;
  after: string;
  changes: {
    subject: string;
    subject_name: string;
    kind: string;
    before: unknown;
    after: unknown;
  }[];
  total: number;
};
export type ImportReport = {
  read: number;
  accepted: number;
  duplicate: number;
  quarantined: number;
  unsupported: number;
  issues: unknown[];
};
