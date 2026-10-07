import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  FolderUp,
  GitBranch,
  GitCompareArrows,
  Layers3,
  Loader2,
  LocateFixed,
  Mail,
  Network,
  Play,
  RotateCcw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Table2,
  Users,
  X,
  AlertCircle,
  Braces,
  ExternalLink,
} from "./icons";
import { api, displayDate, initials, label, post, query } from "./api";
import type {
  Assertion,
  Comparison,
  Detail,
  Evidence,
  Group,
  Page,
  Review,
  Workspace,
} from "./types";
import SemanticChart from "./SemanticChart";
import IntakeFlow from "./IntakeFlow";
import {
  directoryRecovery,
  distinctSnapshotPair,
  reviewEntry,
} from "./explorerGuidance";
import "./explorer-guidance.css";

function useResource<T>(path: string | null, version: number) {
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    api<T>(path, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(String(cause.message || cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, version, attempt]);
  return {
    data,
    error,
    loading,
    retry: () => setAttempt((value) => value + 1),
  };
}
function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Spinner({ text = "Loading…" }: { text?: string }) {
  return (
    <div className="loading">
      <Loader2 className="spin" size={17} />
      {text}
    </div>
  );
}
function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div className="error-box" role="alert">
      <AlertCircle size={16} />
      <span>{message}</span>
    </div>
  ) : null;
}
function Modal({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} className="modal" onCancel={onClose}>
      <div className="modal-heading">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {description && <p className="muted modal-description">{description}</p>}
      {children}
    </dialog>
  );
}
function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const aggregate = evidence.kind === "communication_aggregate";
  return (
    <article className="evidence-card">
      <div className="evidence-kind">
        {aggregate ? <Network size={13} /> : <FileText size={13} />}{" "}
        {label(evidence.kind)}
      </div>
      {!evidence.available ? (
        <div className="notice">
          Evidence body unavailable. Reference retained.
        </div>
      ) : (
        <>
          {evidence.text && <blockquote>{evidence.text}</blockquote>}
          {aggregate && (
            <p className="small muted">
              Behavioral signal; does not establish direct reporting.
            </p>
          )}
          {evidence.details && Object.keys(evidence.details).length > 0 && (
            <details>
              <summary>Derivation & signals</summary>
              <dl className="signal-list">
                {Object.entries(evidence.details).map(([key, value]) => (
                  <div key={key}>
                    <dt>{label(key)}</dt>
                    <dd>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </>
      )}
      <div className="source-ref">
        <span>Source</span>
        <code>{evidence.source_ref || evidence.id}</code>
      </div>
    </article>
  );
}
function assertionText(value: unknown): string {
  if (value === null || value === undefined) return "No selected manager";
  if (typeof value === "string") return value;
  if (typeof value !== "object") return String(value);
  const item = value as Record<string, unknown>;
  return String(
    item.object_name ||
      item.manager_name ||
      item.object ||
      item.manager_id ||
      JSON.stringify(item),
  );
}

export default function App() {
  const [intakeMode, setIntakeMode] = useState<
    "choose" | "import" | "synthetic" | null
  >("choose");
  const [groupOffsets, setGroupOffsets] = useState<Record<string, number>>({});
  const [workspace, setWorkspace] = useState<Workspace | null>(null),
    [initialLoading, setInitialLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState("");
  const [snapshot, setSnapshot] = useState(""),
    [selected, setSelected] = useState<string | null>(null),
    [focus, setFocus] = useState<string | null>(null),
    [nodeLimit, setNodeLimit] = useState(30);
  const [search, setSearch] = useState(""),
    [debouncedSearch, setDebouncedSearch] = useState(""),
    [status, setStatus] = useState("all"),
    [offset, setOffset] = useState(0),
    [view, setView] = useState<"graph" | "people" | "groups" | "changes">(
      "graph",
    );
  const [drawerTab, setDrawerTab] = useState<
      "evidence" | "review" | "activity"
    >("evidence"),
    [assertionId, setAssertionId] = useState(""),
    [reviewAction, setReviewAction] = useState("accept"),
    [undoEvent, setUndoEvent] = useState("");
  const [reason, setReason] = useState(""),
    [managerSearch, setManagerSearch] = useState(""),
    [managerQuery, setManagerQuery] = useState(""),
    [managerId, setManagerId] = useState(""),
    [validFrom, setValidFrom] = useState(""),
    [validTo, setValidTo] = useState("");
  const [modal, setModal] = useState<"run" | "export" | "about" | null>(null);
  const [threshold, setThreshold] = useState(0.55),
    [margin, setMargin] = useState(0.08),
    [asOf, setAsOf] = useState(""),
    [compareBefore, setCompareBefore] = useState(""),
    [compareAfter, setCompareAfter] = useState("");
  const version = workspace?.revision ?? 0;
  const historical = Boolean(
    snapshot && snapshot !== workspace?.active_snapshot,
  );
  const exists = Boolean(workspace?.corpus) && intakeMode === null;
  useEffect(() => {
    api<Workspace>("/workspace")
      .then(setWorkspace)
      .catch((cause) => setError(cause.message))
      .finally(() => setInitialLoading(false));
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 220);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    const timer = setTimeout(() => setManagerQuery(managerSearch), 220);
    return () => clearTimeout(timer);
  }, [managerSearch]);
  useEffect(() => {
    setAssertionId("");
    setReason("");
    setUndoEvent("");
    setReviewAction("accept");
    setManagerId("");
    setManagerSearch("");
    setValidFrom("");
    setValidTo("");
    setDrawerTab("evidence");
  }, [selected]);
  useEffect(() => {
    if (!workspace?.snapshots?.length) return;
    const snaps = workspace.snapshots;
    if (!compareBefore && snaps.length > 1)
      setCompareBefore(snaps[snaps.length - 1].id);
    if (!compareAfter)
      setCompareAfter(workspace.active_snapshot || snaps[0].id);
  }, [workspace, compareBefore, compareAfter]);
  const page = useResource<Page>(
    exists
      ? `/entities${query({ q: debouncedSearch, type: "person", status, offset, limit: 40, snapshot })}`
      : null,
    version,
  );
  const detail = useResource<Detail>(
    exists && selected
      ? `/entities/${encodeURIComponent(selected)}${query({ snapshot })}`
      : null,
    version,
  );
  const groups = useResource<{ items: Group[] }>(
    exists && view === "groups" ? `/groups${query({ snapshot })}` : null,
    version,
  );
  const comparison = useResource<Comparison>(
    exists &&
      view === "changes" &&
      compareBefore &&
      compareAfter &&
      compareBefore !== compareAfter
      ? `/compare${query({ before: compareBefore, after: compareAfter })}`
      : null,
    version,
  );
  const managerOptions = useResource<Page>(
    exists && drawerTab === "review" && reviewAction === "replace"
      ? `/entities${query({ q: managerQuery, type: "person", limit: 30 })}`
      : null,
    version,
  );
  const historicalWorkspace = useResource<Workspace>(
    exists && historical ? `/workspace${query({ snapshot })}` : null,
    version,
  );
  const visibleWorkspace = historicalWorkspace.data || workspace;
  const counts = visibleWorkspace?.counts;
  const selectedSnapshot = workspace?.snapshots?.find(
    (item) => item.id === (snapshot || workspace.active_snapshot),
  );
  const allAssertions = detail.data
    ? [detail.data.manager, ...(detail.data.alternatives || [])]
        .filter((item): item is Assertion => Boolean(item))
        .filter(
          (item, index, all) =>
            all.findIndex((other) => other.id === item.id) === index,
        )
    : [];
  const recovery = directoryRecovery(search, status, offset);
  const firstPerson = page.data?.items[0];
  const comparisonPair = distinctSnapshotPair(
    workspace?.snapshots.map((item) => item.id) || [],
    workspace?.active_snapshot,
  );
  function clearDirectoryFilters() {
    setSearch("");
    setDebouncedSearch("");
    setStatus("all");
    setOffset(0);
    setSelected(null);
  }
  function changeDirectoryStatus(next: string) {
    setStatus(next);
    setOffset(0);
    setSelected(null);
  }
  function recoverDirectory() {
    if (recovery.action === "import") setIntakeMode("import");
    else clearDirectoryFilters();
  }
  function inspectFirstPerson() {
    if (firstPerson) selectPerson(firstPerson.id);
  }
  function showPersonChart(id: string) {
    selectPerson(id);
    setFocus(id);
    setView("graph");
  }
  function openReviewForm() {
    const next = reviewEntry(allAssertions, activeAssertion?.id);
    setAssertionId(next.assertionId);
    setReviewAction(next.action);
    setUndoEvent("");
    setReason("");
    setDrawerTab("review");
  }
  function chooseComparisonPair() {
    if (!comparisonPair) return;
    setCompareBefore(comparisonPair.before);
    setCompareAfter(comparisonPair.after);
  }
  const activeAssertion =
    allAssertions.find((item) => item.id === assertionId) ||
    allAssertions[0] ||
    null;
  const selectedEvidence = activeAssertion
    ? activeAssertion.evidence?.length
      ? activeAssertion.evidence
      : (detail.data?.evidence || []).filter((item) =>
          activeAssertion.evidence_ids?.includes(item.id),
        )
    : detail.data?.evidence || [];
  async function mutate(
    name: string,
    action: () => Promise<Workspace>,
    success: string,
  ) {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      const next = await action();
      setWorkspace(next);
      setCompareBefore(workspace?.active_snapshot || "");
      setCompareAfter(next.active_snapshot || "");
      setSnapshot("");
      setNotice(success);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return false;
    } finally {
      setBusy("");
    }
  }
  function selectPerson(id: string) {
    setSelected(id);
    setAssertionId("");
  }
  function openIntakeResult(next: Workspace) {
    setWorkspace(next);
    setSnapshot("");
    setSelected(null);
    setFocus(null);
    setSearch("");
    setDebouncedSearch("");
    setStatus("all");
    setOffset(0);
    setGroupOffsets({});
    setView("graph");
    setCompareBefore("");
    setCompareAfter("");
    setError("");
    setNotice("");
    setIntakeMode(null);
  }
  async function runInference(event: FormEvent) {
    event.preventDefault();
    const ok = await mutate(
      "infer",
      async () =>
        (
          await post<{ workspace: Workspace }>("/infer", {
            base_revision: version,
            threshold,
            margin,
            as_of: asOf || null,
          })
        ).workspace,
      "Inference complete. A new snapshot is available.",
    );
    if (ok) setModal(null);
  }
  async function saveReview(event: FormEvent) {
    event.preventDefault();
    if (!selected || !reason.trim()) return;
    const ok = await mutate(
      "review",
      async () =>
        (
          await post<{ workspace: Workspace }>("/reviews", {
            base_revision: detail.data?.revision ?? version,
            subject: selected,
            action: reviewAction,
            assertion_id: activeAssertion?.id,
            object: reviewAction === "replace" ? managerId : undefined,
            valid_from: validFrom || null,
            valid_to: validTo || null,
            reason: reason.trim(),
            event_id: reviewAction === "undo" ? undoEvent : undefined,
            idempotency_key: crypto.randomUUID(),
          })
        ).workspace,
      reviewAction === "undo"
        ? "Review undone. The audit trail is retained."
        : "Review saved. Your decision will survive inference refreshes.",
    );
    if (ok) {
      setReason("");
      setUndoEvent("");
      setDrawerTab("activity");
    }
  }
  function prepareReview(
    action: string,
    assertion?: Assertion,
    event?: Review,
  ) {
    if (assertion) setAssertionId(assertion.id);
    setReviewAction(action);
    setUndoEvent(String(event?.id || event?.event_id || ""));
    setReason("");
    setDrawerTab("review");
  }
  async function download(format: string) {
    setBusy("export");
    setError("");
    try {
      const response = await fetch(`/api/export${query({ format, snapshot })}`);
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Export failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `organization-atlas-${snapshot || workspace?.active_snapshot || "current"}.${format === "report" ? "md" : format}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("Export downloaded with snapshot provenance.");
      setModal(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Organization Atlas home">
          <span className="brand-mark">
            <GitBranch size={23} strokeWidth={1.6} />
          </span>
          <span>
            atlas<span className="brand-period">.</span>
          </span>
        </a>
        <div className="topbar-divider" />
        <div className="project-crumb">
          <span>SCADS 2026</span>
          <ChevronRight size={13} />
          <strong>Project 04</strong>
        </div>
        <div className="topbar-right">
          <span className="local-indicator">
            <span className="live-dot" /> Local workspace
          </span>
          <button
            className="icon-button"
            title="About this workspace"
            aria-label="About this workspace"
            onClick={() => setModal("about")}
          >
            <CircleHelp size={18} />
          </button>
          <span className="avatar analyst-avatar" title="Local analyst">
            AN
          </span>
        </div>
      </header>
      <main>
        {intakeMode !== null ? (
          initialLoading ? (
            <Spinner text="Opening your workspace…" />
          ) : (
            <>
              {error && (
                <div className="global-feedback">
                  <ErrorBox message={error} />
                  <button
                    className="text-button"
                    onClick={() => {
                      setError("");
                      api<Workspace>("/workspace")
                        .then(setWorkspace)
                        .catch((cause) => setError(cause.message));
                    }}
                  >
                    Retry workspace connection
                  </button>
                </div>
              )}
              <IntakeFlow
                workspace={workspace}
                initialMode={intakeMode === "choose" ? null : intakeMode}
                onComplete={openIntakeResult}
              />
            </>
          )
        ) : (
          <>
            <section className="page-heading">
              <div>
                <div className="eyebrow">ORGANIZATION INTELLIGENCE</div>
                <h1>Organization atlas</h1>
                <p className="subtitle">
                  Follow the structure. Question the evidence.
                </p>
              </div>
              <div className="heading-actions">
                <button
                  className="button secondary"
                  onClick={() => {
                    setIntakeMode("import");
                  }}
                  disabled={Boolean(busy)}
                >
                  <FolderUp size={16} /> Import records
                </button>
                <button
                  className="button primary"
                  disabled={!exists || Boolean(busy) || historical}
                  onClick={() => setModal("run")}
                >
                  {busy === "infer" ? (
                    <Loader2 className="spin" size={16} />
                  ) : (
                    <Play size={14} fill="currentColor" />
                  )}{" "}
                  Run inference
                </button>
              </div>
            </section>
            <div className="global-feedback">
              {error && (
                <div className="error-banner" role="alert">
                  <AlertCircle size={17} />
                  <span>{error}</span>
                  <button
                    className="text-button"
                    onClick={() => {
                      setError("");
                      api<Workspace>("/workspace")
                        .then(setWorkspace)
                        .catch((cause) => setError(cause.message));
                    }}
                  >
                    Refresh workspace
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Dismiss error"
                    onClick={() => setError("")}
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              {notice && (
                <div className="success-banner" role="status">
                  <CheckCheck size={16} />
                  <span>{notice}</span>
                  <button
                    className="icon-button"
                    aria-label="Dismiss notification"
                    onClick={() => setNotice("")}
                  >
                    <X size={15} />
                  </button>
                </div>
              )}
            </div>
            {initialLoading ? (
              <div className="initial-loading">
                <Spinner text="Opening your workspace…" />
              </div>
            ) : !exists ? (
              <button
                className="button primary"
                onClick={() => setIntakeMode("choose")}
              >
                Choose a dataset
              </button>
            ) : (
              <>
                <section className="workspace-strip">
                  <div className="corpus-name">
                    <span className="corpus-icon">
                      <Layers3 size={18} />
                    </span>
                    <div>
                      <strong>{workspace?.corpus?.name}</strong>
                      <span>
                        {workspace?.corpus?.synthetic
                          ? "Fictional research corpus"
                          : "Imported organization records"}
                      </span>
                    </div>
                    {workspace?.corpus?.synthetic && (
                      <Badge tone="amber">SYNTHETIC</Badge>
                    )}
                  </div>
                  <div className="snapshot-control">
                    <Clock3 size={14} />
                    <label className="sr-only" htmlFor="snapshot">
                      Snapshot
                    </label>
                    <select
                      id="snapshot"
                      value={snapshot}
                      onChange={(event) => {
                        setSnapshot(event.target.value);
                        setOffset(0);
                        setSelected(null);
                      }}
                    >
                      <option value="">Latest snapshot</option>
                      {workspace?.snapshots?.map((item) => (
                        <option key={item.id} value={item.id}>
                          {label(item.reason)} · {displayDate(item.created_at)}
                        </option>
                      ))}
                    </select>
                    <span className="strip-divider" />
                    <button
                      className="text-button"
                      disabled={Boolean(busy)}
                      onClick={() => setModal("export")}
                    >
                      <ArrowDownToLine size={15} /> Export
                    </button>
                  </div>
                </section>
                {historical && (
                  <div className="historical-notice">
                    <Clock3 size={14} /> Historical snapshot · edits are
                    available in the latest snapshot.
                    <button
                      className="text-button"
                      onClick={() => setSnapshot("")}
                    >
                      Return to latest <ArrowRight size={14} />
                    </button>
                  </div>
                )}
                <section
                  className="metrics-strip"
                  aria-label="Workspace summary"
                >
                  <div className="stat">
                    <span>
                      <Users size={15} /> People
                    </span>
                    <strong>{(counts?.people || 0).toLocaleString()}</strong>
                  </div>
                  <div className="stat">
                    <span>
                      <GitBranch size={15} /> Reporting links
                    </span>
                    <strong>{(counts?.selected || 0).toLocaleString()}</strong>
                  </div>
                  <button
                    className={`stat clickable ${status === "unresolved" ? "selected" : ""}`}
                    onClick={() => {
                      changeDirectoryStatus(
                        status === "unresolved" ? "all" : "unresolved",
                      );
                    }}
                  >
                    <span>
                      <CircleHelp size={15} /> Unresolved
                    </span>
                    <strong className="amber-text">
                      {(counts?.unresolved || 0).toLocaleString()}
                      <ArrowUpRight size={15} />
                    </strong>
                  </button>
                  <button
                    className={`stat clickable ${status === "reviewed" ? "selected" : ""}`}
                    onClick={() => {
                      changeDirectoryStatus(
                        status === "reviewed" ? "all" : "reviewed",
                      );
                    }}
                  >
                    <span>
                      <ShieldCheck size={15} /> Reviewed
                    </span>
                    <strong className="teal-text">
                      {(counts?.reviewed || 0).toLocaleString()}
                      <ArrowUpRight size={15} />
                    </strong>
                  </button>
                  <div className="model-state">
                    <span className="model-state-icon">
                      <SlidersHorizontal size={17} />
                    </span>
                    <div>
                      <strong>
                        {visibleWorkspace?.model?.name ||
                          "Baseline not yet run"}
                      </strong>
                      <span>
                        {visibleWorkspace?.model
                          ? "Raw scores · no calibrated probabilities"
                          : "Run inference to propose relationships"}
                      </span>
                    </div>
                  </div>
                </section>
                <section
                  className={`analyst-workspace ${selected ? "has-selection" : ""}`}
                >
                  <aside className="directory" aria-label="People directory">
                    <div className="panel-heading">
                      <h2>People</h2>
                      <span className="count-pill">
                        {page.data?.total ?? counts?.people ?? "—"}
                      </span>
                    </div>
                    <label className="search-field">
                      <Search size={15} />
                      <input
                        placeholder="Find a person, role, email…"
                        aria-label="Search people"
                        value={search}
                        onChange={(event) => {
                          setSearch(event.target.value);
                          setSelected(null);
                        }}
                      />
                      {search && (
                        <button
                          className="icon-button"
                          aria-label="Clear search"
                          onClick={() => {
                            setSearch("");
                            setSelected(null);
                          }}
                        >
                          <X size={13} />
                        </button>
                      )}
                    </label>
                    <div className="directory-filter">
                      <label htmlFor="status">Show</label>
                      <select
                        id="status"
                        value={status}
                        onChange={(event) =>
                          changeDirectoryStatus(event.target.value)
                        }
                      >
                        <option value="all">Everyone</option>
                        <option value="unresolved">Unresolved managers</option>
                        <option value="inferred">Inferred relationships</option>
                        <option value="source">Source relationships</option>
                        <option value="reviewed">Reviewed relationships</option>
                      </select>
                    </div>
                    <div className="people-list">
                      {page.loading && <Spinner text="Finding people…" />}
                      <ErrorBox message={page.error} />
                      {page.error && (
                        <button
                          className="button next-action compact resource-retry"
                          onClick={page.retry}
                        >
                          Retry people <RotateCcw size={13} />
                        </button>
                      )}
                      {page.data?.items.map((person) => (
                        <button
                          key={person.id}
                          className={`person-row ${selected === person.id ? "selected" : ""}`}
                          onClick={() => selectPerson(person.id)}
                        >
                          <span
                            className={`avatar ${person.status === "unresolved" ? "avatar-amber" : ""}`}
                          >
                            {initials(person.name)}
                          </span>
                          <span className="person-info">
                            <strong>{person.name}</strong>
                            <span>
                              {person.role ||
                                person.email ||
                                label(person.type)}
                            </span>
                          </span>
                          <span
                            title={label(person.status)}
                            className={`status-dot ${person.status || "unresolved"}`}
                          />
                          <ChevronRight size={13} />
                        </button>
                      ))}
                      {page.data?.items.length === 0 && (
                        <div className="empty-directory">
                          <Search size={22} />
                          <p>{recovery.title}</p>
                          <button
                            className="button next-action compact"
                            onClick={recoverDirectory}
                          >
                            {recovery.label} <ArrowRight size={13} />
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="list-pagination">
                      <span>
                        {page.data?.total
                          ? `${offset + 1}–${Math.min(offset + 40, page.data.total)} of ${page.data.total}`
                          : "0 results"}
                      </span>
                      <button
                        className="icon-button"
                        aria-label="Previous people page"
                        disabled={offset === 0 || page.loading}
                        onClick={() =>
                          setOffset((value) => Math.max(0, value - 40))
                        }
                      >
                        <ArrowLeft size={14} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label="Next people page"
                        disabled={
                          !page.data ||
                          offset + 40 >= page.data.total ||
                          page.loading
                        }
                        onClick={() => setOffset((value) => value + 40)}
                      >
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  </aside>
                  <section
                    className="explorer"
                    aria-label="Organization explorer"
                  >
                    <div className="explorer-toolbar">
                      <nav className="view-tabs" aria-label="Explorer view">
                        {(
                          [
                            { id: "graph", title: "Chart", icon: GitBranch },
                            { id: "people", title: "Table", icon: Table2 },
                            { id: "groups", title: "Groups", icon: Users },
                            {
                              id: "changes",
                              title: "Changes",
                              icon: GitCompareArrows,
                            },
                          ] as const
                        ).map((item) => (
                          <button
                            key={item.id}
                            className={view === item.id ? "active" : ""}
                            aria-current={view === item.id ? "page" : undefined}
                            onClick={() => setView(item.id)}
                          >
                            <item.icon size={15} />
                            <span>{item.title}</span>
                          </button>
                        ))}
                      </nav>
                      {view === "graph" && (
                        <label className="node-budget">
                          <select
                            aria-label="Chart cards per page"
                            value={nodeLimit}
                            onChange={(event) =>
                              setNodeLimit(Number(event.target.value))
                            }
                          >
                            <option value={30}>30 cards</option>
                            <option value={80}>80 cards</option>
                            <option value={200}>200 cards</option>
                          </select>
                        </label>
                      )}
                    </div>
                    <div className="scope-bar">
                      <span>
                        {selectedSnapshot?.as_of
                          ? `As of ${selectedSnapshot.as_of}`
                          : "Undated exploration"}
                      </span>
                      <Badge>PRIMARY REPORTING</Badge>
                    </div>
                    {view === "graph" && !selected && firstPerson && (
                      <div className="explorer-next-step">
                        <div>
                          <strong>
                            Explore the structure, then inspect the evidence
                          </strong>
                          <p>
                            Zoom into a group or start with one person's
                            reporting connections.
                          </p>
                        </div>
                        <button
                          className="button next-action compact"
                          onClick={() => showPersonChart(firstPerson.id)}
                        >
                          Explore a person <ArrowRight size={14} />
                        </button>
                      </div>
                    )}
                    {view === "people" && firstPerson && (
                      <div className="explorer-next-step">
                        <div>
                          <strong>
                            {selected
                              ? "Follow this person's reporting connections"
                              : "Select a person to inspect their evidence"}
                          </strong>
                          <p>
                            {selected
                              ? "Open their position in the chart, or continue in the evidence panel."
                              : "The table and directory share the same search and filters."}
                          </p>
                        </div>
                        <button
                          className="button next-action compact"
                          onClick={() =>
                            selected
                              ? showPersonChart(selected)
                              : inspectFirstPerson()
                          }
                        >
                          {selected ? "Open in chart" : "Inspect a person"}{" "}
                          <ArrowRight size={14} />
                        </button>
                      </div>
                    )}
                    {view === "graph" && (
                      <SemanticChart
                        snapshot={snapshot || workspace?.active_snapshot || ""}
                        version={version}
                        limit={nodeLimit}
                        selected={selected}
                        onSelect={selectPerson}
                        focus={focus}
                        onFocus={setFocus}
                      />
                    )}
                    {view === "people" && (
                      <div className="table-scroll">
                        <div className="section-intro">
                          <h3>People & communication</h3>
                          <p>
                            Observed interaction counts describe communication,
                            not authority.
                          </p>
                        </div>
                        {page.loading && <Spinner />}
                        <ErrorBox message={page.error} />
                        {Boolean(page.data?.items.length) && (
                          <table>
                            <thead>
                              <tr>
                                <th>Person</th>
                                <th>Manager</th>
                                <th>Status</th>
                                <th title="Distinct observed counterparties">
                                  Breadth
                                </th>
                                <th title="Observed cross-unit communications">
                                  Cross-unit
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {page.data?.items.map((person) => (
                                <tr
                                  key={person.id}
                                  className={
                                    selected === person.id ? "selected" : ""
                                  }
                                >
                                  <td>
                                    <button
                                      className="table-name"
                                      onClick={() => selectPerson(person.id)}
                                    >
                                      {person.name}
                                      <span>{person.role || person.email}</span>
                                    </button>
                                  </td>
                                  <td>
                                    {person.manager_name || (
                                      <span className="muted">Unresolved</span>
                                    )}
                                  </td>
                                  <td>
                                    <Badge
                                      tone={
                                        person.status === "unresolved"
                                          ? "amber"
                                          : "teal"
                                      }
                                    >
                                      {label(person.status)}
                                    </Badge>
                                  </td>
                                  <td>{person.metrics?.breadth ?? "—"}</td>
                                  <td>{person.metrics?.cross_unit ?? "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        {page.data?.items.length === 0 && (
                          <div className="panel-empty">
                            <Search size={26} />
                            <h3>{recovery.title}</h3>
                            <p>{recovery.description}</p>
                            <button
                              className="button next-action"
                              onClick={recoverDirectory}
                            >
                              {recovery.label} <ArrowRight size={14} />
                            </button>
                          </div>
                        )}
                        {Boolean(page.data?.items.length) && (
                          <p className="table-note">
                            Same directory filters and pagination apply. Breadth
                            = distinct observed counterparties; cross-unit =
                            observed communications between different known
                            units.
                          </p>
                        )}
                      </div>
                    )}
                    {view === "groups" && (
                      <div className="content-scroll">
                        <div className="section-intro">
                          <h3>Teams & communication groups</h3>
                          <p>
                            Formal units come from records. Inferred groups are
                            communication patterns; they do not establish
                            reporting lines.
                          </p>
                        </div>
                        {groups.loading && <Spinner />}
                        <ErrorBox message={groups.error} />
                        {groups.error && (
                          <button
                            className="button next-action resource-retry"
                            onClick={groups.retry}
                          >
                            Retry groups <RotateCcw size={14} />
                          </button>
                        )}
                        {groups.data?.items.length === 0 && (
                          <div className="panel-empty">
                            <Users size={26} />
                            <h3>No groups available</h3>
                            <p>
                              This snapshot has no formal units or communication
                              groups. You can still explore individual people
                              and their reporting evidence.
                            </p>
                            <button
                              className="button next-action"
                              onClick={() => setView("people")}
                            >
                              Explore people <ArrowRight size={14} />
                            </button>
                          </div>
                        )}
                        <div className="group-grid">
                          {groups.data?.items.map((group) => (
                            <article className="group-card" key={group.id}>
                              <div>
                                <span className="group-icon">
                                  <Users size={20} />
                                </span>
                                <Badge
                                  tone={
                                    group.kind === "formal" ? "teal" : "amber"
                                  }
                                >
                                  {group.kind === "formal"
                                    ? "Formal unit"
                                    : "Inferred group"}
                                </Badge>
                              </div>
                              <h3>{group.name}</h3>
                              <p>
                                {group.members.length} members ·{" "}
                                {group.kind === "formal"
                                  ? "Source-defined membership"
                                  : "Observed communication pattern"}
                              </p>
                              {group.members.length > 0 ? (
                                <button
                                  className="button next-action compact group-open"
                                  onClick={() =>
                                    showPersonChart(group.members[0])
                                  }
                                >
                                  Explore a member <ArrowRight size={13} />
                                </button>
                              ) : (
                                <>
                                  <p className="empty-group-members">
                                    No person memberships are recorded for this
                                    unit. Browse people to inspect the available
                                    records.
                                  </p>
                                  <button
                                    className="button next-action compact group-open"
                                    onClick={() => setView("people")}
                                  >
                                    Browse people <ArrowRight size={13} />
                                  </button>
                                </>
                              )}
                              {group.members.length > 0 && (
                                <details>
                                  <summary>
                                    Explore members <ChevronDown size={13} />
                                  </summary>
                                  <div className="group-members">
                                    {group.members
                                      .slice(
                                        groupOffsets[group.id] || 0,
                                        (groupOffsets[group.id] || 0) + 20,
                                      )
                                      .map((id) => (
                                        <button
                                          key={id}
                                          className="text-button"
                                          onClick={() => {
                                            selectPerson(id);
                                            setFocus(id);
                                            setView("graph");
                                          }}
                                        >
                                          {group.member_names?.[id] ||
                                            page.data?.items.find(
                                              (person) => person.id === id,
                                            )?.name ||
                                            id}
                                          <ArrowUpRight size={12} />
                                        </button>
                                      ))}
                                  </div>
                                  {group.members.length > 20 && (
                                    <div className="list-pagination">
                                      <span>
                                        {(groupOffsets[group.id] || 0) + 1}–
                                        {Math.min(
                                          (groupOffsets[group.id] || 0) + 20,
                                          group.members.length,
                                        )}{" "}
                                        of {group.members.length}
                                      </span>
                                      <button
                                        className="icon-button"
                                        aria-label={`Previous members of ${group.name}`}
                                        disabled={!groupOffsets[group.id]}
                                        onClick={() =>
                                          setGroupOffsets((current) => ({
                                            ...current,
                                            [group.id]: Math.max(
                                              0,
                                              (current[group.id] || 0) - 20,
                                            ),
                                          }))
                                        }
                                      >
                                        <ArrowLeft size={13} />
                                      </button>
                                      <button
                                        className="icon-button"
                                        aria-label={`Next members of ${group.name}`}
                                        disabled={
                                          (groupOffsets[group.id] || 0) + 20 >=
                                          group.members.length
                                        }
                                        onClick={() =>
                                          setGroupOffsets((current) => ({
                                            ...current,
                                            [group.id]:
                                              (current[group.id] || 0) + 20,
                                          }))
                                        }
                                      >
                                        <ArrowRight size={13} />
                                      </button>
                                    </div>
                                  )}
                                </details>
                              )}
                            </article>
                          ))}
                        </div>
                      </div>
                    )}
                    {view === "changes" && (
                      <div className="content-scroll">
                        <div className="section-intro">
                          <h3>What changed?</h3>
                          <p>
                            Compare semantic relationships. A model or review
                            change does not imply a real-world reorganization.
                          </p>
                        </div>
                        <div className="compare-selectors">
                          <label>
                            Before
                            <select
                              value={compareBefore}
                              onChange={(event) =>
                                setCompareBefore(event.target.value)
                              }
                            >
                              <option value="">Choose snapshot</option>
                              {workspace?.snapshots?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {label(item.reason)} ·{" "}
                                  {displayDate(item.created_at)}
                                </option>
                              ))}
                            </select>
                          </label>
                          <ArrowRight size={18} />
                          <label>
                            After
                            <select
                              value={compareAfter}
                              onChange={(event) =>
                                setCompareAfter(event.target.value)
                              }
                            >
                              <option value="">Choose snapshot</option>
                              {workspace?.snapshots?.map((item) => (
                                <option key={item.id} value={item.id}>
                                  {label(item.reason)} ·{" "}
                                  {displayDate(item.created_at)}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                        {comparison.loading && (
                          <Spinner text="Comparing snapshots…" />
                        )}
                        <ErrorBox message={comparison.error} />
                        {comparison.error && (
                          <button
                            className="button next-action resource-retry"
                            onClick={comparison.retry}
                          >
                            Retry comparison <RotateCcw size={14} />
                          </button>
                        )}
                        {(!compareBefore ||
                          !compareAfter ||
                          compareBefore === compareAfter) && (
                          <div className="panel-empty">
                            <GitCompareArrows size={28} />
                            <h3>
                              {comparisonPair
                                ? "Choose two different snapshots"
                                : "Your first snapshot is ready"}
                            </h3>
                            <p>
                              {comparisonPair
                                ? "Compare an earlier saved state with the latest snapshot to see relationship changes."
                                : "A comparison becomes available after an inference run or an analyst review creates another snapshot. Start by inspecting the existing evidence."}
                            </p>
                            <button
                              className="button next-action"
                              onClick={
                                comparisonPair
                                  ? chooseComparisonPair
                                  : () => {
                                      setView("people");
                                      inspectFirstPerson();
                                    }
                              }
                            >
                              {comparisonPair
                                ? "Compare saved snapshots"
                                : "Inspect people"}{" "}
                              <ArrowRight size={14} />
                            </button>
                          </div>
                        )}
                        {comparison.data && compareBefore !== compareAfter && (
                          <>
                            <div className="comparison-count">
                              {comparison.data.total} relationship changes
                            </div>
                            {comparison.data.changes.map((change, index) => (
                              <article
                                className="change-card"
                                key={`${change.subject}-${index}`}
                              >
                                <div>
                                  <button
                                    className="table-name"
                                    onClick={() => {
                                      setSnapshot(
                                        change.after == null
                                          ? compareBefore
                                          : compareAfter,
                                      );
                                      selectPerson(change.subject);
                                    }}
                                  >
                                    {change.subject_name || change.subject}
                                  </button>
                                  <Badge>{label(change.kind)}</Badge>
                                </div>
                                <div className="change-values">
                                  <span>{assertionText(change.before)}</span>
                                  <ArrowRight size={15} />
                                  <span>{assertionText(change.after)}</span>
                                </div>
                              </article>
                            ))}
                            {comparison.data.total === 0 && (
                              <div className="panel-empty">
                                <CheckCheck size={26} />
                                <h3>No relationship changes</h3>
                                <p>
                                  The selected snapshots have the same compared
                                  relationship state.
                                </p>
                                <button
                                  className="button next-action"
                                  onClick={() => setView("graph")}
                                >
                                  Continue exploring <ArrowRight size={14} />
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </section>
                  <aside
                    className="inspector"
                    aria-label="Person and evidence inspector"
                  >
                    {!selected ? (
                      <div className="inspector-empty">
                        <div className="inspection-icon">
                          <LocateFixed size={27} strokeWidth={1.4} />
                        </div>
                        <div className="eyebrow">NEXT STEP</div>
                        <h2>Inspect a person</h2>
                        <p>
                          Select a person to trace their reporting line, compare
                          alternatives, and review the source material.
                        </p>
                        {firstPerson ? (
                          <button
                            className="button next-action compact"
                            onClick={inspectFirstPerson}
                          >
                            Inspect {firstPerson.name.split(" ")[0]}{" "}
                            <ArrowRight size={14} />
                          </button>
                        ) : page.data?.items.length === 0 ? (
                          <button
                            className="button next-action compact"
                            onClick={recoverDirectory}
                          >
                            {recovery.label} <ArrowRight size={14} />
                          </button>
                        ) : null}
                        <div className="inspector-hint">
                          <ShieldCheck size={16} />
                          <span>Every correction leaves an audit trail.</span>
                        </div>
                      </div>
                    ) : (
                      <>
                        {detail.loading && (
                          <Spinner text="Loading person & evidence…" />
                        )}
                        <ErrorBox message={detail.error} />
                        {detail.error && (
                          <>
                            <button
                              className="button next-action compact resource-retry"
                              onClick={detail.retry}
                            >
                              Retry person <RotateCcw size={14} />
                            </button>
                            <button
                              className="button secondary compact resource-retry"
                              onClick={() => {
                                clearDirectoryFilters();
                                setView("people");
                              }}
                            >
                              Browse available people <ArrowRight size={13} />
                            </button>
                          </>
                        )}
                        {detail.data && (
                          <>
                            <div className="inspector-profile">
                              <div className="profile-top">
                                <span className="avatar profile-avatar">
                                  {initials(detail.data.entity.name)}
                                </span>
                                <button
                                  className="icon-button"
                                  aria-label="Close person details"
                                  onClick={() => setSelected(null)}
                                >
                                  <X size={17} />
                                </button>
                              </div>
                              <h2>{detail.data.entity.name}</h2>
                              <p>
                                {detail.data.entity.role || "Role unavailable"}
                              </p>
                              {detail.data.entity.email && (
                                <a
                                  className="person-email"
                                  href={`mailto:${detail.data.entity.email}`}
                                >
                                  <Mail size={12} />
                                  {detail.data.entity.email}
                                </a>
                              )}
                              <div className="profile-badges">
                                <Badge
                                  tone={detail.data.manager ? "teal" : "amber"}
                                >
                                  {detail.data.manager
                                    ? label(
                                        detail.data.manager.review_status ===
                                          "accepted" ||
                                          detail.data.manager.origin ===
                                            "analyst"
                                          ? "reviewed"
                                          : detail.data.manager.origin ===
                                              "model"
                                            ? "inferred"
                                            : "source",
                                      )
                                    : "Manager unresolved"}
                                </Badge>
                                <button
                                  className="text-button"
                                  onClick={() => {
                                    setFocus(selected);
                                    setView("graph");
                                  }}
                                >
                                  <LocateFixed size={12} /> Focus
                                </button>
                              </div>
                            </div>
                            {detail.data.ancestors?.length > 0 && (
                              <div
                                className="ancestor-path"
                                aria-label="Reporting ancestors"
                              >
                                {detail.data.ancestors.map((person) => (
                                  <span key={person.id}>
                                    <button
                                      onClick={() => {
                                        selectPerson(person.id);
                                        setFocus(person.id);
                                      }}
                                    >
                                      {person.name}
                                    </button>
                                    <ChevronRight size={11} />
                                  </span>
                                ))}
                              </div>
                            )}
                            <nav
                              className="inspector-tabs"
                              aria-label="Person detail sections"
                            >
                              {(
                                ["evidence", "review", "activity"] as const
                              ).map((tab) => (
                                <button
                                  key={tab}
                                  className={drawerTab === tab ? "active" : ""}
                                  onClick={() =>
                                    tab === "review"
                                      ? openReviewForm()
                                      : setDrawerTab(tab)
                                  }
                                >
                                  {tab === "activity"
                                    ? `Activity${detail.data?.history?.length ? ` (${detail.data.history.length})` : ""}`
                                    : label(tab)}
                                </button>
                              ))}
                            </nav>
                            <div className="inspector-content">
                              {drawerTab === "evidence" && (
                                <>
                                  {selectedEvidence.length > 0 && (
                                    <div className="inspector-next-step">
                                      <p>
                                        Read the source material for the
                                        selected relationship before deciding
                                        whether to review it.
                                      </p>
                                      <button
                                        className="button next-action compact"
                                        onClick={() =>
                                          document
                                            .getElementById(
                                              "person-relationship-evidence",
                                            )
                                            ?.scrollIntoView({
                                              block: "start",
                                              behavior: window.matchMedia(
                                                "(prefers-reduced-motion: reduce)",
                                              ).matches
                                                ? "auto"
                                                : "smooth",
                                            })
                                        }
                                      >
                                        Read evidence <ArrowRight size={14} />
                                      </button>
                                    </div>
                                  )}
                                  <section className="manager-section">
                                    <div className="section-label">
                                      PRIMARY MANAGER
                                    </div>
                                    {detail.data.manager ? (
                                      <button
                                        className="manager-link"
                                        onClick={() => {
                                          selectPerson(
                                            detail.data!.manager!.object,
                                          );
                                          setFocus(
                                            detail.data!.manager!.object,
                                          );
                                        }}
                                      >
                                        <span className="avatar small-avatar">
                                          {initials(
                                            detail.data.manager.object_name ||
                                              detail.data.manager.object,
                                          )}
                                        </span>
                                        <span>
                                          <strong>
                                            {detail.data.manager.object_name ||
                                              detail.data.manager.object}
                                          </strong>
                                          <small>
                                            {label(detail.data.manager.origin)}{" "}
                                            ·{" "}
                                            {label(
                                              detail.data.manager
                                                .reporting_type || "primary",
                                            )}
                                          </small>
                                        </span>
                                        <ArrowUpRight size={14} />
                                      </button>
                                    ) : (
                                      <div className="notice">
                                        <CircleHelp size={16} />
                                        <span>
                                          {label(
                                            detail.data.unresolved_reason ||
                                              "insufficient evidence",
                                          )}
                                          . Review available candidates or
                                          assign a manager using an attributed
                                          source.
                                        </span>
                                      </div>
                                    )}
                                  </section>
                                  {allAssertions.length > 0 && (
                                    <section>
                                      <div className="section-label">
                                        RELATIONSHIPS & ALTERNATIVES{" "}
                                        <span>{allAssertions.length}</span>
                                      </div>
                                      <div className="assertion-list">
                                        {allAssertions.map((assertion) => (
                                          <button
                                            key={assertion.id}
                                            className={`assertion-option ${assertion.id === activeAssertion?.id ? "active" : ""}`}
                                            onClick={() =>
                                              setAssertionId(assertion.id)
                                            }
                                          >
                                            <span>
                                              <strong>
                                                {assertion.object_name ||
                                                  assertion.object}
                                              </strong>
                                              <small>
                                                {label(assertion.origin)} ·{" "}
                                                {assertion.selected
                                                  ? "selected"
                                                  : label(
                                                      assertion.review_status,
                                                    )}
                                                {assertion.reporting_type ===
                                                "matrix"
                                                  ? " · matrix"
                                                  : ""}
                                              </small>
                                            </span>
                                            {assertion.raw_score !== null &&
                                            assertion.raw_score !==
                                              undefined ? (
                                              <span className="raw-score">
                                                {assertion.raw_score.toFixed(2)}
                                                <small>raw score</small>
                                              </span>
                                            ) : (
                                              <Badge>
                                                {assertion.origin === "analyst"
                                                  ? "Analyst"
                                                  : "Source"}
                                              </Badge>
                                            )}
                                          </button>
                                        ))}
                                      </div>
                                      {activeAssertion && (
                                        <>
                                          <div className="assertion-scope">
                                            {activeAssertion.valid_from ||
                                            activeAssertion.valid_to
                                              ? `${activeAssertion.valid_from || "Unknown start"} → ${activeAssertion.valid_to || "Open ended"}`
                                              : "Undated relationship"}{" "}
                                            ·{" "}
                                            {label(
                                              activeAssertion.reporting_type ||
                                                "primary",
                                            )}
                                          </div>
                                          {activeAssertion.origin === "model" &&
                                            (activeAssertion.valid_from ||
                                              activeAssertion.valid_to) && (
                                              <p className="small muted">
                                                Model dates describe observation
                                                coverage, not verified
                                                employment start or end dates.
                                              </p>
                                            )}
                                          {activeAssertion.reporting_type ===
                                            "matrix" && (
                                            <p className="small muted">
                                              Matrix reporting is shown
                                              read-only. This workflow reviews
                                              primary managers.
                                            </p>
                                          )}
                                          {activeAssertion.raw_score !== null &&
                                            activeAssertion.raw_score !==
                                              undefined && (
                                              <p className="score-note">
                                                Raw model score, not a
                                                probability. Accuracy and
                                                calibration remain unvalidated.
                                              </p>
                                            )}
                                          <div className="review-shortcuts">
                                            <button
                                              className="button compact secondary"
                                              disabled={
                                                historical ||
                                                Boolean(busy) ||
                                                activeAssertion.reporting_type ===
                                                  "matrix" ||
                                                activeAssertion.review_status ===
                                                  "accepted"
                                              }
                                              onClick={() =>
                                                prepareReview(
                                                  "accept",
                                                  activeAssertion,
                                                )
                                              }
                                            >
                                              <Check size={13} /> Accept
                                            </button>
                                            <button
                                              className="button compact secondary"
                                              disabled={
                                                historical ||
                                                Boolean(busy) ||
                                                activeAssertion.reporting_type ===
                                                  "matrix" ||
                                                activeAssertion.review_status ===
                                                  "rejected"
                                              }
                                              onClick={() =>
                                                prepareReview(
                                                  "reject",
                                                  activeAssertion,
                                                )
                                              }
                                            >
                                              <X size={13} /> Reject
                                            </button>
                                          </div>
                                        </>
                                      )}
                                    </section>
                                  )}
                                  <section
                                    id="person-relationship-evidence"
                                    data-evidence
                                  >
                                    <div className="section-label">
                                      {activeAssertion
                                        ? "RELATIONSHIP EVIDENCE"
                                        : "AVAILABLE EVIDENCE"}
                                      <span>{selectedEvidence.length}</span>
                                    </div>
                                    {selectedEvidence.map((evidence) => (
                                      <EvidenceCard
                                        key={evidence.id}
                                        evidence={evidence}
                                      />
                                    ))}
                                    {selectedEvidence.length === 0 && (
                                      <p className="small muted">
                                        {activeAssertion
                                          ? "No supporting evidence is attached to this relationship. Verify a source before accepting it."
                                          : "No relationship evidence is available for this person. Leave the manager unresolved unless you can cite a source."}
                                      </p>
                                    )}
                                    <button
                                      className="button next-action compact full-width"
                                      disabled={Boolean(busy)}
                                      onClick={
                                        historical
                                          ? () => {
                                              setSnapshot("");
                                              setDrawerTab("evidence");
                                            }
                                          : openReviewForm
                                      }
                                    >
                                      {historical
                                        ? "Return to latest to review"
                                        : activeAssertion
                                          ? "Review relationship"
                                          : "Set a verified manager"}{" "}
                                      <ArrowRight size={14} />
                                    </button>
                                  </section>
                                  <section>
                                    <div className="section-label">
                                      OBSERVED COMMUNICATION
                                    </div>
                                    <div className="person-metrics">
                                      <div>
                                        <strong>
                                          {detail.data.metrics?.breadth ?? "—"}
                                        </strong>
                                        <span>Counterparties</span>
                                      </div>
                                      <div>
                                        <strong>
                                          {detail.data.metrics?.sent ?? "—"}
                                        </strong>
                                        <span>Sent</span>
                                      </div>
                                      <div>
                                        <strong>
                                          {detail.data.metrics?.cross_unit ??
                                            "—"}
                                        </strong>
                                        <span>Cross-unit</span>
                                      </div>
                                    </div>
                                    <p className="small muted">
                                      Communication measures describe observed
                                      traffic; they do not prove authority or
                                      influence.
                                    </p>
                                  </section>
                                  {detail.data.children?.length > 0 && (
                                    <section>
                                      <div className="section-label">
                                        DIRECT REPORTS{" "}
                                        <span>
                                          {detail.data.children.length}
                                        </span>
                                      </div>
                                      <div className="report-list">
                                        {detail.data.children.map((person) => (
                                          <button
                                            key={person.id}
                                            onClick={() =>
                                              selectPerson(person.id)
                                            }
                                          >
                                            <span>{person.name}</span>
                                            <ChevronRight size={13} />
                                          </button>
                                        ))}
                                      </div>
                                    </section>
                                  )}
                                </>
                              )}
                              {drawerTab === "review" && (
                                <form
                                  className="review-form"
                                  onSubmit={saveReview}
                                >
                                  <div className="section-label">
                                    RECORD AN ANALYST DECISION
                                  </div>
                                  <p className="small muted">
                                    Corrections are versioned and attributed.
                                    Model scores are not copied onto analyst
                                    decisions.
                                  </p>
                                  {historical && (
                                    <div className="notice">
                                      <span>
                                        Reviews can be saved in the latest
                                        snapshot.
                                      </span>
                                      <button
                                        type="button"
                                        className="button next-action compact"
                                        onClick={() => {
                                          setSnapshot("");
                                          setDrawerTab("evidence");
                                        }}
                                      >
                                        Open latest <ArrowRight size={13} />
                                      </button>
                                    </div>
                                  )}
                                  <label>
                                    Action
                                    <select
                                      value={reviewAction}
                                      onChange={(event) =>
                                        setReviewAction(event.target.value)
                                      }
                                    >
                                      <option
                                        value="accept"
                                        disabled={
                                          !allAssertions.some(
                                            (item) =>
                                              item.reporting_type !== "matrix",
                                          )
                                        }
                                      >
                                        Accept selected relationship
                                      </option>
                                      <option
                                        value="reject"
                                        disabled={
                                          !allAssertions.some(
                                            (item) =>
                                              item.reporting_type !== "matrix",
                                          )
                                        }
                                      >
                                        Reject selected relationship
                                      </option>
                                      <option value="replace">
                                        Set / change primary manager
                                      </option>
                                      {undoEvent && (
                                        <option value="undo">
                                          Undo previous review
                                        </option>
                                      )}
                                    </select>
                                  </label>
                                  {(reviewAction === "accept" ||
                                    reviewAction === "reject") && (
                                    <label>
                                      Relationship
                                      <select
                                        value={
                                          activeAssertion?.reporting_type ===
                                          "matrix"
                                            ? ""
                                            : activeAssertion?.id || ""
                                        }
                                        onChange={(event) =>
                                          setAssertionId(event.target.value)
                                        }
                                      >
                                        <option value="" disabled>
                                          No relationship selected
                                        </option>
                                        {allAssertions
                                          .filter(
                                            (assertion) =>
                                              assertion.reporting_type !==
                                              "matrix",
                                          )
                                          .map((assertion) => (
                                            <option
                                              key={assertion.id}
                                              value={assertion.id}
                                            >
                                              {assertion.object_name ||
                                                assertion.object}{" "}
                                              · {label(assertion.origin)}
                                            </option>
                                          ))}
                                      </select>
                                    </label>
                                  )}
                                  {reviewAction === "replace" && (
                                    <>
                                      <label>
                                        Find manager
                                        <input
                                          placeholder="Search name, role, email"
                                          value={managerSearch}
                                          onChange={(event) =>
                                            setManagerSearch(event.target.value)
                                          }
                                        />
                                      </label>
                                      <label>
                                        New manager
                                        <select
                                          required
                                          value={managerId}
                                          onChange={(event) =>
                                            setManagerId(event.target.value)
                                          }
                                        >
                                          <option value="">
                                            Select a person
                                          </option>
                                          {managerOptions.data?.items
                                            .filter(
                                              (person) =>
                                                person.id !== selected,
                                            )
                                            .map((person) => (
                                              <option
                                                value={person.id}
                                                key={person.id}
                                              >
                                                {person.name}
                                                {person.role
                                                  ? ` · ${person.role}`
                                                  : ""}
                                              </option>
                                            ))}
                                        </select>
                                      </label>
                                      {managerOptions.loading && (
                                        <Spinner text="Searching managers…" />
                                      )}
                                      <ErrorBox
                                        message={managerOptions.error}
                                      />
                                      {managerOptions.error && (
                                        <button
                                          type="button"
                                          className="button next-action compact"
                                          onClick={managerOptions.retry}
                                        >
                                          Retry manager search{" "}
                                          <RotateCcw size={13} />
                                        </button>
                                      )}
                                      {managerOptions.data &&
                                        !managerOptions.loading &&
                                        managerOptions.data.items.filter(
                                          (person) => person.id !== selected,
                                        ).length === 0 && (
                                          <div className="notice review-missing">
                                            <span>
                                              {managerSearch
                                                ? "No other people match this search."
                                                : "No other people are available on this page. A manager must be a different person in the dataset."}
                                            </span>
                                            {managerSearch && (
                                              <button
                                                type="button"
                                                className="button next-action compact"
                                                onClick={() =>
                                                  setManagerSearch("")
                                                }
                                              >
                                                Clear manager search
                                              </button>
                                            )}
                                          </div>
                                        )}
                                      <div className="date-fields">
                                        <label>
                                          Valid from
                                          <input
                                            type="date"
                                            value={validFrom}
                                            onChange={(event) =>
                                              setValidFrom(event.target.value)
                                            }
                                          />
                                        </label>
                                        <label>
                                          Valid until
                                          <input
                                            type="date"
                                            min={validFrom || undefined}
                                            value={validTo}
                                            onChange={(event) =>
                                              setValidTo(event.target.value)
                                            }
                                          />
                                        </label>
                                      </div>
                                      <p className="small muted">
                                        Dates optional. End date excluded; blank
                                        dates remain explicitly undated.
                                      </p>
                                    </>
                                  )}
                                  <label>
                                    Reason / source reference
                                    <textarea
                                      required
                                      minLength={3}
                                      rows={4}
                                      placeholder="What did you verify, and where?"
                                      value={reason}
                                      onChange={(event) =>
                                        setReason(event.target.value)
                                      }
                                    />
                                  </label>
                                  <button
                                    className="button primary full-width"
                                    type="submit"
                                    disabled={
                                      historical ||
                                      Boolean(busy) ||
                                      !reason.trim() ||
                                      ((reviewAction === "accept" ||
                                        reviewAction === "reject") &&
                                        (!activeAssertion ||
                                          activeAssertion.reporting_type ===
                                            "matrix")) ||
                                      (reviewAction === "replace" && !managerId)
                                    }
                                  >
                                    {busy === "review" ? (
                                      <Loader2 size={15} className="spin" />
                                    ) : (
                                      <ShieldCheck size={15} />
                                    )}
                                    {reviewAction === "undo"
                                      ? "Undo review"
                                      : "Save review"}
                                  </button>
                                </form>
                              )}
                              {drawerTab === "activity" && (
                                <>
                                  <div className="section-label">
                                    DECISION HISTORY
                                  </div>
                                  {detail.data.history?.length ? (
                                    detail.data.history.map((event, index) => (
                                      <article
                                        className="history-item"
                                        key={String(
                                          event.id || event.event_id || index,
                                        )}
                                      >
                                        <div>
                                          <Badge
                                            tone={
                                              event.action === "undo"
                                                ? ""
                                                : "teal"
                                            }
                                          >
                                            {label(event.action)}
                                          </Badge>
                                          <time>
                                            {event.created_at
                                              ? displayDate(event.created_at)
                                              : "Recorded"}
                                          </time>
                                        </div>
                                        <p>
                                          {event.reason || "No reason recorded"}
                                        </p>
                                        {event.action !== "undo" &&
                                          !event.undone &&
                                          (event.id || event.event_id) && (
                                            <button
                                              className="text-button"
                                              disabled={
                                                historical || Boolean(busy)
                                              }
                                              onClick={() =>
                                                prepareReview(
                                                  "undo",
                                                  undefined,
                                                  event,
                                                )
                                              }
                                            >
                                              <RotateCcw size={12} /> Undo this
                                              review
                                            </button>
                                          )}
                                      </article>
                                    ))
                                  ) : (
                                    <div className="panel-empty">
                                      <Clock3 size={24} />
                                      <h3>No reviews yet</h3>
                                      <p>
                                        No analyst decisions have been recorded
                                        for this person. Inspect their evidence
                                        before making a review.
                                      </p>
                                      <button
                                        className="button next-action compact"
                                        onClick={() => setDrawerTab("evidence")}
                                      >
                                        Inspect evidence{" "}
                                        <ArrowRight size={14} />
                                      </button>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          </>
                        )}
                      </>
                    )}
                  </aside>
                </section>
                <footer className="workspace-footer">
                  <span>
                    <span className="live-dot" /> Snapshot{" "}
                    {String(
                      snapshot || workspace?.active_snapshot || "none",
                    ).slice(0, 12)}{" "}
                    · Revision {visibleWorkspace?.revision ?? version}
                  </span>
                  <span>Evidence first. Unknowns preserved.</span>
                </footer>
              </>
            )}
          </>
        )}
      </main>
      {modal === "run" && (
        <Modal
          title="Run baseline inference"
          description="Propose direct-reporting candidates from available communication evidence. Existing analyst corrections are preserved."
          onClose={() => setModal(null)}
        >
          <form onSubmit={runInference}>
            <div className="notice">
              <SlidersHorizontal size={17} />
              <span>
                This scorer is uncalibrated. Thresholds control candidate
                selection, not statistical confidence. Independent labels are
                required for accuracy claims.
              </span>
            </div>
            <label>
              Time scope
              <input
                type="date"
                value={asOf}
                onChange={(event) => setAsOf(event.target.value)}
              />
              <span className="field-hint">
                Leave blank for undated exploration across available records.
              </span>
            </label>
            <div className="date-fields">
              <label>
                Minimum raw score
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={threshold}
                  onChange={(event) => setThreshold(Number(event.target.value))}
                  required
                />
              </label>
              <label>
                Alternative score margin
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={margin}
                  onChange={(event) => setMargin(Number(event.target.value))}
                  required
                />
              </label>
            </div>
            <ErrorBox message={error} />
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => setModal(null)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={Boolean(busy)}>
                {busy === "infer" ? (
                  <Loader2 size={16} className="spin" />
                ) : (
                  <Play size={14} />
                )}{" "}
                Run & create snapshot
              </button>
            </div>
          </form>
        </Modal>
      )}
      {modal === "export" && (
        <Modal
          title="Export this snapshot"
          description="Keep the relationships, uncertainty, and source context together."
          onClose={() => setModal(null)}
        >
          <div className="export-options">
            <button disabled={Boolean(busy)} onClick={() => download("json")}>
              <Braces size={23} />
              <span>
                <strong>Canonical package</strong>
                <small>
                  JSON · identities, assertions, evidence, review history
                </small>
              </span>
              <ArrowDownToLine size={17} />
            </button>
            <button disabled={Boolean(busy)} onClick={() => download("csv")}>
              <Table2 size={23} />
              <span>
                <strong>Organization chart</strong>
                <small>
                  CSV · lossy projection; excludes alternative evidence &
                  history
                </small>
              </span>
              <ArrowDownToLine size={17} />
            </button>
            <button disabled={Boolean(busy)} onClick={() => download("report")}>
              <FileText size={23} />
              <span>
                <strong>Analyst report</strong>
                <small>
                  Markdown · scope, findings, unresolved items & provenance
                </small>
              </span>
              <ArrowDownToLine size={17} />
            </button>
          </div>
          <ErrorBox message={error} />
          {busy === "export" && <Spinner text="Preparing export…" />}
        </Modal>
      )}
      {modal === "about" && (
        <Modal
          title="A chart you can question."
          description="Project 4 · Organization Chart Knowledge Graphs"
          onClose={() => setModal(null)}
        >
          <p className="about-copy">
            Organization Atlas connects records and communication patterns with
            an editable reporting view. Every inferred relationship should stay
            attached to its evidence and uncertainty.
          </p>
          <div className="about-feature">
            <Network size={19} />
            <div>
              <strong>Bounded, navigable context</strong>
              <p>
                Zoom from departments or inferred communication groups into
                reporting branches, individual positions, and their connections.
                Breadcrumbs and paged contexts keep the whole corpus reachable;
                each chart page contains at most 200 cards.
              </p>
            </div>
          </div>
          <div className="about-feature">
            <ShieldCheck size={19} />
            <div>
              <strong>Human review, durable history</strong>
              <p>
                Accept, reject, replace, and undo decisions. Snapshot
                comparisons preserve the distinction between model changes and
                organizational changes.
              </p>
            </div>
          </div>
          <div className="about-feature">
            <CircleHelp size={19} />
            <div>
              <strong>Scores are not probabilities</strong>
              <p>
                The baseline is uncalibrated. Fictional data validates software
                behavior; it cannot establish real-world inference accuracy.
              </p>
            </div>
          </div>
          {workspace?.capabilities && (
            <details>
              <summary>
                Current data capabilities <ExternalLink size={12} />
              </summary>
              <dl className="signal-list">
                {Object.entries(workspace.capabilities).map(([key, value]) => (
                  <div key={key}>
                    <dt>{label(key)}</dt>
                    <dd>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </Modal>
      )}
    </div>
  );
}
