import type { Graph, GraphNode } from "./types";
export type PositionedNode = GraphNode & { x: number; y: number };
export function layoutGraph(
  graph: Graph,
  focusId?: string | null,
): {
  nodes: PositionedNode[];
  width: number;
  height: number;
} {
  const ids = new Set(graph.nodes.map((node) => node.id));
  const children = new Map<string, string[]>();
  const parents = new Map<string, string>();
  graph.edges.forEach((edge) => {
    if (
      !ids.has(edge.source) ||
      !ids.has(edge.target) ||
      edge.source === edge.target ||
      parents.has(edge.target)
    )
      return;
    children.set(edge.source, [
      ...(children.get(edge.source) || []),
      edge.target,
    ]);
    parents.set(edge.target, edge.source);
  });
  const positions = new Map<string, { x: number; y: number }>();
  const visited = new Set<string>();
  let cursor = 0;
  let componentIds: string[] = [];
  const walk = (id: string, depth: number): number => {
    if (visited.has(id)) return positions.get(id)?.x ?? cursor;
    visited.add(id);
    componentIds.push(id);
    const next = (children.get(id) || []).filter(
      (child) => !visited.has(child),
    );
    const xs = next.map((child) => walk(child, depth + 1));
    const x = xs.length ? (xs[0] + xs[xs.length - 1]) / 2 : cursor++ * 212;
    positions.set(id, { x: x + 34, y: depth * 160 + 44 });
    return x;
  };
  const roots = graph.nodes.filter((node) => !parents.has(node.id));
  const components: { ids: string[]; width: number; height: number }[] = [];
  const component = (id: string) => {
    if (visited.has(id)) return;
    cursor = 0;
    componentIds = [];
    walk(id, 0);
    components.push({
      ids: componentIds,
      width: Math.max(
        ...componentIds.map((key) => positions.get(key)!.x + 214),
      ),
      height: Math.max(
        ...componentIds.map((key) => positions.get(key)!.y + 134),
      ),
    });
  };
  roots.forEach((node) => component(node.id));
  // Defensive handling of malformed disconnected/cyclic payloads keeps every node navigable.
  graph.nodes
    .filter((node) => !visited.has(node.id))
    .forEach((node) => component(node.id));
  // Pack independent trees into shelves instead of stretching every root across one tier.
  // The largest reporting component appears first; unresolved people stay separate.
  const shelfWidth = Math.max(660, ...components.map((item) => item.width));
  let shelfX = 0,
    shelfY = 0,
    shelfHeight = 0;
  components
    .sort((a, b) => b.ids.length - a.ids.length)
    .forEach((item) => {
      if (shelfX && shelfX + item.width > shelfWidth) {
        shelfY += shelfHeight + 36;
        shelfX = 0;
        shelfHeight = 0;
      }
      item.ids.forEach((id) => {
        const point = positions.get(id)!;
        positions.set(id, { x: point.x + shelfX, y: point.y + shelfY });
      });
      shelfX += item.width + 12;
      shelfHeight = Math.max(shelfHeight, item.height);
    });
  // Keep the focused employee's reporting line above them even in a wide
  // tree. Ancestors remain within their original subtree's horizontal span;
  // siblings and other components retain their stable positions.
  const focus = focusId ? positions.get(focusId) : undefined;
  if (focus && focusId) {
    const lineage = new Set([focusId]);
    let parent = parents.get(focusId);
    while (parent && !lineage.has(parent)) {
      lineage.add(parent);
      const point = positions.get(parent);
      if (point) positions.set(parent, { ...point, x: focus.x });
      parent = parents.get(parent);
    }
  }
  const nodes = graph.nodes.map((node) => ({
    ...node,
    ...positions.get(node.id)!,
  }));
  return {
    nodes,
    width: Math.max(620, ...nodes.map((node) => node.x + 220)),
    height: Math.max(400, ...nodes.map((node) => node.y + 148)),
  };
}
