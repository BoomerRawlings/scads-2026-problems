import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { MAX_INTAKE_BYTES, validatePeople } from "./intakeModel";
import { readIntakeSession, retryDelay, writeIntakeSession, type IntakeSession } from "./intakeSession";
import type { IntakeJob, IntakeMode } from "./intakeTypes";
import type { Workspace } from "./types";

const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause);
const missing = (cause: unknown) => cause instanceof ApiError && cause.status === 404;

export function useIntakeController(initialMode: IntakeMode | null, onComplete: (workspace: Workspace) => void) {
  const [mode, setMode] = useState<IntakeMode | null>(initialMode);
  const [people, setPeople] = useState("10000");
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<IntakeJob | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disconnected, setDisconnected] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [replace, setReplace] = useState(false);
  const [changedWorkspace, setChangedWorkspace] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);
  const recovery = useRef<IntakeSession | null>(null);
  const operation = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const busy = requesting || job?.status === "profiling" || job?.status === "building";

  function remember(value: IntakeSession | null) {
    recovery.current = value;
    writeIntakeSession(value);
  }
  function accept(next: IntakeJob, token = recovery.current) {
    if (next.status === "cancelled") {
      remember(null); setJob(null); setUncertain(false);
      setNotice("This preview was cancelled. Choose a source to start again.");
      return;
    }
    setJob(next); setMode(next.mode); setUncertain(false); setDisconnected(false);
    if (token) remember({ ...token, id: next.id });
  }
  function expired() {
    remember(null); setJob(null); setReplace(false); setUncertain(false); setDisconnected(false);
    setError("");
    setNotice("The temporary preview is no longer available. Your saved workspace is still available. Inspect the source again to continue.");
  }
  async function lookup(token: IntakeSession, signal?: AbortSignal) {
    return api<IntakeJob>(token.id ? `/intake/${encodeURIComponent(token.id)}` : `/intake/request/${encodeURIComponent(token.requestKey)}`, { signal });
  }
  function begin() {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    const current = ++epoch.current;
    return { controller, valid: () => !controller.signal.aborted && epoch.current === current };
  }

  useEffect(() => {
    const token = readIntakeSession();
    if (!token) return;
    const { controller, valid } = begin();
    recovery.current = token;
    setMode(token.mode);
    if (token.people) setPeople(String(token.people));
    setRequesting(true);
    lookup(token, controller.signal).then(next => {
      if (valid()) { accept(next, token); setNotice("Resumed your dataset walkthrough."); }
    }).catch(cause => {
      if (!valid()) return;
      if (missing(cause)) expired();
      else { setUncertain(true); setDisconnected(true); setError("Couldn’t reconnect to your walkthrough. Check progress to resume it."); }
    }).finally(() => { if (valid()) setRequesting(false); });
    return () => { controller.abort(); epoch.current += 1; };
  }, []);

  useEffect(() => () => { operation.current?.abort(); epoch.current += 1; }, []);

  useEffect(() => {
    if (!job || !["profiling", "building"].includes(job.status)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const id = job.id;
    async function poll() {
      try {
        const next = await api<IntakeJob>(`/intake/${encodeURIComponent(id)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        accept(next); setError(""); attempts = 0;
        if (["profiling", "building"].includes(next.status)) timer = setTimeout(poll, 650);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (missing(cause)) { expired(); return; }
        setDisconnected(true);
        setError("Connection interrupted. We’re reconnecting automatically; your processing may still be running.");
        timer = setTimeout(poll, retryDelay(attempts++));
      }
    }
    timer = setTimeout(poll, 300);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job?.id, job?.status, pollVersion]);

  async function recover() {
    if (!recovery.current || requesting) return;
    const { controller, valid } = begin();
    setRequesting(true); setError("");
    try { const next = await lookup(recovery.current, controller.signal); if (valid()) accept(next); }
    catch (cause) {
      if (!valid()) return;
      if (missing(cause)) expired();
      else { setUncertain(true); setError(`Couldn’t reconnect. ${message(cause)}`); }
    } finally { if (valid()) setRequesting(false); }
  }

  async function discard() {
    const current = job || (recovery.current ? await lookup(recovery.current).catch(cause => {
      if (missing(cause)) return null;
      throw cause;
    }) : null);
    if (current && ["profiling", "ready_for_review", "failed"].includes(current.status)) {
      try { await api(`/intake/${encodeURIComponent(current.id)}`, { method: "DELETE" }); }
      catch (cause) { if (!missing(cause)) throw cause; }
    } else if (current?.status === "building") {
      accept(current); throw new Error("The workspace is still being built. Reconnect to its progress before continuing.");
    }
    remember(null);
  }

  async function reset(nextMode: IntakeMode | null = null) {
    if (requesting || job?.status === "building") return;
    const { valid } = begin();
    setRequesting(true); setError("");
    try {
      await discard();
      if (valid()) { setJob(null); setMode(nextMode); setReplace(false); setNotice(""); setUncertain(false); setDisconnected(false); setChangedWorkspace(false); }
    } catch (cause) { if (valid()) setError(message(cause)); }
    finally { if (valid()) setRequesting(false); }
  }

  async function inspect() {
    if (!mode || busy || uncertain) return;
    const validation = mode === "synthetic" ? validatePeople(people) : !file ? "Choose a dataset to inspect." : file.size > MAX_INTAKE_BYTES ? "This browser accepts files up to 100 MiB. Choose a smaller file, or use the command-line importer for a larger archive." : null;
    if (validation) { setError(validation); return; }
    const { controller, valid } = begin();
    setRequesting(true); setError(""); setNotice(""); setReplace(false); setChangedWorkspace(false);
    const token: IntakeSession = { requestKey: crypto.randomUUID(), mode, people: mode === "synthetic" ? Number(people) : undefined };
    try {
      await discard();
      if (!valid()) return;
      setJob(null); remember(token);
      let next: IntakeJob;
      if (mode === "import") {
        const body = new FormData(); body.set("file", file!); body.set("request_key", token.requestKey);
        next = await api<IntakeJob>("/intake/import", { method: "POST", body, signal: controller.signal });
      } else {
        next = await api<IntakeJob>("/intake/synthetic", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ people: Number(people), request_key: token.requestKey }), signal: controller.signal });
      }
      if (valid()) accept(next, token);
    } catch (cause) {
      if (!valid()) return;
      setError(message(cause));
      // Never post a second preparation just because the first response was lost.
      try { const next = await lookup(token, controller.signal); if (valid()) { accept(next, token); setError(""); } }
      catch (recoveryError) {
        if (!valid()) return;
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && missing(recoveryError)) remember(null);
        else { remember(token); setUncertain(true); setError("The inspection request could not be confirmed. Check progress to recover it before starting another."); }
      }
    } finally { if (valid()) setRequesting(false); }
  }

  async function build() {
    if (!job || busy || job.workspace.package_requires_empty || (job.workspace.requires_replacement && !replace)) return;
    if (job.status !== "ready_for_review" && !(job.status === "failed" && job.retryable)) return;
    const { controller, valid } = begin();
    setRequesting(true); setError(""); setNotice("");
    try {
      const next = await api<IntakeJob>(`/intake/${encodeURIComponent(job.id)}/build`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ base_revision: job.workspace.base_revision, replace }), signal: controller.signal });
      if (valid()) accept(next);
    } catch (cause) {
      if (!valid()) return;
      if (missing(cause)) { expired(); return; }
      setError(message(cause));
      try {
        const next = await api<IntakeJob>(`/intake/${encodeURIComponent(job.id)}`, { signal: controller.signal });
        if (!valid()) return;
        if (next.workspace.base_revision !== job.workspace.base_revision) {
          setReplace(false); setNotice("The workspace changed. Review the current replacement choice before continuing.");
        }
        accept(next);
        if (["ready", "building"].includes(next.status)) setError("");
      } catch (retryError) { if (valid()) { if (missing(retryError)) expired(); else { setUncertain(true); setError("The build response was interrupted. Check progress before retrying."); } } }
    } finally { if (valid()) setRequesting(false); }
  }

  async function openWorkspace(checkResult = false) {
    if (requesting || job?.status === "building" || job?.status === "profiling") return;
    const { controller, valid } = begin();
    setRequesting(true); setError("");
    try {
      const current = await api<Workspace>("/workspace", { signal: controller.signal });
      if (!valid()) return;
      if (!current.corpus) { setError("There is no saved dataset to open. Choose a source to build a workspace."); setChangedWorkspace(true); return; }
      if (checkResult && !changedWorkspace && job?.result && (current.revision !== job.result.revision || current.active_snapshot !== job.result.active_snapshot)) {
        setChangedWorkspace(true); setNotice("The saved workspace changed in another session. Continue to its current version, or choose another dataset."); return;
      }
      await discard();
      if (valid()) { remember(null); onComplete(current); }
    } catch (cause) { if (valid()) setError(message(cause)); }
    finally { if (valid()) setRequesting(false); }
  }

  return { mode, setMode, people, setPeople, file, setFile, job, requesting, busy, error, setError, notice, disconnected, uncertain, replace, setReplace, changedWorkspace, inspect, build, reset, recover, openWorkspace, reconnect: () => { setPollVersion(v => v + 1); if (uncertain) void recover(); } };
}
