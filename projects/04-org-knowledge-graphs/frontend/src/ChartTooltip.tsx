import { useLayoutEffect, useRef, useState } from "react";
import type { Graph } from "./types";
import "./chartTooltip.css";

export type TooltipContent = {
  eyebrow: string;
  title: string;
  subtitle?: string;
  rows: { label: string; value: string }[];
  notice?: string;
  hint: string;
};

export type TooltipNode = {
  name: string;
  kind: "unit" | "group" | "team" | "person" | "unassigned";
  person_count: number;
  unresolved_count?: number;
  role?: string;
  status?: string;
  children_count?: number;
  manager_name?: string | null;
  email?: string;
  expandable: boolean;
};

type Size = { width: number; height: number };
type Point = { x: number; y: number };
const readable = (value: string) => {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};

export function nodeTooltip(
  node: TooltipNode,
  managerName?: string | null,
): TooltipContent {
  const rows: TooltipContent["rows"] = [];
  const kinds = {
    unit: "Department / unit",
    group: "Inferred communication group",
    team: "Reporting branch",
    person: "Individual position",
    unassigned: "Unassigned people",
  };
  if (node.kind === "person") {
    if (managerName || node.manager_name)
      rows.push({
        label: "Reports to",
        value: (managerName || node.manager_name)!,
      });
    if (node.children_count !== undefined)
      rows.push({
        label: "Direct reports",
        value: node.children_count.toLocaleString(),
      });
    if (node.status)
      rows.push({ label: "Status", value: readable(node.status) });
    if (node.email) rows.push({ label: "Email", value: node.email });
  } else {
    rows.push({ label: "People", value: node.person_count.toLocaleString() });
    if (node.unresolved_count !== undefined)
      rows.push({
        label: "Reporting unresolved",
        value: node.unresolved_count.toLocaleString(),
      });
  }
  return {
    eyebrow: kinds[node.kind],
    title: node.name,
    subtitle:
      node.kind === "person" ? node.role || "Position unspecified" : undefined,
    rows,
    notice:
      node.kind === "group"
        ? "Communication patterns suggest this group. It is not a verified formal reporting unit; memberships can overlap."
        : node.kind === "team"
          ? "A presentation group of reporting connections, not an additional formal department."
          : node.kind === "unassigned"
            ? "No membership is recorded for these people in this grouping."
            : undefined,
    hint:
      node.kind === "person"
        ? "Click for evidence · Zoom in or double-click for connections"
        : node.expandable
          ? "Click or zoom in to explore"
          : "No deeper level available",
  };
}

export function edgeTooltip(
  edge: Graph["edges"][number],
  sourceName: string,
  targetName: string,
): TooltipContent {
  const rows: TooltipContent["rows"] = [
    { label: "Reports to", value: sourceName },
    { label: "Origin", value: readable(edge.origin) },
    { label: "Review", value: readable(edge.review_status) },
    { label: "Calibration", value: readable(edge.calibration_status) },
  ];
  if (edge.raw_score !== null && Number.isFinite(edge.raw_score))
    rows.push({
      label: "Raw model score",
      value: `${edge.raw_score.toFixed(3)} · not a probability`,
    });
  return {
    eyebrow: "Reporting connection",
    title: targetName,
    rows,
    notice:
      edge.origin === "model"
        ? "Model-inferred reporting link. The raw score is not a calibrated probability."
        : undefined,
    hint: "Click the connection to inspect its evidence",
  };
}

/** Anchor and bounds are CSS pixels within the chart, independent of SVG zoom. */
export function tooltipPosition(anchor: Point, bounds: Size, measured: Size) {
  const margin = 8;
  const width = Math.min(
    290,
    Math.max(0, bounds.width - margin * 2),
    measured.width,
  );
  const height = Math.min(
    Math.max(0, bounds.height - margin * 2),
    measured.height,
  );
  const preferLeft = anchor.x + 16 + width > bounds.width - margin;
  const preferAbove = anchor.y + 18 + height > bounds.height - margin;
  const clamp = (value: number, maximum: number) =>
    Math.max(0, Math.min(Math.max(margin, value), Math.max(0, maximum)));
  return {
    left: clamp(
      preferLeft ? anchor.x - width - 16 : anchor.x + 16,
      bounds.width - width - margin,
    ),
    top: clamp(
      preferAbove ? anchor.y - height - 18 : anchor.y + 18,
      bounds.height - height - margin,
    ),
    width,
    maxHeight: Math.max(0, bounds.height - margin * 2),
  };
}

export default function ChartTooltip({
  content,
  anchor,
  bounds,
  id = "chart-tooltip",
}: {
  content: TooltipContent | null;
  anchor: Point;
  bounds: Size;
  id?: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<Size>({ width: 290, height: 240 });
  const width = Math.min(290, Math.max(0, bounds.width - 16));
  useLayoutEffect(() => {
    if (!element.current || !content) return;
    const rect = element.current.getBoundingClientRect();
    setMeasured((previous) =>
      previous.width === rect.width && previous.height === rect.height
        ? previous
        : { width: rect.width, height: rect.height },
    );
  }, [content, width, bounds.height]);
  if (!content || bounds.width < 20 || bounds.height < 20) return null;
  return (
    <div
      ref={element}
      id={id}
      role="tooltip"
      className="chart-tooltip"
      style={{ ...tooltipPosition(anchor, bounds, measured), width }}
    >
      <p className="chart-tooltip-kind">{content.eyebrow}</p>
      <strong className="chart-tooltip-title">{content.title}</strong>
      {content.subtitle && (
        <p className="chart-tooltip-subtitle">{content.subtitle}</p>
      )}
      {content.rows.length > 0 && (
        <dl>
          {content.rows.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {content.notice && (
        <p className="chart-tooltip-notice">{content.notice}</p>
      )}
      <p className="chart-tooltip-hint">{content.hint}</p>
    </div>
  );
}
