import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { ArrowRight, Check, FileText, GitBranch, Layers3, LocateFixed, Network, Play, RotateCcw, Users } from "./icons";
import type { IntakeJob, IntakePlan } from "./intakeTypes";
import { formatBytes, INTAKE_STAGES, sourceOrigin } from "./intakeModel";
import { advanceJourney, JOURNEY_DURATIONS, journeyCeiling, journeyPhase, journeySample, journeyServerStatus } from "./intakeJourneyModel";
import "./journey.css";

const icons = [FileText, Users, Network, Layers3, GitBranch, LocateFixed];
const shortLabels = ["Inspect", "Understand", "Preview", "Save", "Connect", "Explore"];
const number = (value: number) => value.toLocaleString();

export type IntakeJourneyProps = {
  job: IntakeJob | null;
  preparing: boolean;
  onAdvance: () => void;
  actionLabel: string;
  actionDisabled: boolean;
  actionHint: string;
  children?: ReactNode;
};

function PauseIcon() {
  return <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="5" y="4" width="3" height="12" rx="1" /><rect x="12" y="4" width="3" height="12" rx="1" /></svg>;
}

export function JourneyGraph({ plan, progress, paused }: { plan: IntakePlan; progress: number; paused: boolean }) {
  const sample = useMemo(() => journeySample(plan), [plan]);
  const byId = new Map(sample.nodes.map((node, index) => [node.id, { ...node, index }]));
  const markerId = useId().replaceAll(":", "");
  const shown = Math.min(sample.nodes.length, Math.floor(progress * (sample.nodes.length + 2)) + 1);
  const activeEdge = Math.min(sample.edges.length - 1, Math.floor(Math.max(0, progress - 0.25) / 0.75 * sample.edges.length));
  return (
    <div className={`journey-graph ${paused ? "is-paused" : ""}`}>
      {sample.nodes.length ? <svg viewBox="0 0 600 328" role="img" aria-label={`Source sample: ${sample.nodes.length} records and ${sample.edges.length} relationships. These are source records, not new reporting inferences.`}>
        <defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="context-stroke" /></marker></defs>
        <circle className="journey-orbit" cx="300" cy="164" r="104" />
        {sample.edges.map((edge, index) => {
          const a = byId.get(edge.source)!, b = byId.get(edge.target)!;
          const dx = b.x - a.x, dy = b.y - a.y;
          const distance = Math.max(1, Math.hypot(dx, dy));
          const inset = Math.min(59, distance * 0.22);
          const ax = a.x + dx / distance * inset, ay = a.y + dy / distance * inset;
          const bx = b.x - dx / distance * inset, by = b.y - dy / distance * inset;
          const visible = a.index < shown && b.index < shown;
          return <g key={`${edge.source}:${edge.target}:${index}`} className={`journey-link ${visible ? "is-revealed" : ""} ${index === activeEdge && progress < 1 ? "is-tracing" : ""} ${edge.origin === "model" ? "is-proposal" : ""}`}>
            <path d={`M${ax} ${ay} Q300 164 ${bx} ${by}`} markerEnd={`url(#${markerId})`} pathLength="1" />
            <title>{a.label} → {b.label}: {edge.relation.replaceAll("_", " ")} · {sourceOrigin(edge.origin)}</title>
          </g>;
        })}
        {sample.nodes.map((node, index) => <g key={node.id} transform={`translate(${node.x - 57} ${node.y - 20})`} className={`journey-record ${index < shown ? "is-revealed" : ""} ${index === shown - 1 && progress < 1 ? "is-spotlit" : ""}`}>
          <rect width="114" height="40" rx="10" />
          <circle cx="12" cy="13" r="3" className={node.kind === "person" ? "is-person" : "is-unit"} />
          <text x="21" y="16" className="journey-record-kind">{node.kind.replaceAll("_", " ")}</text>
          <text x="11" y="31" className="journey-record-name">{node.label.length > 17 ? `${node.label.slice(0, 16)}…` : node.label}</text>
          <title>{node.label} · {node.kind}</title>
        </g>)}
      </svg> : <div className="journey-empty-graph"><Network size={32} /><strong>No graph records available</strong><span>Choose a source containing people or communication records.</span></div>}
      <div className="journey-graph-caption"><span><i />{sample.nodes.length} sample records · {sample.edges.length} source links</span><span>Communication ≠ reporting</span></div>
      {sample.edges.some((edge) => edge.origin === "model") && <p className="journey-proposal-key">Dashed amber: imported model proposals, still unverified.</p>}
      {sample.nodes.length > 0 && sample.edges.length === 0 && <p className="journey-proposal-key">No relationships in this sample. The records remain available for inspection.</p>}
      <details className="journey-source-list"><summary>Read sample relationships</summary>{sample.edges.length ? <ul>{sample.edges.map((edge, index) => <li key={index}><strong>{byId.get(edge.source)?.label}</strong> → {byId.get(edge.target)?.label}<span>{edge.relation.replaceAll("_", " ")} · {sourceOrigin(edge.origin)}</span></li>)}</ul> : <p>No source links in this preview.</p>}</details>
    </div>
  );
}

function StageFacts({ job, index }: { job: IntakeJob | null; index: number }) {
  const profile = job?.profile;
  const result = job?.result;
  let facts: [string, string][] = [];
  if (index === 0 && job) facts = [["Source", job.source.format.toUpperCase()], ["Measured size", formatBytes(job.source.bytes)], ["Dataset", job.source.name]];
  if (index === 1 && profile) facts = [["Distinct person records", number(profile.counts.people)], ["Messages", number(profile.counts.messages)], ["Accepted data points", number(profile.counts.data_points)], ["Quality issues", number(profile.quality.issue_count)]];
  if (index === 2 && profile) facts = [["Entities available", number(profile.counts.entities)], ["Supplied assertions", number(profile.counts.assertions)], ["Communication links", number(profile.counts.communication_links)]];
  if (index === 3 && profile) facts = [["Source records", number(profile.counts.data_points)], ["Provenance", "Retained with records"], ["Workspace", job?.workspace.can_reuse ? "Matching dataset reused" : "Current dataset snapshot"]];
  if (index === 4 && profile) facts = [["Communication signals", `${number(profile.counts.messages)} messages`], ["Source relationships", number(profile.counts.assertions)], ["Reporting scores", "Uncalibrated · inspect evidence"]];
  if (index === 5 && result) facts = [["People", number(result.counts.people)], ["Selected reporting links", number(result.counts.selected)], ["Unresolved positions", number(result.counts.unresolved)]];
  if (!facts.length) return <p className="journey-before-copy">Start with your source. We’ll measure its size, count the people and records, then draw a preview for you to review.</p>;
  return <dl className="journey-facts">{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

export default function IntakeJourney({ job, preparing, onAdvance, actionLabel, actionDisabled, actionHint, children }: IntakeJourneyProps) {
  const phase = journeyPhase(job);
  const ceiling = journeyCeiling(job);
  const phaseStart = phase === "prepare" ? 0 : 3;
  const phaseEnd = phase === "prepare" ? 2 : 5;
  const [cursor, setCursor] = useState({ index: phaseStart, elapsed: 0 });
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [reducedMotion, setReducedMotion] = useState(false);
  const generation = useRef("");
  const autoStarted = Boolean(job || preparing);
  const complete = cursor.index === phaseEnd && cursor.elapsed >= JOURNEY_DURATIONS[cursor.index];
  const stopped = paused || reducedMotion || !autoStarted || job?.status === "failed" || job?.status === "cancelled" || complete;
  const index = Math.min(cursor.index, ceiling);
  const duration = JOURNEY_DURATIONS[index];
  const progress = Math.min(1, cursor.elapsed / duration);
  const stage = INTAKE_STAGES[index];
  const actualStage = job?.stages[index];
  const Icon = icons[index];
  const hintId = useId();

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const key = `${job?.id ?? "new"}:${phase}`;
    if (generation.current !== key) {
      generation.current = key;
      setCursor({ index: phaseStart, elapsed: 0 });
      setPaused(false);
    }
  }, [job?.id, phase, phaseStart]);

  useEffect(() => {
    if (reducedMotion) setCursor({ index: Math.min(ceiling, phaseEnd), elapsed: JOURNEY_DURATIONS[Math.min(ceiling, phaseEnd)] });
  }, [reducedMotion, ceiling, phaseEnd]);

  useEffect(() => {
    if (stopped) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const delta = Math.min(250, now - last) * speed;
      last = now;
      if (!document.hidden) setCursor((current) => advanceJourney(current.index, current.elapsed, delta, Math.min(ceiling, phaseEnd)));
    }, 100);
    return () => window.clearInterval(timer);
  }, [stopped, speed, ceiling, phaseEnd]);

  const waiting = autoStarted && !stopped && progress >= 1 && index < phaseEnd;
  const status = journeyServerStatus(job, preparing);
  const beginReplay = () => { setCursor({ index: phaseStart, elapsed: 0 }); setPaused(false); };
  const goToResult = () => { const target = Math.min(ceiling, phaseEnd); setCursor({ index: target, elapsed: JOURNEY_DURATIONS[target] }); };

  return <section className={`intake-journey ${stopped ? "is-paused" : ""} ${reducedMotion ? "reduce-motion" : ""}`} aria-label="Dataset processing workflow">
    <div className="journey-topline"><span className="journey-eyebrow">Your dataset, step by step</span><span className={`journey-server-state ${job?.status === "failed" ? "has-error" : ""}`}><i className={job?.status === "building" || job?.status === "profiling" || preparing ? "is-busy" : ""} />{status}</span></div>
    <div className="journey-route" aria-label="Six steps from source to chart">
      <div className="journey-route-track" aria-hidden="true"><span style={{ width: `${index / 5 * 100}%` }} /></div>
      {INTAKE_STAGES.map((definition, stepIndex) => {
        const StepIcon = icons[stepIndex];
        const actual = job?.stages[stepIndex]?.status ?? "queued";
        const available = stepIndex <= ceiling;
        return <button key={definition.id} type="button" className={`journey-stop ${stepIndex === index ? "is-current" : ""} ${stepIndex < index ? "is-past" : ""}`} disabled={!available} aria-current={stepIndex === index ? "step" : undefined} aria-label={`Step ${stepIndex + 1}: ${definition.label}. ${actual === "complete" ? "Complete" : actual === "skipped" ? "Not needed" : actual === "running" ? "Working" : actual === "error" ? "Needs attention" : "Upcoming"}`} onClick={() => { setCursor({ index: stepIndex, elapsed: 0 }); setPaused(true); }}><span className="journey-stop-icon"><StepIcon size={19} strokeWidth={1.7} />{actual === "complete" || actual === "skipped" ? <i><Check size={9} /></i> : null}</span><span>{shortLabels[stepIndex]}</span></button>;
      })}
    </div>
    <div className="journey-playback"><span>{reducedMotion ? "Reduced motion" : !autoStarted ? "Automatic walkthrough after inspection starts" : complete ? "Walkthrough complete" : paused ? "Walkthrough paused" : waiting ? "Waiting for measured results" : "Automatic walkthrough"}{autoStarted && <small>Step {index + 1} of 6</small>}</span><div>{autoStarted && !reducedMotion && <>
      {complete ? <button type="button" onClick={beginReplay}><RotateCcw size={13} />Replay steps</button> : <button type="button" onClick={() => setPaused((value) => !value)} aria-label={paused ? "Resume walkthrough" : "Pause walkthrough"}>{paused ? <Play size={13} /> : <PauseIcon />}{paused ? "Play" : "Pause"}</button>}
      <button type="button" onClick={() => setSpeed((value) => value === 1 ? 2 : 1)} aria-label={`Walkthrough speed ${speed} times. Change speed.`}>{speed}×</button>
      {!complete && <button type="button" onClick={goToResult}>Skip explanation<ArrowRight size={12} /></button>}
    </>}</div></div>
    <div className="journey-story" key={`${job?.id ?? "new"}:${index}`}>
      <div className="journey-story-copy"><span className="journey-stage-kicker"><Icon size={15} />Step 0{index + 1}</span><h3>{stage.label}</h3><p>{stage.explanation}</p>
        <StageFacts job={job} index={index} />
        {actualStage?.detail && <p className="journey-stage-detail"><Check size={13} />{actualStage.detail}</p>}
      </div>
      {index === 2 && job?.plan ? <JourneyGraph plan={job.plan} progress={reducedMotion ? 1 : progress} paused={stopped} /> : <div className="journey-stage-visual" aria-hidden="true"><div className="journey-visual-rings" /><div className="journey-visual-center"><Icon size={48} strokeWidth={1} /></div><div className="journey-orbit-item item-a"><FileText size={22} /></div><div className="journey-orbit-item item-b"><Users size={22} /></div><div className="journey-orbit-item item-c"><GitBranch size={22} /></div><svg viewBox="0 0 320 244"><path d="M57 52 Q160 35 160 122 M160 122 Q185 168 272 78 M160 122 Q132 195 57 197" /></svg><span>{index === 5 ? "Ready for exploration" : index === 4 ? "Evidence → proposed structure" : index === 3 ? "Records + provenance" : index === 1 ? "People · messages · relationships" : "A clear view of your source"}</span></div>}
    </div>
    <div className="journey-time-track" aria-hidden="true"><span style={{ "--journey-progress": `${progress * 100}%` } as CSSProperties} /></div>
    <div className="journey-next">{children}<div className="journey-next-row"><p id={hintId}><span>Next step</span>{actionHint}</p><button className="journey-continue" type="button" onClick={onAdvance} disabled={actionDisabled} aria-describedby={hintId}>{actionLabel}<ArrowRight size={16} /></button></div></div>
  </section>;
}
