import { describe, expect, it } from "vitest";
import { normalizeWheel } from "./scrollIntent";
import type { WheelInput } from "./scrollIntent";

const wheel = (overrides: Partial<WheelInput> = {}): WheelInput => ({
  deltaX: 0,
  deltaY: 0,
  deltaMode: 0,
  ctrlKey: false,
  shiftKey: false,
  ...overrides,
});

describe("chart wheel intent", () => {
  it("preserves default vertical-wheel zoom and its direction", () => {
    expect(normalizeWheel(wheel({ deltaY: -20 }), 600, "zoom")).toEqual({
      kind: "zoom",
      logDelta: 0.08,
    });
    expect(normalizeWheel(wheel({ deltaY: 20 }), 600, "zoom")).toEqual({
      kind: "zoom",
      logDelta: -0.08,
    });
  });

  it("normalizes pixel, line, and page units consistently", () => {
    const pixels = normalizeWheel(wheel({ deltaY: 48 }), 600, "zoom");
    expect(
      normalizeWheel(wheel({ deltaY: 3, deltaMode: 1 }), 600, "zoom"),
    ).toEqual(pixels);
    expect(
      normalizeWheel(wheel({ deltaY: 0.08, deltaMode: 2 }), 600, "zoom"),
    ).toEqual(pixels);
    expect(
      normalizeWheel(wheel({ deltaX: 1, deltaY: 2, deltaMode: 2 }), 600, "pan"),
    ).toEqual({ kind: "pan", dx: 600, dy: 1200 });
  });

  it("keeps small wheel increments additive rather than rounding them away", () => {
    const one = normalizeWheel(wheel({ deltaY: -0.25 }), 600, "zoom");
    const many = normalizeWheel(wheel({ deltaY: -25 }), 600, "zoom");
    if (one.kind !== "zoom" || many.kind !== "zoom")
      throw new Error("Expected zoom");
    expect(one.logDelta * 100).toBeCloseTo(many.logDelta);
  });

  it("pans both axes in explicit pan mode without dropping page-sized movement", () => {
    expect(
      normalizeWheel(wheel({ deltaX: -31.5, deltaY: 800 }), 600, "pan"),
    ).toEqual({ kind: "pan", dx: -31.5, dy: 800 });
  });

  it.each(["zoom", "pan"] as const)(
    "Ctrl+wheel zooms in %s mode, including Shift+Ctrl",
    (mode) => {
      expect(
        normalizeWheel(wheel({ deltaY: -25, ctrlKey: true }), 600, mode),
      ).toEqual({ kind: "zoom", logDelta: 0.1 });
      expect(
        normalizeWheel(
          wheel({ deltaX: 100, deltaY: -25, ctrlKey: true, shiftKey: true }),
          600,
          mode,
        ),
      ).toEqual({ kind: "zoom", logDelta: 0.1 });
    },
  );

  it("maps Shift+wheel to horizontal pan without double-mapping browser-translated input", () => {
    expect(
      normalizeWheel(wheel({ deltaY: 40, shiftKey: true }), 600, "zoom"),
    ).toEqual({ kind: "pan", dx: 40, dy: 0 });
    expect(
      normalizeWheel(wheel({ deltaX: 40, shiftKey: true }), 600, "pan"),
    ).toEqual({ kind: "pan", dx: 40, dy: 0 });
  });

  it("uses dominant horizontal motion for pan without inferring a device", () => {
    expect(
      normalizeWheel(wheel({ deltaX: 30, deltaY: 2 }), 600, "zoom"),
    ).toEqual({ kind: "pan", dx: 30, dy: 2 });
    expect(
      normalizeWheel(wheel({ deltaX: 2, deltaY: 30 }), 600, "zoom"),
    ).toEqual({ kind: "zoom", logDelta: -0.12 });
  });

  it("caps extreme zoom events while retaining direction", () => {
    expect(normalizeWheel(wheel({ deltaY: 9000 }), 600, "zoom")).toEqual({
      kind: "zoom",
      logDelta: -0.48,
    });
    expect(
      normalizeWheel(wheel({ deltaY: -9000, ctrlKey: true }), 600, "pan"),
    ).toEqual({ kind: "zoom", logDelta: 0.48 });
  });

  it("keeps outputs finite for malformed or overflowing input", () => {
    const result = normalizeWheel(
      wheel({ deltaX: Infinity, deltaY: NaN }),
      0,
      "pan",
    );
    expect(result).toEqual({ kind: "pan", dx: 0, dy: 0 });
    const large = normalizeWheel(
      wheel({
        deltaX: -Number.MAX_VALUE,
        deltaY: Number.MAX_VALUE,
        deltaMode: 2,
      }),
      Infinity,
      "pan",
    );
    expect(large.kind).toBe("pan");
    if (large.kind !== "pan") throw new Error("Expected pan");
    expect(Number.isFinite(large.dx) && Number.isFinite(large.dy)).toBe(true);
    expect(large.dx).toBeLessThan(0);
    expect(large.dy).toBeGreaterThan(0);
    expect(
      normalizeWheel(wheel({ deltaY: 1, deltaMode: 2 }), NaN, "pan"),
    ).toEqual({ kind: "pan", dx: 0, dy: 560 });
  });
});
