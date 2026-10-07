import { describe, expect, it } from "vitest";
import {
  layoutConnections,
  nextConnectionBudget,
  type ConnectionLayout,
} from "./connectionDetail";
import { layoutGraph } from "./layout";
import type { Graph } from "./types";

const graph = (ids: string[], links: [string, string][]): Graph => ({
  nodes: ids.map((id) => ({ id, name: id, type: "person", role: "Analyst" })),
  edges: links.map(([source, target], i) => ({
    id: `assertion-${i}`,
    source,
    target,
    origin: "model",
    review_status: "unreviewed",
    raw_score: 0.72,
    calibration_status: "uncalibrated",
  })),
  total_nodes: 10000,
  returned_nodes: ids.length,
  omitted_nodes: 10000 - ids.length,
});
const positions = (layout: ConnectionLayout) =>
  Object.fromEntries(layout.nodes.map(({ id, x, y }) => [id, { x, y }]));
const noCollisions = (layout: ConnectionLayout) => {
  for (const [index, node] of layout.nodes.entries()) {
    for (const other of layout.nodes.slice(index + 1)) {
      expect(
        Math.abs(node.x - other.x) >= 228 || Math.abs(node.y - other.y) >= 136,
      ).toBe(true);
    }
  }
};

describe("progressive reporting connection budgets", () => {
  it("grows through bounded stages then stops at the API cap", () => {
    expect(nextConnectionBudget(30, 30)).toBe(80);
    expect(nextConnectionBudget(80, 80)).toBe(200);
    expect(nextConnectionBudget(200, 200)).toBeNull();
    expect(nextConnectionBudget(50, 50)).toBe(80);
  });
  it("stops when this focused component is exhausted despite organization omissions", () => {
    expect(nextConnectionBudget(30, 1)).toBeNull();
    expect(nextConnectionBudget(80, 79)).toBeNull();
    expect(nextConnectionBudget(30, 0)).toBeNull();
  });
  it("rejects invalid counters without unbounded requests", () => {
    expect(nextConnectionBudget(0, 0)).toBeNull();
    expect(nextConnectionBudget(NaN, 30)).toBeNull();
    expect(nextConnectionBudget(30, Infinity)).toBeNull();
    expect(nextConnectionBudget(201, 201)).toBeNull();
  });
});

describe("stable expanded reporting layout", () => {
  it("matches the existing initial semantic view and retains entity metadata", () => {
    const fixture = graph(
      ["manager", "a", "b"],
      [
        ["manager", "a"],
        ["manager", "b"],
      ],
    );
    const original = layoutGraph(fixture, "a");
    const initial = layoutConnections(fixture, "a");
    expect(initial.nodes).toEqual(
      original.nodes.map((node) => ({
        ...node,
        x: node.x * 1.25,
        y: node.y * 1.15,
      })),
    );
    expect(initial.width).toBe(original.width * 1.25);
    expect(initial.height).toBe(original.height * 1.15);
    expect(initial.nodes.every((node) => node.role === "Analyst")).toBe(true);
  });
  it("preserves every retained position through 30, 80, and 200 people without collisions", () => {
    const fixture = (count: number) =>
      graph(
        Array.from({ length: count }, (_, i) => String(i)),
        Array.from(
          { length: count - 1 },
          (_, i) =>
            [String(Math.floor(i / 6)), String(i + 1)] as [string, string],
        ),
      );
    let previous = layoutConnections(fixture(30), "1");
    for (const count of [80, 200]) {
      const expanded = layoutConnections(fixture(count), "1", previous);
      const after = positions(expanded);
      for (const node of previous.nodes)
        expect(after[node.id]).toEqual({ x: node.x, y: node.y });
      const lookup = new Map(expanded.nodes.map((node) => [node.id, node]));
      for (const edge of fixture(count).edges)
        expect(lookup.get(edge.target)!.y).toBeGreaterThan(
          lookup.get(edge.source)!.y,
        );
      noCollisions(expanded);
      expect(expanded.nodes).toHaveLength(count);
      previous = expanded;
    }
  });
  it("places additional ancestors above retained cards and includes negative bounds", () => {
    const before = layoutConnections(
      graph(["child", "parent"], [["parent", "child"]]),
      "child",
    );
    const expanded = layoutConnections(
      graph(
        ["child", "parent", "grandparent"],
        [
          ["parent", "child"],
          ["grandparent", "parent"],
        ],
      ),
      "child",
      before,
    );
    const byId = positions(expanded);
    expect(byId.child).toEqual(positions(before).child);
    expect(byId.parent).toEqual(positions(before).parent);
    expect(byId.grandparent.y).toBeLessThan(byId.parent.y);
    expect(expanded.minY).toBeLessThanOrEqual(byId.grandparent.y);
    expect(expanded.minY).toBeLessThan(0);
    noCollisions(expanded);
  });
  it("drops displaced IDs, updates metadata, and never fabricates graph connections", () => {
    const before = layoutConnections(
      graph(
        ["parent", "a", "removed"],
        [
          ["parent", "a"],
          ["parent", "removed"],
        ],
      ),
      "a",
    );
    const next = graph(
      ["parent", "a", "new"],
      [
        ["parent", "a"],
        ["parent", "new"],
      ],
    );
    next.nodes[1].role = "Manager";
    const input = structuredClone(next);
    const expanded = layoutConnections(next, "a", before);
    expect(expanded.nodes.map((node) => node.id)).toEqual([
      "parent",
      "a",
      "new",
    ]);
    expect(positions(expanded).a).toEqual(positions(before).a);
    expect(expanded.nodes[1].role).toBe("Manager");
    expect(next).toEqual(input);
    noCollisions(expanded);
  });
  it("handles disconnected additions, malformed edges, cycles and empty responses", () => {
    const before = layoutConnections(graph(["a"], []), "a");
    const next = graph(
      ["a", "b", "c", "isolated"],
      [
        ["a", "b"],
        ["b", "c"],
        ["c", "b"],
        ["missing", "c"],
        ["a", "a"],
      ],
    );
    const expanded = layoutConnections(next, "a", before);
    expect(
      expanded.nodes.every(
        (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
      ),
    ).toBe(true);
    noCollisions(expanded);
    expect(layoutConnections(graph([], []), null, expanded).nodes).toEqual([]);
  });
  it("is deterministic for the same retained neighborhood", () => {
    const before = layoutConnections(
      graph(["parent", "a"], [["parent", "a"]]),
      "a",
    );
    const next = graph(
      ["parent", "a", "b", "c"],
      [
        ["parent", "a"],
        ["parent", "b"],
        ["parent", "c"],
      ],
    );
    expect(layoutConnections(next, "a", before)).toEqual(
      layoutConnections(next, "a", before),
    );
  });
});
