import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  FileText,
  FolderUp,
  GitBranch,
  Layers3,
  Loader2,
  LocateFixed,
  Network,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Users,
} from "./icons";
import { api } from "./api";
import type { Workspace } from "./types";
import type {
  IntakeJob,
  IntakeMode,
  IntakePlan,
  IntakeProfile,
  IntakeStage,
  IntakeStageId,
} from "./intakeTypes";
import {
  activeStage,
  completedStages,
  fieldCoverage,
  formatBytes,
  initialStages,
  INTAKE_STAGES,
  MAX_INTAKE_BYTES,
  planPositions,
  sourceOrigin,
  validatePeople,
} from "./intakeModel";
import "./intake.css";

const number = (value: number) => value.toLocaleString();
const stageIcons = [FileText, Users, Network, Layers3, GitBranch, LocateFixed];
const stageNames = {
  queued: "Up next",
  running: "Working",
  complete: "Complete",
  skipped: "Not needed",
  error: "Needs attention",
};

async function discardPreview(id: string) {
  try {
    await api(`/intake/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch (cause) {
    // An expired in-memory preview already has no staged payload to release.
    if (
      !String((cause as Error).message || cause).includes(
        "Intake preview expired or was not found",
      )
    )
      throw cause;
  }
}

export function IntakeDiagram({
  stages,
  selected,
  onSelect,
  replay,
}: {
  stages: IntakeStage[];
  selected: IntakeStageId;
  onSelect: (id: IntakeStageId) => void;
  replay: IntakeStageId | null;
}) {
  const connectors = [
    "M310 80 H338",
    "M656 80 H680",
    "M834 151 V177",
    "M687 256 H659",
    "M343 256 H318",
  ];
  return (
    <div
      className="intake-flow-diagram"
      aria-label="Dataset processing workflow"
    >
      <svg
        className="intake-flow-lines"
        viewBox="0 0 1000 331"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <marker
            id="intake-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10z" />
          </marker>
        </defs>
        {connectors.map((path, index) => {
          const next = stages[index + 1];
          const moving = replay
            ? next?.id === replay
            : next?.status === "running";
          return (
            <path
              key={path}
              d={path}
              markerEnd="url(#intake-arrow)"
              className={
                moving
                  ? "is-moving"
                  : next?.status === "complete"
                    ? "is-complete"
                    : ""
              }
            />
          );
        })}
      </svg>
      <ol className="intake-stages">
        {INTAKE_STAGES.map((definition, index) => {
          const stage = stages.find((item) => item.id === definition.id) ?? {
            ...definition,
            status: "queued",
            detail: "",
          };
          const Icon = stageIcons[index];
          const spotlight = replay === stage.id;
          const working = !replay && stage.status === "running";
          return (
            <li key={stage.id}>
              <button
                type="button"
                className={`intake-stage ${stage.status} ${selected === stage.id ? "selected" : ""} ${spotlight ? "replaying" : ""}`}
                onClick={() => onSelect(stage.id)}
                aria-pressed={selected === stage.id}
                aria-label={`Step ${index + 1}: ${definition.label}, ${stageNames[stage.status]}`}
              >
                <span className="intake-stage-top">
                  <span className="intake-stage-icon">
                    <Icon size={21} strokeWidth={1.5} />
                  </span>
                  <span className="intake-step-number">0{index + 1}</span>
                </span>
                <strong>{definition.label}</strong>
                <span className="intake-stage-state">
                  {working ? (
                    <Loader2 size={12} className="intake-spin" />
                  ) : stage.status === "complete" ? (
                    <Check size={12} />
                  ) : (
                    <span className="intake-status-dot" />
                  )}
                  {spotlight ? "Walkthrough replay" : stageNames[stage.status]}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function GraphPlan({ plan }: { plan: IntakePlan }) {
  const positions = planPositions(plan.nodes);
  const byId = new Map(positions.map((node) => [node.id, node]));
  const edges = plan.edges.filter(
    (edge) => byId.has(edge.source) && byId.has(edge.target),
  );
  const height = Math.max(138, Math.ceil(positions.length / 3) * 102 + 26);
  return (
    <section className="intake-plan-card">
      <div className="intake-section-heading">
        <span>
          <span className="intake-eyebrow">Before the database</span>
          <h3>Source graph preview</h3>
        </span>
        <span className="intake-small-badge">Source relationships</span>
      </div>
      <p className="intake-muted">
        {plan.note ||
          "A bounded sample of the entities and relationships available in your source."}
      </p>
      {positions.length ? (
        <div className="intake-plan-scroll">
          <svg
            viewBox={`0 0 660 ${height}`}
            role="img"
            aria-label={`Source graph sample: ${positions.length} entities and ${edges.length} relationships`}
          >
            <defs>
              <marker
                id="intake-plan-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M0 0 L10 5 L0 10z" fill="#8aa593" />
              </marker>
            </defs>
            {edges.map((edge, index) => {
              const a = byId.get(edge.source)!,
                b = byId.get(edge.target)!;
              const x1 = a.x + 88,
                y1 = a.y + 62,
                x2 = b.x + 88,
                y2 = b.y;
              return (
                <path
                  key={`${edge.source}-${edge.target}-${index}`}
                  d={`M${x1} ${y1} C${x1} ${y1 + 28} ${x2} ${y2 - 28} ${x2} ${y2}`}
                  fill="none"
                  stroke="#a3b5a6"
                  strokeWidth="1.5"
                  strokeDasharray={edge.origin === "model" ? "5 4" : undefined}
                  markerEnd="url(#intake-plan-arrow)"
                >
                  <title>
                    {edge.relation.replaceAll("_", " ")} ·{" "}
                    {sourceOrigin(edge.origin)}
                  </title>
                </path>
              );
            })}
            {positions.map((node) => {
              const original = plan.nodes.find((item) => item.id === node.id)!;
              return (
                <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
                  <rect
                    width="176"
                    height="62"
                    rx="10"
                    fill={node.kind === "person" ? "#fffefa" : "#eaf0e5"}
                    stroke="#cbd7c7"
                  />
                  <text x="12" y="22" fontSize="10" fill="#687e6d">
                    {node.kind.replaceAll("_", " ").toUpperCase()}
                  </text>
                  <text x="12" y="43" fontSize="12" fill="#2b4435">
                    {original.label.length > 22
                      ? `${original.label.slice(0, 21)}…`
                      : original.label}
                  </text>
                  <title>
                    {original.label} · {node.kind}
                  </title>
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div className="intake-empty-plan">
          No usable entities were found in this source.
        </div>
      )}
      <div className="intake-plan-caption">
        Showing {number(positions.length)} of {number(plan.total_nodes)}{" "}
        entities · {number(edges.length)} sample relationships. New reporting
        inferences are added later.
      </div>
      {plan.edges.length > 0 && (
        <details className="intake-relations-detail">
          <summary>Read sample relationships</summary>
          <ul>
            {plan.edges.slice(0, 30).map((edge, index) => (
              <li key={index}>
                <strong>
                  {plan.nodes.find((node) => node.id === edge.source)?.label ||
                    edge.source}
                </strong>{" "}
                <span>{edge.relation.replaceAll("_", " ")}</span>{" "}
                <strong>
                  {plan.nodes.find((node) => node.id === edge.target)?.label ||
                    edge.target}
                </strong>
                <small> · {sourceOrigin(edge.origin)}</small>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function ProfileSummary({
  profile,
  bytes,
}: {
  profile: IntakeProfile;
  bytes: number | null;
}) {
  const counts = profile.counts;
  const metrics = [
    {
      label: "Individuals",
      value: number(counts.people),
      note: "Distinct person records",
    },
    {
      label: "Messages",
      value: number(counts.messages),
      note: "Communication records",
    },
    {
      label: "Data points",
      value: number(counts.data_points),
      note: "Accepted records across types",
    },
    {
      label: "Source size",
      value: formatBytes(bytes),
      note: "Measured source bytes",
    },
  ];
  return (
    <section className="intake-profile" aria-label="Dataset profile">
      <div className="intake-section-heading">
        <span>
          <span className="intake-eyebrow">Measured, before building</span>
          <h3>What’s in this dataset?</h3>
        </span>
        <span className="intake-small-badge">
          <Check size={12} /> Inspection complete
        </span>
      </div>
      <div className="intake-metrics">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.note}</small>
          </div>
        ))}
      </div>
      <div className="intake-record-breakdown">
        <span>
          <strong>{number(counts.units)}</strong> organizational units
        </span>
        <span>
          <strong>{number(counts.shared_mailboxes)}</strong> shared mailboxes
        </span>
        <span>
          <strong>{number(counts.assertions)}</strong> supplied assertions
        </span>
        <span>
          <strong>{number(counts.evidence)}</strong> evidence records
        </span>
        <span>
          <strong>{number(counts.communication_links)}</strong> communication
          links
        </span>
        <span>
          <strong>{number(counts.labels)}</strong> isolated evaluation labels
        </span>
      </div>
      <div className="intake-profile-columns">
        <div>
          <h4>Available information</h4>
          <div className="intake-fields">
            {profile.fields.map((field) => (
              <div className="intake-field" key={field.id}>
                <span>{field.label}</span>
                <strong>
                  {number(field.present)}
                  <small> / {number(field.total)}</small>
                </strong>
                <div
                  className="intake-field-meter"
                  role="meter"
                  aria-label={`${field.label} coverage`}
                  aria-valuemin={0}
                  aria-valuemax={field.total || 1}
                  aria-valuenow={field.present}
                >
                  <i
                    style={{
                      width: `${fieldCoverage(field.present, field.total)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="intake-quality">
          <h4>Source quality</h4>
          <dl>
            <div>
              <dt>Records read</dt>
              <dd>{number(profile.quality.read)}</dd>
            </div>
            <div>
              <dt>Accepted</dt>
              <dd>{number(profile.quality.accepted)}</dd>
            </div>
            <div>
              <dt>Duplicates</dt>
              <dd>{number(profile.quality.duplicate)}</dd>
            </div>
            <div>
              <dt>Quarantined</dt>
              <dd>{number(profile.quality.quarantined)}</dd>
            </div>
            <div>
              <dt>Unsupported</dt>
              <dd>{number(profile.quality.unsupported)}</dd>
            </div>
          </dl>
          {profile.timestamp_start && (
            <p>
              Communications: {profile.timestamp_start.slice(0, 10)}
              {profile.timestamp_end &&
                ` — ${profile.timestamp_end.slice(0, 10)}`}
            </p>
          )}
          {profile.quality.issue_count > 0 && (
            <details>
              <summary>
                {number(profile.quality.issue_count)} source issues
              </summary>
              <ul>
                {profile.quality.issues.slice(0, 15).map((issue, index) => (
                  <li key={index}>{issue.reason}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
      {profile.notes.length > 0 && (
        <div className="intake-profile-notes">
          <ShieldCheck size={16} />
          <ul>
            {profile.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function IntakeFlow({
  workspace,
  onComplete,
  initialMode = null,
}: {
  workspace: Workspace | null;
  onComplete: (workspace: Workspace) => void;
  initialMode?: IntakeMode | null;
}) {
  const [mode, setMode] = useState<IntakeMode | null>(initialMode);
  const [people, setPeople] = useState("10000");
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<IntakeJob | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState("");
  const [pollVersion, setPollVersion] = useState(0);
  const [replace, setReplace] = useState(false);
  const [selectedStage, setSelectedStage] = useState<IntakeStageId>("inspect");
  const [replayStage, setReplayStage] = useState<IntakeStageId | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const processRef = useRef<HTMLElement | null>(null);
  const generation = useRef(0);
  const replayTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busy =
    requesting || job?.status === "profiling" || job?.status === "building";
  const building = job?.status === "building";
  const ready = job?.status === "ready" && job.result;
  const review = job?.status === "ready_for_review";
  const canBuild = Boolean(
    review || (job?.status === "failed" && job.retryable && job.profile),
  );
  const stages =
    job?.stages ??
    initialStages().map((stage) =>
      requesting && stage.id === "inspect"
        ? {
            ...stage,
            status: "running" as const,
            detail: "Sending the source for inspection.",
          }
        : stage,
    );
  const selectedDefinition = INTAKE_STAGES.find(
    (stage) => stage.id === (replayStage ?? selectedStage),
  )!;
  const selectedDetail = stages.find(
    (stage) => stage.id === selectedDefinition.id,
  );
  const existing = Boolean(workspace?.corpus);

  useEffect(
    () => () => {
      generation.current += 1;
      requestRef.current?.abort();
      if (replayTimer.current) clearTimeout(replayTimer.current);
    },
    [],
  );

  useEffect(() => {
    if (job) setSelectedStage(activeStage(job));
  }, [
    job?.status,
    job?.stages.find((stage) => stage.status === "running")?.id,
  ]);

  useEffect(() => {
    // Fast processing can finish between polls. Replay only confirmed steps,
    // visibly labelled as playback; the review/build controls stay available.
    if (job?.status === "ready_for_review") replay("prepare");
    if (job?.status === "ready") replay("build");
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!job?.id || !["profiling", "building"].includes(job.status)) return;
    const controller = new AbortController();
    const currentGeneration = generation.current;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<IntakeJob>(
          `/intake/${encodeURIComponent(job.id)}`,
          { signal: controller.signal },
        );
        if (
          controller.signal.aborted ||
          generation.current !== currentGeneration
        )
          return;
        setJob(next);
        setError("");
        if (["profiling", "building"].includes(next.status))
          timer = setTimeout(poll, 650);
      } catch (cause) {
        if (
          !controller.signal.aborted &&
          generation.current === currentGeneration
        )
          setError(
            `Progress connection interrupted. ${String((cause as Error).message || cause)}`,
          );
      }
    };
    timer = setTimeout(poll, 450);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [job?.id, job?.status, pollVersion]);

  function stopReplay() {
    if (replayTimer.current) clearTimeout(replayTimer.current);
    replayTimer.current = null;
    setReplayStage(null);
  }

  function replay(phase: "all" | "prepare" | "build" = "all") {
    stopReplay();
    const completed = completedStages(stages, phase);
    let index = 0;
    function advance() {
      if (index >= completed.length) {
        setReplayStage(null);
        return;
      }
      setReplayStage(completed[index++]);
      replayTimer.current = setTimeout(advance, 1700);
    }
    advance();
  }

  function revealProcess() {
    processRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "start",
    });
  }

  async function inspect() {
    if (!mode || busy) return;
    const validation =
      mode === "synthetic"
        ? validatePeople(people)
        : !file
          ? "Choose a dataset to inspect."
          : file.size > MAX_INTAKE_BYTES
            ? "This intake accepts files up to 100 MB. Split the source into a smaller import."
            : null;
    if (validation) {
      setError(validation);
      return;
    }
    const currentGeneration = ++generation.current;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    stopReplay();
    setError("");
    setJob(null);
    setReplace(false);
    setSelectedStage("inspect");
    setRequesting(true);
    revealProcess();
    try {
      let result: IntakeJob;
      if (mode === "import") {
        const body = new FormData();
        body.set("file", file!);
        result = await api<IntakeJob>("/intake/import", {
          method: "POST",
          body,
          signal: controller.signal,
        });
      } else {
        result = await api<IntakeJob>("/intake/synthetic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ people: Number(people) }),
          signal: controller.signal,
        });
      }
      if (
        !controller.signal.aborted &&
        generation.current === currentGeneration
      )
        setJob(result);
    } catch (cause) {
      if (
        !controller.signal.aborted &&
        generation.current === currentGeneration
      )
        setError(String((cause as Error).message || cause));
    } finally {
      if (generation.current === currentGeneration) setRequesting(false);
    }
  }

  async function build() {
    if (
      !job ||
      !canBuild ||
      busy ||
      job.workspace.package_requires_empty ||
      (job.workspace.requires_replacement && !replace)
    )
      return;
    stopReplay();
    const currentGeneration = generation.current;
    const controller = new AbortController();
    requestRef.current = controller;
    setError("");
    setRequesting(true);
    setSelectedStage("database");
    revealProcess();
    try {
      const next = await api<IntakeJob>(
        `/intake/${encodeURIComponent(job.id)}/build`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            base_revision: job.workspace.base_revision,
            replace,
          }),
          signal: controller.signal,
        },
      );
      if (
        !controller.signal.aborted &&
        generation.current === currentGeneration
      )
        setJob(next);
    } catch (cause) {
      if (
        !controller.signal.aborted &&
        generation.current === currentGeneration
      ) {
        setError(String((cause as Error).message || cause));
        // A response can be lost after a successful start. Recover the actual
        // job, including a fresh revision after a conflict, before retrying.
        try {
          const refreshed = await api<IntakeJob>(
            `/intake/${encodeURIComponent(job.id)}`,
            { signal: controller.signal },
          );
          if (
            !controller.signal.aborted &&
            generation.current === currentGeneration
          ) {
            if (
              refreshed.workspace.base_revision !== job.workspace.base_revision
            )
              setReplace(false);
            setJob(refreshed);
            if (["building", "ready"].includes(refreshed.status)) setError("");
          }
        } catch {
          /* Retain the original error; another explicit retry can recover. */
        }
      }
    } finally {
      if (generation.current === currentGeneration) setRequesting(false);
    }
  }

  async function reset(nextMode: IntakeMode | null = null) {
    if (building || requesting) return;
    generation.current += 1;
    requestRef.current?.abort();
    stopReplay();
    if (
      job &&
      ["profiling", "ready_for_review", "failed"].includes(job.status)
    ) {
      try {
        await discardPreview(job.id);
      } catch (cause) {
        setError(String((cause as Error).message || cause));
        setPollVersion((value) => value + 1);
        return;
      }
    }
    setJob(null);
    setMode(nextMode);
    setError("");
    setReplace(false);
    setSelectedStage("inspect");
  }

  async function resume() {
    if (busy) return;
    stopReplay();
    setRequesting(true);
    try {
      if (job && ["ready_for_review", "failed"].includes(job.status)) {
        await discardPreview(job.id);
      }
      // A failed analysis may still have saved its source records. Read the
      // current workspace so the explorer cannot mix old and new snapshots.
      onComplete(await api<Workspace>("/workspace"));
    } catch (cause) {
      setError(String((cause as Error).message || cause));
      setRequesting(false);
    }
  }

  const statusLabel = requesting
    ? "Starting next step…"
    : replayStage
      ? "Walkthrough replay · no work is running"
      : ready
        ? "Your chart is ready"
        : review
          ? "Review before building"
          : job?.status === "failed"
            ? "This step needs attention"
            : busy
              ? (stages.find((stage) => stage.status === "running")?.label ??
                "Processing source…")
              : "A clear route from source to chart";
  const statusDetail = requesting
    ? "Waiting for the server to confirm the next step. The diagram will update with actual progress."
    : replayStage
      ? "Follow the completed steps again. This replay does not change your data."
      : ready
        ? "The source has been processed. Open the chart to explore positions, reporting links and evidence."
        : review
          ? "The profile and source graph are ready. No source records have been written to the database yet."
          : job?.status === "failed"
            ? (job.error ?? "Review the issue below and try again.")
            : busy
              ? (stages.find((stage) => stage.status === "running")?.detail ??
                "Progress below reflects work reported by the server.")
              : "Inspect the source, understand its scale, and draw a plan. Build only after you review it.";

  return (
    <div className="intake-page">
      <header className="intake-header">
        <div className="intake-brand">
          <span>
            <Network size={22} strokeWidth={1.6} />
          </span>
          <div>
            <strong>Organization Atlas</strong>
            <small>PROJECT 04 · DATA INTAKE</small>
          </div>
        </div>
        {existing && (
          <button
            type="button"
            className="intake-resume"
            onClick={() => void resume()}
            disabled={busy}
          >
            <span>Continue existing workspace</span>
            <ArrowRight size={15} />
          </button>
        )}
      </header>
      {!mode ? (
        <div className="intake-welcome">
          <span className="intake-eyebrow">Begin with understanding</span>
          <h1>Choose a dataset to explore.</h1>
          <p>
            Choose a source. We’ll measure its size, show what it contains, and
            draw the path from records to an organization chart.
          </p>
          {error && (
            <div className="intake-error" role="alert">
              <AlertCircle size={18} />
              <div>
                <strong>Couldn’t open the workspace.</strong>
                <p>{error}</p>
              </div>
            </div>
          )}
          <div className="intake-choices">
            <button
              type="button"
              className="intake-choice"
              disabled={busy}
              onClick={() => setMode("import")}
            >
              <span className="intake-choice-icon">
                <FolderUp size={29} strokeWidth={1.4} />
              </span>
              <span className="intake-choice-kicker">YOUR ORGANIZATION</span>
              <h2>Import a dataset</h2>
              <p>
                Bring a roster, communication archive, or an exported workspace.
                Inspect it before anything is built.
              </p>
              <span className="intake-choice-action">
                Choose your source <ArrowRight size={17} />
              </span>
              <small>JSON · CSV · EML · mbox</small>
            </button>
            <button
              type="button"
              className="intake-choice synthetic"
              disabled={busy}
              onClick={() => setMode("synthetic")}
            >
              <span className="intake-choice-icon">
                <Sparkles size={29} strokeWidth={1.4} />
              </span>
              <span className="intake-choice-kicker">EXPLORE THE PROCESS</span>
              <h2>View synthetic dataset</h2>
              <p>
                Generate a fictional organization and watch the same workflow
                turn people and messages into a navigable chart.
              </p>
              <span className="intake-choice-action">
                Create an example <ArrowRight size={17} />
              </span>
              <small>10,000 people by default · adjustable size</small>
            </button>
          </div>
          <div className="intake-welcome-foot">
            <ShieldCheck size={17} />
            <span>
              Source facts, inferred relationships and unknowns remain
              distinguishable at every step.
            </span>
          </div>
          {existing && (
            <p className="intake-existing-note">
              Existing workspace: <strong>{workspace!.corpus!.name}</strong> ·{" "}
              {number(workspace!.counts.people)} people. Your saved chart is
              available above.
            </p>
          )}
        </div>
      ) : (
        <div className="intake-content">
          <div className="intake-topline">
            <button
              type="button"
              onClick={() => void reset()}
              disabled={building || requesting}
            >
              <ArrowLeft size={14} /> Choose another source
            </button>
            <span className="intake-small-badge">
              {mode === "synthetic"
                ? "Fictional demonstration"
                : "Your dataset"}
            </span>
          </div>
          <div className="intake-title">
            <span className="intake-eyebrow">
              Follow the evidence, step by step
            </span>
            <h1>From dataset to organization chart</h1>
            <p>
              Size and coverage come first. A graph preview comes next. You
              decide when the workspace is built.
            </p>
          </div>
          <div className="intake-workbench">
            <aside className="intake-source-card">
              <span className="intake-eyebrow">01 / Source</span>
              <h2>
                {mode === "synthetic"
                  ? "A fictional organization"
                  : "Bring your dataset"}
              </h2>
              {!job ? (
                <>
                  {mode === "synthetic" ? (
                    <>
                      <p>
                        Deterministic people, teams, messages and reporting
                        clues. The same inputs reproduce the same source.
                      </p>
                      <label
                        className="intake-size-label"
                        htmlFor="intake-people"
                      >
                        People to generate
                      </label>
                      <input
                        id="intake-people"
                        className="intake-people-input"
                        type="number"
                        min="72"
                        max="100000"
                        step="1"
                        value={people}
                        disabled={busy}
                        onChange={(event) => {
                          setPeople(event.target.value);
                          setError("");
                        }}
                      />
                      <div className="intake-presets">
                        {[72, 1000, 10000].map((count) => (
                          <button
                            type="button"
                            key={count}
                            className={Number(people) === count ? "active" : ""}
                            onClick={() => setPeople(String(count))}
                            disabled={busy}
                          >
                            {number(count)}
                          </button>
                        ))}
                      </div>
                      <div className="intake-source-facts">
                        <div>
                          <span>Planned individuals</span>
                          <strong>
                            {validatePeople(people)
                              ? "Choose a valid size"
                              : number(Number(people))}
                          </strong>
                        </div>
                        <div>
                          <span>Actual source size</span>
                          <strong>Measured after generation</strong>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <p>
                        Start with the file you have. We’ll inspect its format,
                        identities and available evidence.
                      </p>
                      <label
                        className={`intake-upload ${file ? "has-file" : ""}`}
                      >
                        <FolderUp size={28} strokeWidth={1.4} />
                        <strong>{file ? file.name : "Choose a dataset"}</strong>
                        <span>
                          {file
                            ? formatBytes(file.size)
                            : "JSON, CSV / TSV, EML or mbox · up to 100 MB"}
                        </span>
                        <input
                          type="file"
                          accept=".json,.csv,.tsv,.eml,.mbox,.mbx"
                          disabled={busy}
                          onChange={(event) => {
                            setFile(event.target.files?.[0] ?? null);
                            setError("");
                          }}
                        />
                      </label>
                      <div className="intake-source-facts">
                        <div>
                          <span>Source size</span>
                          <strong>
                            {file ? formatBytes(file.size) : "Choose a file"}
                          </strong>
                        </div>
                        <div>
                          <span>People & data points</span>
                          <strong>Counted during inspection</strong>
                        </div>
                      </div>
                    </>
                  )}
                  <button
                    className="intake-primary"
                    type="button"
                    onClick={() => void inspect()}
                    disabled={busy || (mode === "import" && !file)}
                  >
                    {requesting ? (
                      <Loader2 size={16} className="intake-spin" />
                    ) : (
                      <Play size={15} />
                    )}
                    {mode === "synthetic"
                      ? "Generate & inspect"
                      : "Inspect dataset"}
                  </button>
                  <small className="intake-source-note">
                    Inspection stages data in memory. Database construction
                    waits for your review.
                  </small>
                </>
              ) : (
                <>
                  <div className="intake-source-name">
                    <FileText size={24} />
                    <strong>{job.source.name}</strong>
                  </div>
                  <div className="intake-source-facts">
                    <div>
                      <span>Format</span>
                      <strong>{job.source.format}</strong>
                    </div>
                    <div>
                      <span>Source size</span>
                      <strong>{formatBytes(job.source.bytes)}</strong>
                    </div>
                    {job.source.requested_people != null && (
                      <div>
                        <span>Requested individuals</span>
                        <strong>{number(job.source.requested_people)}</strong>
                      </div>
                    )}
                  </div>
                  <div className="intake-source-note">
                    {job.profile
                      ? "Source inspected. Counts shown are measured from the accepted records."
                      : "Inspecting the source before creating a workspace."}
                  </div>
                  {!busy && (
                    <button
                      className="intake-text-button"
                      type="button"
                      onClick={() => void reset(mode)}
                    >
                      <RotateCcw size={13} /> Change this source
                    </button>
                  )}
                </>
              )}
              <div className="intake-source-rule" />
              <div className="intake-principle">
                <ShieldCheck size={17} />
                <div>
                  <strong>Know what the chart knows</strong>
                  <p>
                    Missing fields, ambiguous identities and unsupported records
                    stay visible. An inferred link is a proposal to inspect.
                  </p>
                </div>
              </div>
              {mode === "import" && (
                <details className="intake-format-help">
                  <summary>Supported source fields</summary>
                  <p>
                    Message CSV: sender, to, timestamp, body. Roster CSV: id,
                    name, email, manager_id. Canonical JSON can also carry
                    entities, evidence and relationships.
                  </p>
                </details>
              )}
            </aside>
            <div className="intake-main-column">
              <section className="intake-process-card" ref={processRef}>
                <div className="intake-process-heading">
                  <span>
                    <span className="intake-eyebrow">The processing map</span>
                    <h2>{statusLabel}</h2>
                  </span>
                  {busy && (
                    <span className="intake-live">
                      <span /> Live
                    </span>
                  )}
                  {replayStage && (
                    <span className="intake-small-badge">REPLAY</span>
                  )}
                </div>
                <p
                  className="intake-process-description"
                  role="status"
                  aria-live="polite"
                >
                  {statusDetail}
                </p>
                {ready && (
                  <div className="intake-ready-action">
                    <span>
                      <Check size={16} /> {number(job.result!.counts.people)}{" "}
                      people · {number(job.result!.counts.selected)} selected
                      reporting links
                    </span>
                    <button
                      type="button"
                      className="intake-primary"
                      onClick={() => onComplete(job.result!)}
                      disabled={requesting}
                    >
                      Explore organization chart <ChevronRight size={17} />
                    </button>
                  </div>
                )}
                <IntakeDiagram
                  stages={stages}
                  selected={replayStage ?? selectedStage}
                  onSelect={(id) => {
                    stopReplay();
                    setSelectedStage(id);
                  }}
                  replay={replayStage}
                />
                <div className="intake-step-explanation">
                  <div>
                    <span className="intake-eyebrow">
                      {replayStage ? "Replay · " : ""}Step{" "}
                      {INTAKE_STAGES.findIndex(
                        (stage) => stage.id === selectedDefinition.id,
                      ) + 1}
                    </span>
                    <strong>{selectedDefinition.label}</strong>
                    <p>{selectedDefinition.explanation}</p>
                    {selectedDetail?.detail && (
                      <small>{selectedDetail.detail}</small>
                    )}
                  </div>
                  {!busy && completedStages(stages).length > 0 && (
                    <button
                      type="button"
                      className="intake-replay-button"
                      onClick={replayStage ? stopReplay : () => replay()}
                    >
                      {replayStage ? (
                        <span>Stop replay</span>
                      ) : (
                        <>
                          <Play size={13} /> Replay walkthrough
                        </>
                      )}
                    </button>
                  )}
                </div>
              </section>
              {(error || job?.error) && (
                <div className="intake-error" role="alert">
                  <AlertCircle size={18} />
                  <div>
                    <strong>We couldn’t finish this step.</strong>
                    <p>{error || job?.error}</p>
                    {busy && error && (
                      <button
                        type="button"
                        onClick={() => {
                          setError("");
                          setPollVersion((value) => value + 1);
                        }}
                      >
                        Reconnect to progress
                      </button>
                    )}
                    {job?.status === "failed" && !canBuild && (
                      <button type="button" onClick={() => void inspect()}>
                        Inspect source again
                      </button>
                    )}
                  </div>
                </div>
              )}
              {job?.profile && (
                <ProfileSummary
                  profile={job.profile}
                  bytes={job.source.bytes}
                />
              )}
              {job?.plan && <GraphPlan plan={job.plan} />}
              {canBuild && (
                <section className="intake-review-card">
                  <span className="intake-review-icon">
                    <Check size={21} />
                  </span>
                  <div>
                    <span className="intake-eyebrow">Your checkpoint</span>
                    <h2>Ready to build from this source?</h2>
                    <p>
                      The profile and preview describe source records. Reporting
                      links will be proposed from the available evidence during
                      the next steps.
                    </p>
                    {job!.workspace.package_requires_empty && (
                      <div className="intake-review-warning">
                        This exported workspace requires an empty destination to
                        preserve its history.
                      </div>
                    )}
                    {job!.workspace.requires_replacement &&
                      !job!.workspace.package_requires_empty && (
                        <label className="intake-replace">
                          <input
                            type="checkbox"
                            checked={replace}
                            onChange={(event) =>
                              setReplace(event.target.checked)
                            }
                          />{" "}
                          Switch the active workspace to this dataset. Previous
                          snapshots remain available.
                        </label>
                      )}
                    {job!.workspace.can_reuse && (
                      <p className="intake-reuse">
                        This dataset already exists in the workspace. Its saved
                        chart can be reused.
                      </p>
                    )}
                    <button
                      className="intake-primary"
                      type="button"
                      onClick={() => void build()}
                      disabled={
                        busy ||
                        job!.workspace.package_requires_empty ||
                        (job!.workspace.requires_replacement && !replace)
                      }
                    >
                      <Layers3 size={16} />
                      {job?.status === "failed"
                        ? "Retry building chart"
                        : job!.workspace.can_reuse
                          ? "Open saved chart"
                          : "Build organization chart"}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </section>
              )}
              {ready && (
                <section className="intake-complete-card">
                  <span className="intake-review-icon">
                    <Check size={23} />
                  </span>
                  <div>
                    <span className="intake-eyebrow">Ready to explore</span>
                    <h2>
                      {number(job.result!.counts.people)} people. One navigable
                      organization.
                    </h2>
                    <p>
                      {number(job.result!.counts.selected)} selected reporting
                      links · {number(job.result!.counts.unresolved)} people
                      without a selected manager. Open the chart to inspect the
                      evidence behind each connection.
                    </p>
                  </div>
                </section>
              )}
            </div>
          </div>
        </div>
      )}
      <footer className="intake-footer">
        <span>ORGANIZATION ATLAS</span>
        <span>From source records to explainable structure.</span>
        <span>Project 04</span>
      </footer>
    </div>
  );
}
