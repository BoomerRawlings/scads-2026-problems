import { describe, expect, it } from "vitest";
import { cameraSettled, stepCamera } from "./cameraMotion";
import { zoomAt } from "./semanticZoom";

describe("smooth camera motion", () => {
  it("advances equally over the same elapsed time at different frame rates", () => {
    const current = { x: -120, y: 320, scale: 0.7 };
    const target = { x: 530, y: -200, scale: 1.9 };
    const advance = (frames: number) => {
      let camera = current;
      for (let frame = 0; frame < frames; frame++)
        camera = stepCamera(camera, target, 120 / frames);
      return camera;
    };
    for (const frames of [1, 8, 16, 24]) {
      const actual = advance(frames);
      expect(actual.x).toBeCloseTo(advance(1).x, 10);
      expect(actual.y).toBeCloseTo(advance(1).y, 10);
      expect(actual.scale).toBeCloseTo(advance(1).scale, 10);
    }
  });

  it.each([0.12, 0.8, 2.4])(
    "keeps the cursor anchored throughout zoom to %s",
    (nextScale) => {
      let camera = { x: -320, y: 240, scale: 0.65 };
      const pointer = { x: 390, y: 217 };
      const world = {
        x: camera.x + pointer.x / camera.scale,
        y: camera.y + pointer.y / camera.scale,
      };
      const target = zoomAt(camera, nextScale, pointer);
      for (let frame = 0; frame < 100; frame++) {
        camera = stepCamera(camera, target, 1000 / 120);
        expect(camera.x + pointer.x / camera.scale).toBeCloseTo(world.x, 8);
        expect(camera.y + pointer.y / camera.scale).toBeCloseTo(world.y, 8);
      }
    },
  );

  it("approaches the target without overshoot and eventually settles exactly", () => {
    let camera = { x: -80, y: 300, scale: 2.3 };
    const target = { x: 800, y: -100, scale: 0.3 };
    for (let frame = 0; frame < 200; frame++) {
      const next = stepCamera(camera, target, 16);
      expect(next.x).toBeGreaterThanOrEqual(camera.x);
      expect(next.x).toBeLessThanOrEqual(target.x);
      expect(next.y).toBeLessThanOrEqual(camera.y);
      expect(next.y).toBeGreaterThanOrEqual(target.y);
      expect(next.scale).toBeLessThanOrEqual(camera.scale);
      expect(next.scale).toBeGreaterThanOrEqual(target.scale);
      camera = next;
    }
    expect(camera).toEqual(target);
    expect(cameraSettled(camera, target)).toBe(true);
  });

  it("keeps accumulated wheel targets without waiting for earlier frames", () => {
    const start = { x: 0, y: 0, scale: 1 };
    const point = { x: 200, y: 300 };
    let target = start;
    for (let index = 0; index < 15; index++)
      target = zoomAt(target, target.scale * 1.025, point);
    expect(target.scale).toBeCloseTo(Math.pow(1.025, 15));
    let camera = start;
    for (let index = 0; index < 100; index++)
      camera = stepCamera(camera, target, 16);
    expect(camera).toEqual(target);
  });

  it("snaps with reduced motion, including fitted overviews below the zoom floor", () => {
    const current = { x: 0, y: 0, scale: 1 };
    const target = { x: -1200, y: -1000, scale: 0.14 };
    expect(stepCamera(current, target, 1, true)).toEqual(target);
    expect(stepCamera(target, target, 0)).toEqual(target);
    expect(stepCamera(current, target, -10)).toEqual(current);
  });
});
