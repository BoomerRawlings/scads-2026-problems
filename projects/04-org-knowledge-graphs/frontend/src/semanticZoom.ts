/** Camera coordinates are the world-space top-left of the viewport. */
export type Camera = { x: number; y: number; scale: number };
export type Point = { x: number; y: number };
export type Viewport = { width: number; height: number };

export const CARD_WIDTH = 228;
export const CARD_HEIGHT = 136;
export const CARD_GAP = 24;
export const MIN_ZOOM = 0.45;
export const MAX_ZOOM = 2.4;

/** Keep the same world position under a viewport pixel while changing scale. */
export function zoomAt(
  camera: Camera,
  nextScale: number,
  point: Point,
): Camera {
  // An overview may be fitted below the normal floor. Preserve that floor
  // until the user zooms in; zooming out must never increase magnification.
  const minAllowed = Math.min(MIN_ZOOM, camera.scale);
  const scale = Math.max(minAllowed, Math.min(MAX_ZOOM, nextScale));
  return {
    x: camera.x + point.x / camera.scale - point.x / scale,
    y: camera.y + point.y / camera.scale - point.y / scale,
    scale,
  };
}

export function focusCamera(
  centerWorld: Point,
  viewport: Viewport,
  scale = 1,
): Camera {
  return {
    x: centerWorld.x - viewport.width / (2 * scale),
    y: centerWorld.y - viewport.height / (2 * scale),
    scale,
  };
}

/** Fitting may go below MIN_ZOOM to keep a large bounded overview visible. */
export function fitCamera(
  bounds: Viewport,
  viewport: Viewport,
  padding = 28,
  maxScale = 1,
): Camera {
  const scale = Math.min(
    maxScale,
    Math.max(1, viewport.width - padding * 2) / Math.max(1, bounds.width),
    Math.max(1, viewport.height - padding * 2) / Math.max(1, bounds.height),
  );
  return focusCamera(
    { x: bounds.width / 2, y: bounds.height / 2 },
    viewport,
    scale,
  );
}

/** Stable input order makes department positions predictable between renders. */
export function layoutCards<T>(
  nodes: T[],
  viewportWidth: number,
): { nodes: Array<T & Point>; width: number; height: number } {
  const columns = viewportWidth >= CARD_WIDTH * 3 + CARD_GAP * 2 ? 3 : 2;
  const usedColumns = Math.min(columns, nodes.length);
  const rows = Math.ceil(nodes.length / columns);
  return {
    nodes: nodes.map((node, index) => ({
      ...node,
      x: (index % columns) * (CARD_WIDTH + CARD_GAP),
      y: Math.floor(index / columns) * (CARD_HEIGHT + CARD_GAP),
    })),
    width: usedColumns
      ? usedColumns * CARD_WIDTH + (usedColumns - 1) * CARD_GAP
      : 0,
    height: rows ? rows * CARD_HEIGHT + (rows - 1) * CARD_GAP : 0,
  };
}

/** Separate entry/exit thresholds provide hysteresis between semantic levels. */
export function zoomTransition(
  direction: "in" | "out",
  nextScale: number,
  canEnter: boolean,
  canExit: boolean,
): "enter" | "exit" | null {
  if (direction === "in" && nextScale >= 1.6 && canEnter) return "enter";
  if (direction === "out" && nextScale <= 0.6 && canExit) return "exit";
  return null;
}
