import { describe, expect, it } from "vitest";
import { layoutGraph } from "./layout";
import type { Graph } from "./types";
const graph = (ids: string[], edges: [string, string][]): Graph => ({
  nodes: ids.map((id) => ({ id, name: id, type: "person" })),
  edges: edges.map(([source, target], i) => ({
    id: String(i),
    source,
    target,
    origin: "source",
    review_status: "unreviewed",
    raw_score: null,
    calibration_status: "unavailable",
  })),
  total_nodes: ids.length,
  returned_nodes: ids.length,
  omitted_nodes: 0,
});
describe("bounded hierarchy layout", () => {
  it("places reports below managers with distinct sibling positions", () => {
    const result = layoutGraph(
      graph(
        ["a", "b", "c", "d"],
        [
          ["a", "b"],
          ["a", "c"],
          ["b", "d"],
        ],
      ),
    );
    const nodes = Object.fromEntries(
      result.nodes.map((node) => [node.id, node]),
    );
    expect(nodes.b.y).toBeGreaterThan(nodes.a.y);
    expect(nodes.d.y).toBeGreaterThan(nodes.b.y);
    expect(nodes.b.x).not.toBe(nodes.c.x);
  });
  it("retains isolated unresolved people and survives malformed cycles", () => {
    const result = layoutGraph(
      graph(
        ["a", "b", "unknown"],
        [
          ["a", "b"],
          ["b", "a"],
        ],
      ),
    );
    expect(result.nodes).toHaveLength(3);
    expect(
      result.nodes.every(
        (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
      ),
    ).toBe(true);
  });
  it("is deterministic across repeated projections", () => {
    const fixture = graph(
      ["root", "x", "y"],
      [
        ["root", "x"],
        ["root", "y"],
      ],
    );
    expect(layoutGraph(fixture)).toEqual(layoutGraph(fixture));
  });
  it("packs unrelated roots without one impossibly wide horizontal tier", () => {
    const result = layoutGraph(
      graph(
        Array.from({ length: 30 }, (_, index) => String(index)),
        [],
      ),
    );
    expect(result.width).toBeLessThan(800);
    expect(new Set(result.nodes.map((node) => node.y)).size).toBeGreaterThan(1);
    expect(
      new Set(result.nodes.map((node) => `${node.x},${node.y}`)).size,
    ).toBe(30);
  });

  it("keeps a focused employee and ancestors aligned in a wide reporting tree", () => {
    const ids = ["root", "unresolved"];
    const edges: [string, string][] = [];
    for (let manager = 0; manager < 8; manager++) {
      const managerId = `manager-${manager}`;
      ids.push(managerId);
      edges.push(["root", managerId]);
      for (let person = 0; person < 8; person++) {
        const personId = `person-${manager}-${person}`;
        ids.push(personId);
        edges.push([managerId, personId]);
      }
    }
    const fixture = graph(ids, edges);
    const original = layoutGraph(fixture);
    const focused = layoutGraph(fixture, "person-0-0");
    const before = Object.fromEntries(
      original.nodes.map((node) => [node.id, node]),
    );
    const after = Object.fromEntries(
      focused.nodes.map((node) => [node.id, node]),
    );
    // Previously the immediate manager was outside a 640px viewport centered
    // on this employee, even before the semantic chart's 1.25x spacing.
    expect(before["manager-0"].x - before["person-0-0"].x).toBeGreaterThan(640);
    expect(after["manager-0"].x).toBe(after["person-0-0"].x);
    expect(after.root.x).toBe(after["person-0-0"].x);
    for (const node of focused.nodes) {
      expect(node.y).toBe(before[node.id].y);
      if (node.id !== "root" && node.id !== "manager-0") {
        expect(node.x).toBe(before[node.id].x);
      }
    }
    // Test the actual 228x136 semantic cards with their renderer's spacing.
    focused.nodes.forEach((node, index) => {
      for (const other of focused.nodes.slice(index + 1)) {
        expect(
          Math.abs(node.x - other.x) * 1.25 >= 228 ||
            Math.abs(node.y - other.y) * 1.15 >= 136,
        ).toBe(true);
      }
    });
    expect(layoutGraph(fixture, "person-0-0")).toEqual(focused);
  });

  it("leaves layout unchanged for absent focus and terminates cyclic ancestry", () => {
    const fixture = graph(
      ["a", "b", "isolated"],
      [
        ["a", "b"],
        ["b", "a"],
      ],
    );
    expect(layoutGraph(fixture, "missing")).toEqual(layoutGraph(fixture));
    const focused = layoutGraph(fixture, "a");
    expect(focused.nodes).toHaveLength(3);
    expect(
      focused.nodes.every(
        (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
      ),
    ).toBe(true);
  });
});
