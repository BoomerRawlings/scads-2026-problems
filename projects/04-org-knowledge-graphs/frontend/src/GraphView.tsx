import { useMemo, useRef, useState, useEffect } from "react";
import { Focus, Minus, Plus, Maximize2, LocateFixed } from "./icons";
import type { Graph } from "./types";
import { initials, label } from "./api";
import { layoutGraph } from "./layout";
export default function GraphView({
  graph,
  selected,
  onSelect,
  onFocus,
  focus,
  onReset,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string) => void;
  onFocus: () => void;
  focus: string | null;
  onReset: () => void;
}) {
  const layout = useMemo(() => layoutGraph(graph), [graph]);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [viewport, setViewport] = useState({ width: 640, height: 420 });
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (!svg.current) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setViewport({ width, height });
    });
    observer.observe(svg.current);
    return () => observer.disconnect();
  }, [Boolean(graph.nodes.length)]);
  useEffect(() => {
    const incoming = new Set(graph.edges.map((edge) => edge.target));
    const target =
      layout.nodes.find((node) => node.id === (focus || selected)) ||
      layout.nodes
        .filter((node) => !incoming.has(node.id))
        .sort((a, b) => a.y - b.y || a.x - b.x)[0] ||
      layout.nodes[0];
    const parentId = graph.edges.find((edge) => edge.target === target?.id)?.source;
    const parent = layout.nodes.find((node) => node.id === parentId);
    setZoom(1);
    setPan({
      x: target ? ((parent?.x ?? target.x) + target.x) / 2 + 90 - viewport.width / 2 : 0,
      y: target ? Math.max(0, (parent?.y ?? target.y) - 60) : 0,
    });
    // Preserve the user's pan while selecting a card; recenter only for a new context or resize.
  }, [graph, viewport.width, viewport.height]);
  const byId = new Map(layout.nodes.map((node) => [node.id, node]));
  return (
    <div className="graph-surface">
      <div className="graph-caption">
        <span className="live-dot" /> Primary reporting{" "}
        <span className="caption-divider">/</span>{" "}
        {focus ? "Focused context" : "Organization overview"}
      </div>
      {graph.nodes.length === 0 ? (
        <div className="panel-empty">
          <Focus size={28} />
          <h3>No relationships in this view</h3>
          <p>Try another person or a different time scope.</p>
        </div>
      ) : (
        <svg
          ref={svg}
          className="org-graph"
          aria-label={`Organization graph: ${graph.returned_nodes} people, ${graph.omitted_nodes} outside this view. Drag background to pan; use zoom buttons.`}
          viewBox={`${pan.x} ${pan.y} ${viewport.width / zoom} ${viewport.height / zoom}`}
          onPointerDown={(event) => {
            if ((event.target as Element).closest('[role="button"]')) return;
            drag.current = { x: event.clientX, y: event.clientY };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (!drag.current) return;
            const rect = event.currentTarget.getBoundingClientRect();
            const scale = Math.max(
              viewport.width / zoom / rect.width,
              viewport.height / zoom / rect.height,
            );
            setPan((value) => ({
              x: value.x - (event.clientX - drag.current!.x) * scale,
              y: value.y - (event.clientY - drag.current!.y) * scale,
            }));
            drag.current = { x: event.clientX, y: event.clientY };
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
        >
          <defs>
            <filter
              id="card-shadow"
              x="-15%"
              y="-20%"
              width="130%"
              height="150%"
            >
              <feDropShadow
                dx="0"
                dy="3"
                stdDeviation="3"
                floodOpacity=".045"
              />
            </filter>
          </defs>
          {graph.edges.map((edge) => {
            const source = byId.get(edge.source),
              target = byId.get(edge.target);
            if (!source || !target) return null;
            const x1 = source.x + 90,
              y1 = source.y + 94,
              x2 = target.x + 90,
              y2 = target.y;
            return (
              <path
                key={edge.id}
                d={`M${x1},${y1} V${(y1 + y2) / 2} H${x2} V${y2}`}
                fill="none"
                stroke={edge.origin === "analyst" ? "#327267" : "#b5c0bb"}
                strokeWidth="1.5"
                strokeDasharray={
                  edge.origin === "model" && edge.review_status !== "accepted"
                    ? "5 4"
                    : undefined
                }
              />
            );
          })}
          {layout.nodes.map((node) => {
            const active = node.id === selected;
            const unknown = node.status === "unresolved";
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={`${node.name}, ${node.role || node.type}, ${label(node.status)}. Select to inspect evidence.`}
                aria-pressed={active}
                onClick={() => onSelect(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(node.id);
                  }
                }}
                className={`graph-node ${active ? "active" : ""}`}
                transform={`translate(${node.x},${node.y})`}
              >
                <rect
                  className="node-card"
                  width="180"
                  height="94"
                  rx="8"
                  fill={active ? "#194e46" : "#fffefb"}
                  stroke={active ? "#194e46" : "#d9ded8"}
                  filter="url(#card-shadow)"
                />
                <circle
                  cx="25"
                  cy="28"
                  r="14"
                  fill={active ? "#3a6a62" : "#edf1eb"}
                />
                <text
                  x="25"
                  y="32"
                  textAnchor="middle"
                  fontSize="9"
                  fontWeight="700"
                  fill={active ? "#edf7ef" : "#416158"}
                >
                  {initials(node.name)}
                </text>
                <text
                  x="48"
                  y="25"
                  fontSize="11"
                  fontWeight="650"
                  fill={active ? "#fff" : "#263d35"}
                >
                  {node.name.length > 20
                    ? `${node.name.slice(0, 18)}…`
                    : node.name}
                </text>
                <text
                  x="48"
                  y="40"
                  fontSize="9"
                  fill={active ? "#c0d5cb" : "#788079"}
                >
                  {(node.role || label(node.type)).slice(0, 24)}
                </text>
                <line
                  x1="13"
                  x2="167"
                  y1="57"
                  y2="57"
                  stroke={active ? "#47736a" : "#e9ece6"}
                />
                <circle
                  cx="18"
                  cy="75"
                  r="3"
                  fill={unknown ? "#c58650" : active ? "#a6cab9" : "#5c9280"}
                />
                <text
                  x="27"
                  y="78"
                  fontSize="9"
                  fill={active ? "#dcebe2" : "#737d73"}
                >
                  {unknown
                    ? "Manager unresolved"
                    : label(node.status || "source")}
                </text>
                <text
                  x="163"
                  y="78"
                  textAnchor="end"
                  fontSize="12"
                  fill={active ? "#dcebe2" : "#737d73"}
                >
                  ↗
                </text>
              </g>
            );
          })}
        </svg>
      )}
      <div className="graph-bottom">
        <div className="graph-legend">
          <span>
            <i className="solid-line" /> Source / reviewed
          </span>
          <span>
            <i className="dash-line" /> Inferred
          </span>
          <span>
            <i className="unknown-dot" /> Unresolved
          </span>
        </div>
        <div className="graph-controls">
          <button
            title="Zoom out"
            aria-label="Zoom out"
            onClick={() => setZoom((value) => Math.max(0.5, value / 1.3))}
          >
            <Minus size={16} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            title="Zoom in"
            aria-label="Zoom in"
            onClick={() => setZoom((value) => Math.min(6, value * 1.3))}
          >
            <Plus size={16} />
          </button>
          <button
            title="Fit graph"
            aria-label="Fit graph"
            onClick={() => {
              setZoom(
                Math.min(
                  viewport.width / layout.width,
                  viewport.height / layout.height,
                ),
              );
              setPan({ x: 0, y: 0 });
            }}
          >
            <Maximize2 size={15} />
          </button>
        </div>
      </div>
      <div className="graph-footnote">
        <span>
          {graph.returned_nodes.toLocaleString()} /{" "}
          {graph.total_nodes.toLocaleString()} entities loaded · Drag to explore
          {graph.omitted_nodes
            ? ` · ${graph.omitted_nodes.toLocaleString()} outside this context`
            : ""}
        </span>
        <div>
          {focus && (
            <button className="text-button" onClick={onReset}>
              Show overview
            </button>
          )}
          <button
            className="text-button"
            disabled={!selected}
            onClick={onFocus}
          >
            <LocateFixed size={13} /> Focus selected
          </button>
        </div>
      </div>
    </div>
  );
}
