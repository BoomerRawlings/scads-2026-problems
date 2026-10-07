import { layoutGraph, type PositionedNode } from "./layout";
import { CARD_HEIGHT, CARD_WIDTH } from "./semanticZoom";
import type { Graph } from "./types";

export type ConnectionLayout = {
  nodes: PositionedNode[];
  /** Right and bottom world extents; minX/minY allow newly revealed ancestors. */
  width: number;
  height: number;
  minX: number;
  minY: number;
};

/** Omitted nodes describe the whole organization, not this reporting component. */
export function nextConnectionBudget(
  currentBudget: number,
  returnedNodes: number,
): number | null {
  if (
    !Number.isFinite(currentBudget) ||
    currentBudget < 1 ||
    !Number.isFinite(returnedNodes) ||
    returnedNodes < currentBudget
  )
    return null;
  return [30, 80, 200].find((budget) => budget > currentBudget) ?? null;
}

/**
 * Keep the cards already under the analyst's eyes fixed as a bounded reporting
 * neighborhood grows. New cards use the nearest vacant slot on their tier.
 */
export function layoutConnections(
  graph: Graph,
  focus: string | null,
  previous?: ConnectionLayout | null,
): ConnectionLayout {
  if (!previous?.nodes.length) {
    const initial = layoutGraph(graph, focus);
    return {
      nodes: initial.nodes.map((node) => ({
        ...node,
        x: node.x * 1.25,
        y: node.y * 1.15,
      })),
      width: initial.width * 1.25,
      height: initial.height * 1.15,
      minX: 0,
      minY: 0,
    };
  }

  const ids = new Set(graph.nodes.map((node) => node.id));
  const positions = new Map(
    previous.nodes
      .filter((node) => ids.has(node.id))
      .map((node) => [node.id, { x: node.x, y: node.y }]),
  );
  const parents = new Map<string, string>();
  const children = new Map<string, string[]>();
  for (const edge of graph.edges) {
    if (
      !ids.has(edge.source) ||
      !ids.has(edge.target) ||
      edge.source === edge.target ||
      parents.has(edge.target)
    )
      continue;
    parents.set(edge.target, edge.source);
    children.set(edge.source, [
      ...(children.get(edge.source) || []),
      edge.target,
    ]);
  }
  const pending = graph.nodes.filter((node) => !positions.has(node.id));
  const horizontalStep = CARD_WIDTH + 32;
  const verticalStep = CARD_HEIGHT + 48;
  const overlaps = (x: number, y: number) =>
    Array.from(positions.values()).some(
      (other) =>
        Math.abs(x - other.x) < CARD_WIDTH + 24 &&
        Math.abs(y - other.y) < CARD_HEIGHT + 24,
    );

  while (pending.length) {
    // Prefer a frontier attached to a retained card, including new ancestors.
    const attached = pending.findIndex(
      (node) =>
        positions.has(parents.get(node.id) || "") ||
        (children.get(node.id) || []).some((child) => positions.has(child)),
    );
    const [node] = pending.splice(Math.max(0, attached), 1);
    const parent = positions.get(parents.get(node.id) || "");
    const knownChildren = (children.get(node.id) || [])
      .map((child) => positions.get(child))
      .filter((point): point is { x: number; y: number } => Boolean(point));
    let x = parent?.x ?? 42.5;
    let y = parent ? parent.y + verticalStep : 50.6;
    if (!parent && knownChildren.length) {
      x =
        knownChildren.reduce((sum, point) => sum + point.x, 0) /
        knownChildren.length;
      y = Math.min(...knownChildren.map((point) => point.y)) - verticalStep;
    } else if (!parent && !knownChildren.length && positions.size) {
      // A disconnected or malformed response stays navigable without moving
      // any established reporting component.
      y =
        Math.max(...Array.from(positions.values(), (point) => point.y)) +
        verticalStep;
    }
    let slot = 0;
    while (overlaps(x + slot * horizontalStep, y)) {
      // 0, +1, -1, +2, -2… retains the closest available parent alignment.
      slot = slot > 0 ? -slot : 1 - slot;
    }
    positions.set(node.id, { x: x + slot * horizontalStep, y });
  }

  const nodes = graph.nodes.map((node) => ({
    ...node,
    ...positions.get(node.id)!,
  }));
  return {
    nodes,
    width: Math.max(775, ...nodes.map((node) => node.x + CARD_WIDTH + 24)),
    height: Math.max(460, ...nodes.map((node) => node.y + CARD_HEIGHT + 24)),
    minX: Math.min(0, ...nodes.map((node) => node.x - 24)),
    minY: Math.min(0, ...nodes.map((node) => node.y - 24)),
  };
}
