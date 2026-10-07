import { describe, expect, it } from "vitest";
import {
  layoutWindow,
  mergePage,
  reanchorGridCamera,
  visibleCards,
} from "./chartWindow";
import type { ChartWindow } from "./chartWindow";
import { layoutCards } from "./semanticZoom";

type Item = { id: string; value: number };
const page = (
  offset: number,
  length: number,
  total = 1000,
): ChartWindow<Item> => ({
  nodes: Array.from(
    { length: Math.min(length, total - offset) },
    (_, index) => ({
      id: `person-${offset + index}`,
      value: offset + index,
    }),
  ),
  offset,
  total,
});

describe("continuous chart layout", () => {
  it.each([600, 900])("matches the original full grid at width %s", (width) => {
    const all = page(0, 81, 81);
    expect(layoutWindow(all.nodes, 0, all.total, width)).toEqual(
      layoutCards(all.nodes, width),
    );
  });

  it.each([600, 900])(
    "uses absolute positions when page offsets split rows at width %s",
    (width) => {
      const all = page(0, 100, 100);
      const part = page(31, 17, 100);
      const layout = layoutWindow(part.nodes, part.offset, part.total, width);
      const full = layoutWindow(all.nodes, 0, all.total, width);
      expect(layout.nodes).toEqual(full.nodes.slice(31, 48));
      expect(layout.width).toBe(full.width);
      expect(layout.height).toBe(full.height);
    },
  );

  it("keeps full-scope bounds while unloaded or empty", () => {
    expect(layoutWindow([], 0, 0, 900)).toEqual({
      nodes: [],
      width: 0,
      height: 0,
    });
    expect(layoutWindow([], 0, 10000, 900).height).toBe(3334 * 160 - 24);
  });
});

describe("visible chart cards", () => {
  it("retains partially visible cards and excludes cards outside every viewport edge", () => {
    const nodes = [
      { id: "partial", x: -220, y: -130 },
      { id: "inside", x: 20, y: 30 },
      { id: "left", x: -229, y: 30 },
      { id: "above", x: 20, y: -137 },
      { id: "right", x: 601, y: 30 },
      { id: "below", x: 20, y: 401 },
    ];
    expect(
      visibleCards(
        nodes,
        { x: 0, y: 0, scale: 1 },
        { width: 600, height: 400 },
        0,
      ).map((node) => node.id),
    ).toEqual(["partial", "inside"]);
  });

  it("converts overscan pixels to world coordinates at the current zoom", () => {
    const nodes = [
      { id: "near", x: 320, y: 0 },
      { id: "far", x: 331, y: 0 },
    ];
    expect(
      visibleCards(
        nodes,
        { x: 0, y: 0, scale: 2 },
        { width: 600, height: 400 },
        60,
      ).map((node) => node.id),
    ).toEqual(["near"]);
  });

  it("caps rendering at 200, prioritizes the viewport center, and preserves input order", () => {
    const nodes = Array.from({ length: 300 }, (_, index) => ({
      id: index,
      x: index * 10,
      y: 0,
    }));
    const result = visibleCards(
      nodes,
      { x: 0, y: 0, scale: 1 },
      { width: 3000, height: 200 },
      0,
    );
    expect(result).toHaveLength(200);
    expect(result.some((node) => node.id === 150)).toBe(true);
    expect(result.map((node) => node.id)).toEqual(
      [...result.map((node) => node.id)].sort((a, b) => a - b),
    );
    expect(nodes).toHaveLength(300);
  });
});

describe("responsive chart anchoring", () => {
  it("preserves the absolute center card and its cell inset when three columns become two", () => {
    // Index73: column1,row24 at three columns; column1,row36 at two.
    const previous = { width: 900, height: 600 };
    const next = { width: 600, height: 500 };
    const scale = 2;
    const center = { x: 252 + 20, y: 24 * 160 + 70 };
    const camera = {
      x: center.x - previous.width / (2 * scale),
      y: center.y - previous.height / (2 * scale),
      scale,
    };
    const result = reanchorGridCamera(camera, previous, next, 1000);
    expect(result.x + next.width / (2 * scale)).toBeCloseTo(252 + 20);
    expect(result.y + next.height / (2 * scale)).toBeCloseTo(36 * 160 + 70);
    expect(reanchorGridCamera(result, next, previous, 1000)).toEqual(camera);
  });

  it("preserves world center when the column count does not change", () => {
    const camera = { x: 80, y: 1600, scale: 2 };
    const previous = { width: 900, height: 600 },
      next = { width: 1100, height: 800 };
    const result = reanchorGridCamera(camera, previous, next, 1000);
    expect(result.x + next.width / (2 * result.scale)).toBe(
      camera.x + previous.width / (2 * camera.scale),
    );
    expect(result.y + next.height / (2 * result.scale)).toBe(
      camera.y + previous.height / (2 * camera.scale),
    );
    expect(result.scale).toBe(camera.scale);
  });

  it("keeps the last real card visible through a drastic resize and incomplete final row", () => {
    const total = 100;
    const previous = { width: 900, height: 500 },
      next = { width: 400, height: 1200 };
    const camera = { x: -250, y: 33 * 160 - 300, scale: 1 };
    const result = reanchorGridCamera(camera, previous, next, total);
    const layout = layoutWindow(
      page(0, total, total).nodes,
      0,
      total,
      next.width,
    );
    const last = layout.nodes.at(-1)!;
    expect(last.y + 136).toBeGreaterThan(result.y);
    expect(last.y).toBeLessThan(result.y + next.height / result.scale);
    expect(result.y).toBeLessThanOrEqual(
      layout.height - next.height / result.scale + 40 / result.scale,
    );
    expect(Object.values(result).every(Number.isFinite)).toBe(true);
  });

  it("centers content when a resize makes it smaller than the viewport", () => {
    const next = { width: 1600, height: 2000 };
    const result = reanchorGridCamera(
      { x: 400, y: 1200, scale: 1 },
      { width: 600, height: 400 },
      next,
      8,
    );
    const bounds = layoutWindow([], 0, 8, next.width);
    expect(result.x).toBe((bounds.width - next.width) / 2);
    expect(result.y).toBe((bounds.height - next.height) / 2);
  });

  it.each([
    [
      { width: 0, height: 0 },
      { width: 0, height: 0 },
    ],
    [
      { width: 900, height: 600 },
      { width: 0, height: 0 },
    ],
    [
      { width: 0, height: 0 },
      { width: 900, height: 600 },
    ],
  ])(
    "handles empty scopes and collapsed viewports with finite coordinates",
    (previous, next) => {
      const result = reanchorGridCamera(
        { x: 0, y: 0, scale: 1 },
        previous,
        next,
        0,
      );
      expect(Object.values(result).every(Number.isFinite)).toBe(true);
      expect(result.x).toBeCloseTo(-next.width / 2);
      expect(result.y).toBeCloseTo(-next.height / 2);
      expect(result.scale).toBe(1);
    },
  );
});

describe("bounded metadata window", () => {
  it("appends an adjacent page and trims the front without moving retained cards", () => {
    const current = page(0, 200);
    const merged = mergePage(current, page(200, 80));
    expect(merged.offset).toBe(40);
    expect(merged.nodes).toHaveLength(240);
    expect(merged.nodes[0].id).toBe("person-40");
    const before = layoutWindow(
      current.nodes,
      current.offset,
      current.total,
      900,
    );
    const after = layoutWindow(merged.nodes, merged.offset, merged.total, 900);
    expect(after.nodes.slice(0, 160)).toEqual(before.nodes.slice(40));
    expect(current.nodes).toHaveLength(200);
  });

  it("prepends an adjacent page and trims the end without moving retained cards", () => {
    const current = page(80, 240);
    const merged = mergePage(current, page(0, 80));
    expect(merged.offset).toBe(0);
    expect(merged.nodes).toHaveLength(240);
    expect(merged.nodes.at(-1)?.id).toBe("person-239");
    const before = layoutWindow(
      current.nodes,
      current.offset,
      current.total,
      900,
    );
    const after = layoutWindow(merged.nodes, merged.offset, merged.total, 900);
    expect(after.nodes.slice(80)).toEqual(before.nodes.slice(0, 160));
  });

  it("deduplicates overlap by absolute index and gives fresh metadata precedence", () => {
    const next = page(50, 100);
    next.nodes[0] = { id: "person-50", value: -1 };
    const merged = mergePage(page(0, 100), next);
    expect(merged.offset).toBe(0);
    expect(merged.nodes).toHaveLength(150);
    expect(new Set(merged.nodes.map((node) => node.id)).size).toBe(150);
    expect(merged.nodes[50].value).toBe(-1);
  });

  it("replaces disjoint pages and inconsistent ordering without inventing missing cards", () => {
    expect(mergePage(page(0, 20), page(200, 20))).toEqual(page(200, 20));
    const reordered = page(20, 20);
    reordered.nodes[0] = { id: "person-0", value: 0 };
    expect(mergePage(page(0, 20), reordered)).toEqual(reordered);
  });

  it("uses the latest total and handles empty, final, and bounded replacement pages", () => {
    expect(mergePage(page(0, 20), page(0, 0, 0))).toEqual({
      nodes: [],
      offset: 0,
      total: 0,
    });
    expect(mergePage(page(0, 20), page(10, 10, 15))).toEqual(page(0, 15, 15));
    expect(mergePage(page(0, 20), page(20, 0, 20))).toEqual(page(0, 20, 20));
    expect(mergePage(page(0, 0), page(900, 100), 40)).toEqual(page(900, 40));
  });

  it("can traverse every person forward and backward with a bounded window", () => {
    let window = page(0, 0, 10000);
    const forward = new Set<string>(),
      backward = new Set<string>();
    for (let offset = 0; offset < 10000; offset += 73) {
      window = mergePage(window, page(offset, 73, 10000));
      expect(window.nodes.length).toBeLessThanOrEqual(240);
      window.nodes.forEach((node, index) => {
        forward.add(node.id);
        expect(node.value).toBe(window.offset + index);
      });
    }
    for (let offset = Math.floor(9999 / 73) * 73; offset >= 0; offset -= 73) {
      window = mergePage(window, page(offset, 73, 10000));
      expect(window.nodes.length).toBeLessThanOrEqual(240);
      window.nodes.forEach((node, index) => {
        backward.add(node.id);
        expect(node.value).toBe(window.offset + index);
      });
    }
    expect(forward.size).toBe(10000);
    expect(backward.size).toBe(10000);
  });
});
