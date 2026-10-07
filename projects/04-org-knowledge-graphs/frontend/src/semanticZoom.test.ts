import { describe, expect, it } from "vitest";
import {
  CARD_GAP,
  CARD_HEIGHT,
  CARD_WIDTH,
  fitCamera,
  focusCamera,
  layoutCards,
  zoomAt,
  zoomTransition,
} from "./semanticZoom";

describe("semantic zoom camera", () => {
  it.each([0.1, 0.8, 1.7, 6])(
    "keeps the cursor's world point fixed at requested scale %s",
    (nextScale) => {
      const camera = { x: -94, y: 123, scale: 1.2 };
      const pointer = { x: 413, y: 271 };
      const updated = zoomAt(camera, nextScale, pointer);
      expect(updated.x + pointer.x / updated.scale).toBeCloseTo(
        camera.x + pointer.x / camera.scale,
      );
      expect(updated.y + pointer.y / updated.scale).toBeCloseTo(
        camera.y + pointer.y / camera.scale,
      );
      expect(camera).toEqual({ x: -94, y: 123, scale: 1.2 });
    },
  );

  it("bounds direct zoom and can reverse a zoom without drifting", () => {
    const camera = { x: 35, y: -86, scale: 1 };
    const pointer = { x: 200, y: 310 };
    expect(zoomAt(camera, -1, pointer).scale).toBe(0.45);
    expect(zoomAt(camera, 100, pointer).scale).toBe(2.4);
    const restored = zoomAt(zoomAt(camera, 1.9, pointer), 1, pointer);
    expect(restored.x).toBeCloseTo(camera.x);
    expect(restored.y).toBeCloseTo(camera.y);
  });

  it("never reverses zoom direction from an overview fitted below the normal floor", () => {
    const camera = { x: -32, y: -47, scale: 0.14 };
    const pointer = { x: 350, y: 250 };
    const zoomedOut = zoomAt(camera, camera.scale / 1.3, pointer);
    expect(zoomedOut.scale).toBe(camera.scale);
    expect(zoomedOut.x).toBeCloseTo(camera.x);
    expect(zoomedOut.y).toBeCloseTo(camera.y);
    const zoomedIn = zoomAt(camera, camera.scale * 1.3, pointer);
    expect(zoomedIn.scale).toBeCloseTo(0.182);
    expect(zoomedIn.x + pointer.x / zoomedIn.scale).toBeCloseTo(
      camera.x + pointer.x / camera.scale,
    );
    expect(zoomedIn.y + pointer.y / zoomedIn.scale).toBeCloseTo(
      camera.y + pointer.y / camera.scale,
    );
  });

  it("places the requested world point at the viewport center", () => {
    const center = { x: 475, y: 241 };
    const viewport = { width: 920, height: 660 };
    const camera = focusCamera(center, viewport, 1.7);
    expect((center.x - camera.x) * camera.scale).toBeCloseTo(
      viewport.width / 2,
    );
    expect((center.y - camera.y) * camera.scale).toBeCloseTo(
      viewport.height / 2,
    );
    expect(focusCamera(center, viewport).scale).toBe(1);
  });

  it("fits every boundary with padding, even below normal zoom's minimum", () => {
    const bounds = { width: 3000, height: 6000 };
    const viewport = { width: 900, height: 600 };
    const padding = 28;
    const camera = fitCamera(bounds, viewport, padding);
    expect(camera.scale).toBeLessThan(0.45);
    const tolerance = 1e-9;
    expect(-camera.x * camera.scale).toBeGreaterThanOrEqual(
      padding - tolerance,
    );
    expect(-camera.y * camera.scale).toBeGreaterThanOrEqual(
      padding - tolerance,
    );
    expect((bounds.width - camera.x) * camera.scale).toBeLessThanOrEqual(
      viewport.width - padding + tolerance,
    );
    expect((bounds.height - camera.y) * camera.scale).toBeLessThanOrEqual(
      viewport.height - padding + tolerance,
    );
  });

  it("caps fit magnification and handles empty bounds and a collapsed viewport", () => {
    expect(
      fitCamera({ width: 40, height: 40 }, { width: 800, height: 600 }, 28, 1.3)
        .scale,
    ).toBe(1.3);
    const empty = fitCamera({ width: 0, height: 0 }, { width: 0, height: 0 });
    expect(Object.values(empty).every(Number.isFinite)).toBe(true);
    expect(empty.scale).toBeGreaterThan(0);
  });
});

describe("aggregate card layout", () => {
  it.each([600, 900])(
    "retains every card in deterministic, nonoverlapping positions at viewport %s",
    (width) => {
      const cards = Array.from({ length: 107 }, (_, index) => ({
        id: `group-${index}`,
      }));
      const layout = layoutCards(cards, width);
      expect(layout).toEqual(layoutCards(cards, width));
      expect(layout.nodes.map((card) => card.id)).toEqual(
        cards.map((card) => card.id),
      );
      expect(cards.every((card) => !("x" in card))).toBe(true);
      layout.nodes.forEach((card, index) => {
        expect(card.x + CARD_WIDTH).toBeLessThanOrEqual(layout.width);
        expect(card.y + CARD_HEIGHT).toBeLessThanOrEqual(layout.height);
        for (const other of layout.nodes.slice(index + 1)) {
          const separated =
            Math.abs(card.x - other.x) >= CARD_WIDTH + CARD_GAP ||
            Math.abs(card.y - other.y) >= CARD_HEIGHT + CARD_GAP;
          expect(separated).toBe(true);
        }
      });
    },
  );

  it("switches between two and three columns and gives small inputs tight bounds", () => {
    const cards = ["a", "b", "c"].map((id) => ({ id }));
    const threshold = 3 * CARD_WIDTH + 2 * CARD_GAP;
    expect(layoutCards(cards, threshold - 1).nodes[2].y).toBe(
      CARD_HEIGHT + CARD_GAP,
    );
    expect(layoutCards(cards, threshold).nodes[2].y).toBe(0);
    expect(layoutCards(cards.slice(0, 1), 900)).toMatchObject({
      width: CARD_WIDTH,
      height: CARD_HEIGHT,
    });
    expect(layoutCards([], 900)).toEqual({ nodes: [], width: 0, height: 0 });
  });
});

describe("semantic level transitions", () => {
  it("enters only when zooming in across the entry threshold", () => {
    expect(zoomTransition("in", 1.599, true, true)).toBeNull();
    expect(zoomTransition("in", 1.6, true, true)).toBe("enter");
    expect(zoomTransition("in", 2, false, true)).toBeNull();
    expect(zoomTransition("out", 1.6, true, true)).toBeNull();
  });

  it("exits only when zooming out across the exit threshold", () => {
    expect(zoomTransition("out", 0.601, true, true)).toBeNull();
    expect(zoomTransition("out", 0.6, true, true)).toBe("exit");
    expect(zoomTransition("out", 0.4, true, false)).toBeNull();
    expect(zoomTransition("in", 0.6, true, true)).toBeNull();
  });
});
