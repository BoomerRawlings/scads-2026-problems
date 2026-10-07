import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, initials, label, query } from "./api";
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  Layers3,
  LocateFixed,
  Maximize2,
  Minus,
  Plus,
} from "./icons";
import type { Graph } from "./types";
import { layoutConnections, nextConnectionBudget } from "./connectionDetail";
import type { ConnectionLayout } from "./connectionDetail";
import ChartTooltip, { nodeTooltip, edgeTooltip } from "./ChartTooltip";
import type { TooltipContent } from "./ChartTooltip";
import { fitCamera, focusCamera, zoomAt, zoomTransition } from "./semanticZoom";
import type { Camera } from "./semanticZoom";
import { useSmoothCamera } from "./useSmoothCamera";
import { createChartCache } from "./chartCache";
import {
  layoutWindow,
  mergePage,
  visibleCards,
  reanchorGridCamera,
} from "./chartWindow";
import { normalizeWheel } from "./scrollIntent";
import type { ScrollMode } from "./scrollIntent";

type ChartNode = {
  id: string;
  name: string;
  kind: "unit" | "group" | "team" | "person" | "unassigned";
  person_count: number;
  unresolved_count?: number;
  role?: string;
  status?: string;
  entity_id?: string;
  manager_id?: string | null;
  manager_name?: string | null;
  email?: string;
  children_count?: number;
  expandable: boolean;
};
type ChartData = {
  snapshot: string;
  total_people: number;
  breadcrumbs: { id: string | null; name: string }[];
  nodes: ChartNode[];
  edges: Graph["edges"];
  total: number;
  offset: number;
  limit: number;
  scope: string | null;
  lens: "formal" | "inferred";
  description: string;
};
type Request = { scope: string | null; offset: number; person?: string };
const short = (value: string, count: number) =>
  value.length > count ? `${value.slice(0, count - 1)}…` : value;

export default function SemanticChart({
  snapshot,
  version,
  limit,
  selected,
  focus,
  onSelect,
  onFocus,
}: {
  snapshot: string;
  version: number;
  limit: number;
  selected: string | null;
  focus: string | null;
  onSelect: (id: string) => void;
  onFocus: (id: string | null) => void;
}) {
  const [lens, setLens] = useState<"formal" | "inferred">("formal");
  const [scrollMode, setScrollMode] = useState<ScrollMode>("zoom");
  const [request, setRequest] = useState<Request>({ scope: null, offset: 0 });
  const [data, setData] = useState<ChartData | null>(null);
  const [connections, setConnections] = useState<Graph | null>(null);
  const [connectionBudget, setConnectionBudget] = useState(Math.max(30, limit));
  const [expanding, setExpanding] = useState(false);
  const expansionBusy = useRef(false);
  const requestGeneration = useRef(0);
  const connectionPositions = useRef<{
    key: string;
    layout: ConnectionLayout;
  } | null>(null);
  const [hover, setHover] = useState<{
    id: string;
    content: TooltipContent;
    anchor: { x: number; y: number };
  } | null>(null);
  const [requestedConnection, setRequestedConnection] = useState<string | null>(
    null,
  );
  const [connection, setConnection] = useState<string | null>(null);
  const [loading, setLoading] = useState(true),
    [pageLoading, setPageLoading] = useState(false),
    [error, setError] = useState("");
  const [viewport, setViewport] = useState({ width: 640, height: 560 });
  const [highlight, setHighlight] = useState<string | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const {
    cameraRef,
    targetRef,
    viewCamera,
    scale,
    moveTo,
    zoomTo,
    panBy,
    stop,
  } = useSmoothCamera(svg, viewport);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pointerStarts = useRef(new Map<number, { x: number; y: number }>());
  const moved = useRef(false);
  const wheelHandler = useRef<(event: WheelEvent) => void>(() => {});
  const pageBusy = useRef(false),
    pending = useRef(false);
  const queuedZoom = useRef<{
    log: number;
    point: { x: number; y: number };
  } | null>(null);
  const transition = useRef<"enter" | "exit" | "direct">("direct");
  const history = useRef(
    new Map<
      string,
      {
        camera: Camera;
        offset: number;
        viewport: { width: number; height: number };
        graph?: Graph;
        connectionLayout?: ConnectionLayout;
        budget?: number;
      }
    >(),
  );
  const previousViewport = useRef(viewport);
  const sceneRef = useRef("");
  const cache = useMemo(
    () =>
      createChartCache<ChartData | Graph>((path, signal) =>
        api(path, { signal }),
      ),
    [],
  );
  const resolvedSnapshot = snapshot || undefined;
  const sceneKey = data
    ? JSON.stringify([data.snapshot, data.lens, data.scope, connection])
    : "";
  const chartPath = (value: Request, grouping = lens) =>
    `/chart${query({ lens: grouping, ...value, limit, snapshot: data?.snapshot || resolvedSnapshot })}`;

  useEffect(() => () => cache.clear(), [cache]);
  useEffect(() => {
    cache.clear();
    history.current.clear();
    sceneRef.current = "";
    queuedZoom.current = null;
    pending.current = true;
    setRequest({ scope: null, offset: 0 });
    setRequestedConnection(null);
    setHighlight(null);
    setHover(null);
    setScrollMode("zoom");
  }, [snapshot, version, cache]);
  useEffect(() => {
    if (focus && focus !== requestedConnection) {
      remember();
      queuedZoom.current = null;
      transition.current = "direct";
      pending.current = true;
      setRequest({ scope: null, offset: 0, person: focus });
      setRequestedConnection(focus);
      setHighlight(`person:${focus}`);
    } else if (!focus && requestedConnection) setRequestedConnection(null);
  }, [focus]);

  useEffect(() => {
    let cancelled = false;
    requestGeneration.current++;
    pending.current = true;
    setHover(null);
    setLoading(true);
    setError("");
    const path = `/chart${query({ lens, ...request, limit, snapshot: resolvedSnapshot })}`;
    cache
      .get(path)
      .then(async (value) => {
        const chart = value as ChartData;
        const saved = requestedConnection
          ? history.current.get(
              JSON.stringify([
                chart.snapshot,
                lens,
                chart.scope,
                requestedConnection,
              ]),
            )
          : undefined;
        const graph = requestedConnection
          ? saved?.graph ||
            ((await cache.get(
              `/graph${query({ focus: requestedConnection, limit: Math.max(30, limit), snapshot: chart.snapshot })}`,
            )) as Graph)
          : null;
        if (cancelled) return;
        if (saved?.connectionLayout && requestedConnection)
          connectionPositions.current = {
            key: JSON.stringify([chart.snapshot, requestedConnection]),
            layout: saved.connectionLayout,
          };
        setData(chart);
        setConnections(graph);
        setConnectionBudget(saved?.budget || Math.max(30, limit));
        setConnection(requestedConnection);
        setLoading(false);
        pending.current = false;
      })
      .catch((cause) => {
        if (!cancelled) {
          queuedZoom.current = null;
          setError(String(cause.message || cause));
          setLoading(false);
          pending.current = false;
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    request,
    lens,
    limit,
    resolvedSnapshot,
    version,
    requestedConnection,
    cache,
  ]);

  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setViewport({ width, height });
    });
    observer.observe(element);
    const wheel = (event: WheelEvent) => wheelHandler.current(event);
    element.addEventListener("wheel", wheel, { passive: false });
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", wheel);
    };
  }, []);

  const displayNodes: ChartNode[] = useMemo(
    () =>
      connection && connections
        ? connections.nodes.map((node) => ({
            ...node,
            id: `person:${node.id}`,
            entity_id: node.id,
            kind: "person",
            person_count: 1,
            expandable: false,
          }))
        : data?.nodes || [],
    [data, connections, connection],
  );
  const edges = useMemo(
    () =>
      connection && connections
        ? connections.edges.map((edge) => ({
            ...edge,
            source: `person:${edge.source}`,
            target: `person:${edge.target}`,
          }))
        : data?.edges || [],
    [data, connections, connection],
  );
  const connectionLayout = useMemo(() => {
    if (!connection || !connections) return null;
    const key = JSON.stringify([connections.snapshot, connection]);
    return {
      key,
      layout: layoutConnections(
        connections,
        connection,
        connectionPositions.current?.key === key
          ? connectionPositions.current.layout
          : undefined,
      ),
    };
  }, [connection, connections]);
  useLayoutEffect(() => {
    connectionPositions.current = connectionLayout;
  }, [connectionLayout]);
  const layout = useMemo(() => {
    if (connectionLayout) {
      const hierarchy = connectionLayout.layout;
      return {
        ...hierarchy,
        nodes: hierarchy.nodes.map((node) => ({
          ...displayNodes.find((item) => item.entity_id === node.id)!,
          x: node.x,
          y: node.y,
        })),
      };
    }
    return layoutWindow(
      displayNodes,
      data?.offset || 0,
      data?.total || 0,
      viewport.width,
    );
  }, [
    displayNodes,
    connections,
    connectionLayout,
    connection,
    viewport.width,
    data?.offset,
    data?.total,
  ]);
  const byId = new Map(layout.nodes.map((node) => [node.id, node]));
  const visibleNodes = useMemo(
    () => visibleCards(layout.nodes, viewCamera, viewport, 260),
    [layout.nodes, viewCamera, viewport],
  );
  const columns = viewport.width >= 732 ? 3 : 2;

  useLayoutEffect(() => {
    if (!data || !sceneKey || sceneRef.current === sceneKey) return;
    const firstScene = !sceneRef.current;
    sceneRef.current = sceneKey;
    previousViewport.current = viewport;
    const person =
      (connection || request.person) &&
      layout.nodes.find(
        (node) => node.entity_id === (connection || request.person),
      );
    const fitted = fitCamera(layout, viewport, 24, 1);
    const readableScale = Math.min(
      1,
      Math.max(0.55, (viewport.width - 32) / 480),
    );
    const saved = history.current.get(sceneKey);
    let goal =
      (saved
        ? connection
          ? {
              ...saved.camera,
              x:
                saved.camera.x +
                (saved.viewport.width - viewport.width) /
                  (2 * saved.camera.scale),
              y:
                saved.camera.y +
                (saved.viewport.height - viewport.height) /
                  (2 * saved.camera.scale),
            }
          : reanchorGridCamera(
              saved.camera,
              saved.viewport,
              viewport,
              data.total,
            )
        : null) ||
      (person
        ? focusCamera(
            { x: person.x + 114, y: person.y + 68 },
            viewport,
            readableScale,
          )
        : fitted.scale >= 0.65
          ? fitted
          : {
              x: (layout.width - viewport.width / readableScale) / 2,
              y: (layout.nodes[0]?.y || 0) - 24 / readableScale,
              scale: readableScale,
            });
    const carry = queuedZoom.current;
    queuedZoom.current = null;
    if (carry)
      goal = zoomAt(
        goal,
        goal.scale * Math.exp(Math.max(-0.25, Math.min(0.25, carry.log))),
        carry.point,
      );
    // The outgoing chart remains visible until metadata arrives. Reveal the next
    // level at its own readable scale, with a short continuous camera settle.
    const start = zoomAt(
      goal,
      goal.scale * (transition.current === "exit" ? 1.12 : 0.88),
      { x: viewport.width / 2, y: viewport.height / 2 },
    );
    moveTo(firstScene ? goal : start, { immediate: true, publish: true });
    if (!firstScene) moveTo(goal);
  }, [sceneKey, data, layout, viewport, connection, request.person, moveTo]);

  useLayoutEffect(() => {
    const previous = previousViewport.current;
    previousViewport.current = viewport;
    if (
      !data ||
      (previous.width === viewport.width && previous.height === viewport.height)
    )
      return;
    const c = targetRef.current;
    const next = connection
      ? {
          ...c,
          x: c.x + (previous.width - viewport.width) / (2 * c.scale),
          y: c.y + (previous.height - viewport.height) / (2 * c.scale),
        }
      : reanchorGridCamera(c, previous, viewport, data.total);
    moveTo(next, { immediate: true, publish: true });
  }, [viewport, connection, data?.total, moveTo]);

  function remember(camera = targetRef.current) {
    if (!sceneKey) return;
    history.current.delete(sceneKey);
    const first = Math.max(
      0,
      Math.floor(Math.max(0, camera.y) / 160) * columns,
    );
    const offset = data?.total
      ? Math.min(
          Math.floor(first / limit) * limit,
          Math.floor((data.total - 1) / limit) * limit,
        )
      : 0;
    history.current.set(sceneKey, {
      camera: { ...camera },
      offset,
      viewport,
      ...(connection && connections && connectionLayout
        ? {
            graph: connections,
            connectionLayout: connectionLayout.layout,
            budget: connectionBudget,
          }
        : {}),
    });
    while (history.current.size > 24)
      history.current.delete(history.current.keys().next().value!);
  }
  function navigate(
    scope: string | null,
    offset = 0,
    direction: "enter" | "exit" | "direct" = "direct",
    grouping = lens,
  ) {
    remember();
    queuedZoom.current = null;
    transition.current = direction;
    pending.current = true;
    const saved = history.current.get(
      JSON.stringify([data?.snapshot || snapshot, grouping, scope, null]),
    );
    setRequest({ scope, offset: saved?.offset ?? offset });
    setRequestedConnection(null);
    onFocus(null);
    setHighlight(null);
  }
  function prefetch(node: ChartNode) {
    if (!data || pending.current || node.entity_id === connection) return;
    if (node.kind === "person" && node.entity_id) {
      void cache
        .get(chartPath({ scope: null, offset: 0, person: node.entity_id }))
        .then((value) =>
          cache.get(
            `/graph${query({ focus: node.entity_id, limit: Math.max(30, limit), snapshot: (value as ChartData).snapshot })}`,
          ),
        )
        .catch(() => {});
    } else if (node.expandable)
      void cache.get(chartPath({ scope: node.id, offset: 0 })).catch(() => {});
  }
  function enter(node: ChartNode) {
    if (
      pending.current ||
      (node.kind === "person" ? !node.entity_id : !node.expandable)
    )
      return;
    if (node.entity_id === connection) {
      const position = byId.get(node.id);
      setHover(null);
      if (position)
        moveTo(
          focusCamera({ x: position.x + 114, y: position.y + 68 }, viewport, 1),
        );
      return;
    }
    queuedZoom.current = null;
    prefetch(node);
    remember();
    transition.current = "enter";
    pending.current = true;
    if (node.kind === "person" && node.entity_id) {
      onSelect(node.entity_id);
      onFocus(node.entity_id);
      setRequestedConnection(node.entity_id);
      setRequest({ scope: null, offset: 0, person: node.entity_id });
    } else if (node.expandable) navigate(node.id, 0, "enter");
  }
  function up() {
    if (!data || pending.current) return;
    if (connection) {
      navigate(data.scope, data.offset, "exit");
      return;
    }
    const path = data.breadcrumbs;
    navigate(path.length > 1 ? path[path.length - 2].id : null, 0, "exit");
  }
  function zoom(
    direction: "in" | "out",
    factor: number,
    pointer?: { x: number; y: number },
  ) {
    if (!data) return;
    setHover(null);
    const point = pointer || { x: viewport.width / 2, y: viewport.height / 2 };
    const camera = targetRef.current;
    if (pending.current) {
      queuedZoom.current = {
        log: (queuedZoom.current?.log || 0) + Math.log(factor),
        point,
      };
      zoomTo(camera.scale * factor, point);
      return;
    }
    const displayed = cameraRef.current;
    const world = {
      x: displayed.x + point.x / displayed.scale,
      y: displayed.y + point.y / displayed.scale,
    };
    const underPointer = layout.nodes.find(
      (node) =>
        world.x >= node.x &&
        world.x <= node.x + 228 &&
        world.y >= node.y &&
        world.y <= node.y + 136,
    );
    const highlighted = byId.get(highlight || `person:${selected}`);
    const target =
      (pointer ? underPointer : highlighted || underPointer) ||
      (!pointer ? visibleNodes[0] : undefined);
    const nextScale = camera.scale * factor;
    const more =
      connection && connections
        ? nextConnectionBudget(connectionBudget, connections.returned_nodes)
        : null;
    if (
      connection &&
      direction === "in" &&
      more &&
      nextScale >= (connectionBudget < 80 ? 1.3 : 1.75)
    ) {
      void expandConnections();
    }
    if (target && direction === "in" && nextScale > 1.1) prefetch(target);
    const change = zoomTransition(
      direction,
      nextScale,
      Boolean(
        target &&
          (!connection ||
            (!more && !expanding && target.entity_id !== connection)) &&
          (target.expandable || target.kind === "person"),
      ),
      Boolean(connection || data.scope),
    );
    // Input is accumulated against the target camera, not a stale React render.
    zoomTo(nextScale, point);
    if (change === "enter" && target) {
      // Returning from the child restores this exact neighborhood, without refit.
      enter(target);
      remember(zoomAt(camera, Math.min(camera.scale, 1.15), point));
    } else if (change === "exit") up();
  }
  function pan(dx: number, dy: number, immediate = false) {
    setHover(null);
    const c = targetRef.current;
    const width = viewport.width / c.scale,
      height = viewport.height / c.scale;
    const xMin = Math.min(
      (connectionLayout?.layout.minX || 0) - 40 / c.scale,
      (layout.width - width) / 2,
    );
    const yMin = Math.min(
      (connectionLayout?.layout.minY || 0) - 40 / c.scale,
      (layout.height - height) / 2,
    );
    const xMax = Math.max(xMin, layout.width - width + 40 / c.scale);
    const yMax = Math.max(yMin, layout.height - height + 40 / c.scale);
    const x = Math.max(xMin, Math.min(xMax, c.x + dx / c.scale));
    const y = Math.max(yMin, Math.min(yMax, c.y + dy / c.scale));
    panBy((x - c.x) * c.scale, (y - c.y) * c.scale, immediate);
  }
  wheelHandler.current = (event) => {
    event.preventDefault();
    const rect = svg.current!.getBoundingClientRect();
    const intent = normalizeWheel(event, viewport.height, scrollMode);
    if (intent.kind === "pan") pan(intent.dx, intent.dy);
    else if (intent.logDelta !== 0)
      zoom(intent.logDelta >= 0 ? "in" : "out", Math.exp(intent.logDelta), {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
  };

  async function expandConnections() {
    if (!connection || !connections || pending.current || expansionBusy.current)
      return;
    const next = nextConnectionBudget(
      connectionBudget,
      connections.returned_nodes,
    );
    if (!next) return;
    const key = sceneKey;
    const generation = requestGeneration.current;
    expansionBusy.current = true;
    setExpanding(true);
    setError("");
    try {
      const graph = (await cache.get(
        `/graph${query({ focus: connection, limit: next, snapshot: data!.snapshot })}`,
      )) as Graph;
      if (
        sceneRef.current !== key ||
        pending.current ||
        requestGeneration.current !== generation
      )
        return;
      setConnections(graph);
      setConnectionBudget(next);
    } catch (cause) {
      if (
        sceneRef.current === key &&
        !pending.current &&
        requestGeneration.current === generation
      )
        setError(
          `Could not reveal more connections: ${String((cause as Error).message || cause)}`,
        );
    } finally {
      expansionBusy.current = false;
      setExpanding(false);
    }
  }

  function showInformation(
    id: string,
    content: TooltipContent,
    element: Element,
  ) {
    if (pending.current || pointers.current.size) return;
    const card = element.getBoundingClientRect();
    const canvas = svg.current!.getBoundingClientRect();
    setHover({
      id,
      content,
      anchor: {
        x: Math.max(
          12,
          Math.min(viewport.width - 12, card.right - canvas.left),
        ),
        y: Math.max(
          12,
          Math.min(viewport.height - 12, card.top - canvas.top + 16),
        ),
      },
    });
  }
  function showNodeInformation(node: ChartNode, element: Element) {
    const manager = node.manager_id
      ? byId.get(`person:${node.manager_id}`)?.name
      : undefined;
    showInformation(node.id, nodeTooltip(node, manager), element);
  }

  async function loadPage(offset: number, jump = false) {
    if (
      !data ||
      !data.total ||
      connection ||
      pending.current ||
      pageBusy.current
    )
      return;
    const base = data,
      key = sceneKey;
    pageBusy.current = true;
    setPageLoading(true);
    try {
      const page = (await cache.get(
        chartPath({ scope: base.scope, offset }),
      )) as ChartData;
      if (sceneRef.current !== key || pending.current) return;
      setData((current) =>
        current &&
        current.snapshot === page.snapshot &&
        current.lens === page.lens &&
        current.scope === page.scope
          ? { ...current, ...mergePage(current, page, 240), edges: [] }
          : current,
      );
      if (jump) {
        const c = targetRef.current;
        moveTo({ ...c, y: Math.floor(offset / columns) * 160 - 24 / c.scale });
      }
    } catch (cause) {
      if (sceneRef.current === key)
        setError(
          `Could not load more cards: ${String((cause as Error).message || cause)}`,
        );
    } finally {
      pageBusy.current = false;
      setPageLoading(false);
    }
  }
  useEffect(() => {
    if (!data || !data.total || connection || loading || pageLoading || error)
      return;
    const first = Math.max(0, Math.floor(viewCamera.y / 160) * columns);
    const last =
      Math.ceil((viewCamera.y + viewport.height / viewCamera.scale) / 160) *
      columns;
    const end = data.offset + data.nodes.length;
    if (first >= end && end < data.total)
      void loadPage(
        Math.min(
          Math.floor(first / limit) * limit,
          Math.floor((data.total - 1) / limit) * limit,
        ),
      );
    else if (last < data.offset && data.offset > 0)
      void loadPage(Math.max(0, Math.floor(first / limit) * limit));
    else if (last >= end - columns * 4 && end < data.total) void loadPage(end);
    else if (first < data.offset + columns * 2 && data.offset > 0)
      void loadPage(Math.max(0, data.offset - limit));
  }, [
    viewCamera,
    viewport,
    columns,
    data,
    connection,
    loading,
    pageLoading,
    error,
    limit,
  ]);

  const currentTitle = connection
    ? "Individual connections"
    : data?.scope
      ? data.breadcrumbs.at(-1)?.name
      : (data?.lens || lens) === "formal"
        ? "Department overview"
        : "Communication groups";
  const canGoUp = Boolean(connection || data?.scope);
  const pageStart = data?.total
    ? Math.max(
        data.offset,
        Math.floor(Math.max(0, viewCamera.y) / 160) * columns,
      ) + 1
    : 0;
  const breadcrumbs = data?.breadcrumbs.length
    ? data.breadcrumbs
    : [{ id: null, name: "Organization" }];
  function fitCurrent() {
    setHover(null);
    if (connectionLayout) {
      const { minX, minY, width, height } = connectionLayout.layout;
      const fitted = fitCamera(
        { width: width - minX, height: height - minY },
        viewport,
        24,
        1,
      );
      moveTo({ ...fitted, x: fitted.x + minX, y: fitted.y + minY });
      return;
    }
    if ((data?.total || 0) <= 30) {
      moveTo(fitCamera(layout, viewport, 24, 1));
      return;
    }
    const y = Math.max(0, Math.floor(targetRef.current.y / 160) * 160);
    const fitted = fitCamera(
      { width: layout.width, height: Math.min(5 * 160, layout.height - y) },
      viewport,
      24,
      1,
    );
    moveTo({ ...fitted, y: fitted.y + y });
  }
  return (
    <div className="graph-surface semantic-surface">
      <div className="semantic-toolbar">
        <label className="semantic-lens">
          <Layers3 size={14} />
          <select
            aria-label="Chart grouping"
            value={lens}
            onChange={(event) => {
              setLens(event.target.value as "formal" | "inferred");
              navigate(
                null,
                0,
                "direct",
                event.target.value as "formal" | "inferred",
              );
            }}
          >
            <option value="formal">Departments</option>
            <option value="inferred">Communication groups</option>
          </select>
        </label>
        <label className="semantic-scroll-mode">
          <span>Scroll</span>
          <select
            aria-label="Scroll behavior"
            value={scrollMode}
            onChange={(event) =>
              setScrollMode(event.target.value as ScrollMode)
            }
          >
            <option value="zoom">Zoom</option>
            <option value="pan">Move through chart</option>
          </select>
        </label>
        <button
          className="text-button"
          onClick={() => navigate(null)}
          title="Return to the whole organization"
        >
          Overview
        </button>
      </div>
      <nav className="chart-breadcrumbs" aria-label="Chart hierarchy">
        {breadcrumbs.map((crumb, index) => (
          <span key={crumb.id || "root"}>
            {index > 0 && <ChevronRight size={12} />}
            <button
              onClick={() => navigate(crumb.id)}
              aria-current={
                !connection && index === breadcrumbs.length - 1
                  ? "location"
                  : undefined
              }
            >
              {crumb.name}
            </button>
          </span>
        ))}
        {connection && (
          <span>
            <ChevronRight size={12} />
            <strong>Connections</strong>
          </span>
        )}
      </nav>
      <div className="semantic-heading">
        <div>
          <h3>{currentTitle}</h3>
          <p>
            {connection
              ? "Keep zooming to reveal more connections • Hover for details • Drag to explore"
              : scrollMode === "zoom"
                ? "Scroll to zoom into more detail • Hover for information • Drag to explore"
                : "Scroll through the chart • Pinch or Ctrl + scroll to zoom • Groups load as you move"}
          </p>
        </div>
        {canGoUp && (
          <button className="semantic-up" onClick={up}>
            <ArrowLeft size={13} /> Up one level
          </button>
        )}
      </div>
      <div className="semantic-canvas">
        <svg
          ref={svg}
          className="org-graph semantic-graph"
          role="group"
          aria-label={`Semantic organization chart: ${currentTitle}, ${visibleNodes.length} visible cards. Scroll to ${scrollMode === "pan" ? "move" : "zoom"}; drag to pan.`}
          aria-busy={loading || pageLoading || expanding}
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Escape" && hover) {
              event.preventDefault();
              setHover(null);
              return;
            }
            if (event.key === "+" || event.key === "=") {
              event.preventDefault();
              zoom("in", 1.3);
            }
            if (event.key === "-") {
              event.preventDefault();
              zoom("out", 1 / 1.3);
            }
            if (event.key === "Escape" && canGoUp) {
              event.preventDefault();
              up();
            }
            const delta = (
              {
                ArrowLeft: [-60, 0],
                ArrowRight: [60, 0],
                ArrowUp: [0, -60],
                ArrowDown: [0, 60],
              } as Record<string, number[]>
            )[event.key];
            if (delta && event.target === event.currentTarget) {
              event.preventDefault();
              pan(delta[0], delta[1]);
            }
          }}
          onPointerDown={(event) => {
            setHover(null);
            stop();
            moved.current = false;
            pointers.current.set(event.pointerId, {
              x: event.clientX,
              y: event.clientY,
            });
            pointerStarts.current.set(event.pointerId, {
              x: event.clientX,
              y: event.clientY,
            });
            // Preserve card click targeting; capture only once an actual drag starts.
            if (!(event.target as Element).closest('[role="button"]'))
              event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const previous = pointers.current.get(event.pointerId);
            if (!previous) return;
            const current = { x: event.clientX, y: event.clientY };
            const start =
              pointerStarts.current.get(event.pointerId) || previous;
            if (Math.hypot(current.x - start.x, current.y - start.y) > 4) {
              moved.current = true;
              event.currentTarget.setPointerCapture(event.pointerId);
            }
            const other = [...pointers.current.entries()].find(
              ([id]) => id !== event.pointerId,
            )?.[1];
            if (other) {
              const before = Math.hypot(
                  previous.x - other.x,
                  previous.y - other.y,
                ),
                after = Math.hypot(current.x - other.x, current.y - other.y);
              const rect = event.currentTarget.getBoundingClientRect();
              if (before > 5)
                zoom(after > before ? "in" : "out", after / before, {
                  x: (current.x + other.x) / 2 - rect.left,
                  y: (current.y + other.y) / 2 - rect.top,
                });
            } else if (moved.current)
              pan(previous.x - current.x, previous.y - current.y, true);
            pointers.current.set(event.pointerId, current);
          }}
          onPointerUp={(event) => {
            pointers.current.delete(event.pointerId);
            pointerStarts.current.delete(event.pointerId);
          }}
          onPointerCancel={(event) => {
            pointers.current.delete(event.pointerId);
            pointerStarts.current.delete(event.pointerId);
          }}
          onLostPointerCapture={(event) => {
            pointers.current.delete(event.pointerId);
            pointerStarts.current.delete(event.pointerId);
          }}
          onPointerLeave={(event) => {
            setHover(null);
            if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
              pointers.current.delete(event.pointerId);
              pointerStarts.current.delete(event.pointerId);
            }
          }}
        >
          <defs>
            <marker
              id="reporting-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M0 0 L10 5 L0 10" fill="#829b8c" />
            </marker>
          </defs>
          <g key={sceneKey} className="semantic-scene">
            {edges.map((edge) => {
              const source = byId.get(edge.source),
                target = byId.get(edge.target);
              if (!source || !target) return null;
              // In the paged directory, cards are a grid; individual connections use the reporting layout.
              if (!connection) return null;
              const x1 = source.x + 114,
                y1 = source.y + 136,
                x2 = target.x + 114,
                y2 = target.y;
              const path = `M${x1} ${y1} V${(y1 + y2) / 2} H${x2} V${y2}`;
              const inferred =
                edge.origin === "model" && edge.review_status !== "accepted";
              const inspect = () => {
                if (target.entity_id) onSelect(target.entity_id);
              };
              return (
                <g
                  key={edge.id}
                  className="semantic-edge"
                  onMouseEnter={(event) =>
                    showInformation(
                      edge.id,
                      edgeTooltip(edge, source.name, target.name),
                      event.currentTarget,
                    )
                  }
                  onMouseLeave={() => setHover(null)}
                  onClick={() => {
                    if (!moved.current) inspect();
                  }}
                >
                  <path
                    d={path}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="16"
                  />
                  <path
                    className="edge-visible"
                    d={path}
                    fill="none"
                    stroke={inferred ? "#91a99b" : "#327267"}
                    strokeWidth="2"
                    strokeDasharray={inferred ? "5 4" : undefined}
                    markerEnd="url(#reporting-arrow)"
                  />
                  <g
                    role="button"
                    tabIndex={0}
                    className="edge-evidence"
                    aria-describedby={
                      hover?.id === edge.id ? "chart-tooltip" : undefined
                    }
                    transform={`translate(${x2},${y2 - 15})`}
                    aria-label={`${source.name} manages ${target.name}. ${inferred ? "Inferred" : "Source or reviewed"} reporting connection. Inspect evidence.`}
                    onFocus={(event) =>
                      showInformation(
                        edge.id,
                        edgeTooltip(edge, source.name, target.name),
                        event.currentTarget,
                      )
                    }
                    onBlur={() => setHover(null)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        inspect();
                      }
                    }}
                  >
                    <circle r="9" fill="#f8fbf4" stroke="#8aa491" />
                    <text
                      y="3"
                      textAnchor="middle"
                      fontSize="10"
                      fontWeight="600"
                      fill="#56765f"
                    >
                      i
                    </text>
                  </g>
                </g>
              );
            })}
            {visibleNodes.map((node) => {
              const person = node.kind === "person",
                active = person
                  ? node.entity_id === selected
                  : node.id === highlight;
              const color = active ? "#194e46" : "#fffefb",
                ink = active ? "#ffffff" : "#263d35",
                muted = active ? "#c3dbce" : "#708274";
              const action = () => {
                setHighlight(node.id);
                if (person && node.entity_id) onSelect(node.entity_id);
                else enter(node);
              };
              return (
                <g
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  className={`graph-node ${active ? "active" : ""}`}
                  transform={`translate(${node.x},${node.y})`}
                  aria-label={
                    person
                      ? `${node.name}, ${node.role || "Position unspecified"}, ${label(node.status)}. Select for evidence; double-click for connections.`
                      : `${node.name}, ${node.person_count.toLocaleString()} people, ${label(node.kind)}. Zoom into group.`
                  }
                  aria-pressed={active}
                  aria-describedby={
                    hover?.id === node.id ? "chart-tooltip" : undefined
                  }
                  onMouseEnter={(event) => {
                    setHighlight(node.id);
                    prefetch(node);
                    showNodeInformation(node, event.currentTarget);
                  }}
                  onMouseLeave={() => setHover(null)}
                  onFocus={(event) =>
                    showNodeInformation(node, event.currentTarget)
                  }
                  onBlur={() => setHover(null)}
                  onClick={() => {
                    if (!moved.current) action();
                  }}
                  onDoubleClick={() => enter(node)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      action();
                    }
                    if (event.key === "ArrowRight") {
                      event.preventDefault();
                      enter(node);
                    }
                  }}
                >
                  <rect
                    className="node-card"
                    width="228"
                    height="136"
                    rx="12"
                    fill={color}
                    stroke={
                      active
                        ? "#194e46"
                        : node.kind === "group"
                          ? "#b6c7d2"
                          : "#d7e0d5"
                    }
                    strokeDasharray={node.kind === "group" ? "5 3" : undefined}
                  />
                  <text
                    x="17"
                    y="25"
                    fontSize="9"
                    letterSpacing="1.2"
                    fill={muted}
                  >
                    {person
                      ? "INDIVIDUAL POSITION"
                      : node.kind === "group"
                        ? "INFERRED GROUP"
                        : node.kind === "team"
                          ? "REPORTING BRANCH"
                          : node.kind === "unassigned"
                            ? "UNASSIGNED"
                            : "DEPARTMENT"}
                  </text>
                  <text x="17" y="51" fontSize="14" fontWeight="650" fill={ink}>
                    {short(node.name.replace(/ · reporting branch$/, ""), 26)}
                  </text>
                  {person ? (
                    <>
                      <text x="17" y="72" fontSize="11" fill={muted}>
                        {short(node.role || "Position unspecified", 32)}
                      </text>
                      <line
                        x1="17"
                        x2="211"
                        y1="87"
                        y2="87"
                        stroke={active ? "#457469" : "#e8ede4"}
                      />
                      <circle
                        cx="21"
                        cy="108"
                        r="3"
                        fill={
                          node.status === "unresolved" ? "#c18a53" : "#7fa58d"
                        }
                      />
                      <text x="31" y="112" fontSize="10" fill={muted}>
                        {node.status === "unresolved"
                          ? "Manager unresolved"
                          : label(node.status)}
                      </text>
                      <text
                        x="209"
                        y="113"
                        textAnchor="end"
                        fontSize="11"
                        fill={muted}
                      >
                        {initials(node.name)}
                      </text>
                    </>
                  ) : (
                    <>
                      <text
                        x="17"
                        y="82"
                        fontSize="22"
                        fontWeight="600"
                        fill={ink}
                      >
                        {node.person_count.toLocaleString()}
                        <tspan fontSize="11" fontWeight="400" fill={muted}>
                          {" "}
                          people
                        </tspan>
                      </text>
                      <text x="17" y="112" fontSize="10" fill={muted}>
                        {(node.unresolved_count ?? 0).toLocaleString()}{" "}
                        unresolved managers
                      </text>
                      <text
                        x="209"
                        y="112"
                        fontSize="17"
                        fill={muted}
                        textAnchor="end"
                      >
                        ↗
                      </text>
                    </>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <ChartTooltip
          content={hover?.content || null}
          anchor={hover?.anchor || { x: 0, y: 0 }}
          bounds={viewport}
        />
        {loading && !data && (
          <div className="semantic-overlay" role="status">
            Loading this level…
          </div>
        )}
        {(loading || pageLoading || expanding) && data && (
          <div className="semantic-loading-pill" role="status">
            {expanding
              ? "Revealing connections…"
              : pageLoading
                ? "Loading more…"
                : "Opening level…"}
          </div>
        )}
        {error && (
          <div
            className={data ? "semantic-error-pill" : "semantic-overlay"}
            role="alert"
          >
            <p>{error}</p>
            <button
              className="text-button"
              onClick={() => {
                setError("");
                if (error.startsWith("Could not reveal"))
                  void expandConnections();
                else if (!data) navigate(null);
                else if (!error.startsWith("Could not load more"))
                  setRequest({ ...request });
              }}
            >
              Retry
            </button>
          </div>
        )}
        {!loading && !error && !displayNodes.length && (
          <div className="semantic-overlay">
            No people or groups in this scope.
          </div>
        )}
      </div>
      <div className="semantic-footer">
        <span className="semantic-level" aria-live="polite">
          {connection
            ? "Connections"
            : displayNodes.some((n) => n.kind !== "person")
              ? "Groups"
              : "People & positions"}
          <small>
            {data?.total_people.toLocaleString() || "—"} people in organization
          </small>
        </span>
        <div className="graph-controls">
          <button
            aria-label="Zoom out"
            title="Zoom out; return to parent group"
            onClick={() => zoom("out", 1 / 1.3)}
          >
            <Minus size={16} />
          </button>
          <span>{Math.round(scale * 100)}%</span>
          <button
            aria-label="Zoom in"
            title="Zoom in; enter the highlighted group"
            onClick={() => zoom("in", 1.3)}
          >
            <Plus size={16} />
          </button>
          <button
            aria-label="Fit this level"
            title="Fit this level"
            onClick={fitCurrent}
          >
            <Maximize2 size={15} />
          </button>
        </div>
      </div>
      <div className="semantic-pagination">
        <span title={data?.description}>
          {connection
            ? `${displayNodes.length} people · ${edges.length} reporting connections · dashed = inferred`
            : `${Math.min(pageStart, data?.total || 0)}–${Math.min(data?.total || 0, Math.ceil((Math.max(0, viewCamera.y) + viewport.height / viewCamera.scale) / 160) * columns)} of ${data?.total || 0} cards · Continuous scroll`}
        </span>
        {connection &&
          connections &&
          (nextConnectionBudget(
            connectionBudget,
            connections.returned_nodes,
          ) ? (
            <button
              className="text-button"
              disabled={expanding || loading}
              onClick={() => void expandConnections()}
            >
              Reveal more connections
            </button>
          ) : (
            <span className="semantic-connection-hint">
              Zoom into another person to follow their branch
            </span>
          ))}
        {!connection && (
          <div>
            <button
              aria-label="Previous chart page"
              disabled={loading || pageLoading || pageStart <= 1}
              onClick={() =>
                void loadPage(Math.max(0, pageStart - 1 - limit), true)
              }
            >
              <ArrowLeft size={14} />
            </button>
            <button
              aria-label="Next chart page"
              disabled={
                loading ||
                pageLoading ||
                !data ||
                pageStart + limit >= data.total
              }
              onClick={() =>
                void loadPage(
                  Math.min(data!.total - 1, pageStart - 1 + limit),
                  true,
                )
              }
            >
              <ArrowRight size={14} />
            </button>
          </div>
        )}
        {selected && (
          <button
            className="text-button"
            onClick={() => {
              if (selected === connection) {
                const node = byId.get(`person:${selected}`);
                if (node) enter(node);
                return;
              }
              onFocus(selected);
              remember();
              queuedZoom.current = null;
              transition.current = "direct";
              pending.current = true;
              setRequestedConnection(selected);
              setRequest({ scope: null, offset: 0, person: selected });
            }}
          >
            <LocateFixed size={13} /> Selected person
          </button>
        )}
      </div>
    </div>
  );
}
