import type { Camera } from "./semanticZoom";

/** A time constant, rather than a per-frame factor, keeps trackpads and 120 Hz screens consistent. */
export const CAMERA_RESPONSE_MS = 90;

export function cameraSettled(current: Camera, target: Camera): boolean {
  return (
    Math.abs(current.x - target.x) * target.scale < 0.025 &&
    Math.abs(current.y - target.y) * target.scale < 0.025 &&
    Math.abs(current.scale / target.scale - 1) < 0.000025
  );
}

/**
 * Interpolate viewBox dimensions (inverse scale), not magnification. When both
 * endpoints preserve a cursor's world point, every intermediate frame does too.
 */
export function stepCamera(
  current: Camera,
  target: Camera,
  elapsedMs: number,
  reducedMotion = false,
): Camera {
  if (reducedMotion || cameraSettled(current, target)) return { ...target };
  const fraction = -Math.expm1(-Math.max(0, elapsedMs) / CAMERA_RESPONSE_MS);
  const next = {
    x: current.x + (target.x - current.x) * fraction,
    y: current.y + (target.y - current.y) * fraction,
    scale:
      1 /
      (1 / current.scale + (1 / target.scale - 1 / current.scale) * fraction),
  };
  return cameraSettled(next, target) ? { ...target } : next;
}
