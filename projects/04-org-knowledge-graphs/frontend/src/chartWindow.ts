import { CARD_GAP, CARD_HEIGHT, CARD_WIDTH } from "./semanticZoom";
import type { Camera, Point, Viewport } from "./semanticZoom";

export type ChartWindow<T> = { nodes: T[]; offset: number; total: number };
const gridColumns = (width: number) =>
  width >= CARD_WIDTH * 3 + CARD_GAP * 2 ? 3 : 2;

/** Absolute indices keep cards stationary while the retained metadata window moves. */
export function layoutWindow<T>(
  nodes: T[],
  offset: number,
  total: number,
  viewportWidth: number,
): { nodes: Array<T & Point>; width: number; height: number } {
  const columns = gridColumns(viewportWidth);
  const usedColumns = Math.min(columns, total);
  const rows = Math.ceil(total / columns);
  return {
    nodes: nodes.map((node, index) => ({
      ...node,
      x: ((offset + index) % columns) * (CARD_WIDTH + CARD_GAP),
      y: Math.floor((offset + index) / columns) * (CARD_HEIGHT + CARD_GAP),
    })),
    width: usedColumns
      ? usedColumns * CARD_WIDTH + (usedColumns - 1) * CARD_GAP
      : 0,
    height: rows ? rows * CARD_HEIGHT + (rows - 1) * CARD_GAP : 0,
  };
}

/** Preserve the center's absolute card and cell inset across responsive reflow. */
export function reanchorGridCamera(
  camera: Camera,
  previousViewport: Viewport,
  nextViewport: Viewport,
  total: number,
): Camera {
  const dimension = (value: number) =>
    Number.isFinite(value) ? Math.max(0, value) : 0;
  const previous = {
    width: dimension(previousViewport.width),
    height: dimension(previousViewport.height),
  };
  const next = {
    width: dimension(nextViewport.width),
    height: dimension(nextViewport.height),
  };
  const count = Number.isFinite(total) ? Math.max(0, Math.floor(total)) : 0;
  const scale =
    Number.isFinite(camera.scale) && camera.scale > 0 ? camera.scale : 1;
  const oldColumns = gridColumns(previous.width);
  const newColumns = gridColumns(next.width);
  let centerX =
    (Number.isFinite(camera.x) ? camera.x : 0) + previous.width / (2 * scale);
  let centerY =
    (Number.isFinite(camera.y) ? camera.y : 0) + previous.height / (2 * scale);

  if (count && oldColumns !== newColumns) {
    const column = Math.max(
      0,
      Math.min(oldColumns - 1, Math.floor(centerX / (CARD_WIDTH + CARD_GAP))),
    );
    const row = Math.max(0, Math.floor(centerY / (CARD_HEIGHT + CARD_GAP)));
    const index = Math.min(count - 1, row * oldColumns + column);
    const oldX = (index % oldColumns) * (CARD_WIDTH + CARD_GAP);
    const oldY = Math.floor(index / oldColumns) * (CARD_HEIGHT + CARD_GAP);
    // If the center is in padding or an empty final-row cell, anchor to the
    // nearest point of the last actual cell instead of creating a missing card.
    const insetX = Math.max(0, Math.min(CARD_WIDTH + CARD_GAP, centerX - oldX));
    const insetY = Math.max(
      0,
      Math.min(CARD_HEIGHT + CARD_GAP, centerY - oldY),
    );
    centerX = (index % newColumns) * (CARD_WIDTH + CARD_GAP) + insetX;
    centerY =
      Math.floor(index / newColumns) * (CARD_HEIGHT + CARD_GAP) + insetY;
  }

  const bounds = layoutWindow([], 0, count, next.width);
  const clampAxis = (center: number, span: number, extent: number) => {
    if (extent <= span) return (extent - span) / 2;
    const padding = 40 / scale;
    return Math.max(
      -padding,
      Math.min(extent - span + padding, center - span / 2),
    );
  };
  return {
    x: clampAxis(centerX, next.width / scale, bounds.width),
    y: clampAxis(centerY, next.height / scale, bounds.height),
    scale,
  };
}

/** Overscan is measured in viewport pixels, independent of magnification. */
export function visibleCards<T extends Point>(
  nodes: T[],
  camera: Camera,
  viewport: Viewport,
  overscan = 160,
): T[] {
  const padding = Math.max(0, overscan) / camera.scale;
  const left = camera.x - padding,
    top = camera.y - padding;
  const right = camera.x + viewport.width / camera.scale + padding;
  const bottom = camera.y + viewport.height / camera.scale + padding;
  const visible = nodes.filter(
    (node) =>
      node.x + CARD_WIDTH >= left &&
      node.x <= right &&
      node.y + CARD_HEIGHT >= top &&
      node.y <= bottom,
  );
  if (visible.length <= 200) return visible;

  // An unusually wide overview still has a fixed rendering budget. Favor its center.
  const centerX = camera.x + viewport.width / (2 * camera.scale);
  const centerY = camera.y + viewport.height / (2 * camera.scale);
  const closest = new Set(
    [...visible]
      .sort(
        (a, b) =>
          Math.hypot(
            a.x + CARD_WIDTH / 2 - centerX,
            a.y + CARD_HEIGHT / 2 - centerY,
          ) -
          Math.hypot(
            b.x + CARD_WIDTH / 2 - centerX,
            b.y + CARD_HEIGHT / 2 - centerY,
          ),
      )
      .slice(0, 200),
  );
  return visible.filter((node) => closest.has(node));
}

/** Merge pages from the same snapshot and scope; never compact absolute indices. */
export function mergePage<T extends { id: string }>(
  current: ChartWindow<T>,
  page: ChartWindow<T>,
  maxItems = 240,
): ChartWindow<T> {
  if (!Number.isInteger(maxItems) || maxItems < 1)
    throw new RangeError("maxItems must be a positive integer");
  const total = page.total;
  if (!total) return { nodes: [], offset: 0, total };

  const nextNodes = page.nodes.slice(0, Math.max(0, total - page.offset));
  const oldNodes = current.nodes.slice(0, Math.max(0, total - current.offset));
  const fresh = (): ChartWindow<T> => ({
    nodes: nextNodes.slice(0, maxItems),
    offset: page.offset,
    total,
  });
  if (!oldNodes.length) return fresh();
  if (!nextNodes.length)
    return {
      nodes: oldNodes.slice(0, maxItems),
      offset: current.offset,
      total,
    };

  const oldEnd = current.offset + oldNodes.length;
  const nextEnd = page.offset + nextNodes.length;
  if (page.offset > oldEnd || current.offset > nextEnd) return fresh();

  const offset = Math.min(current.offset, page.offset);
  const end = Math.max(oldEnd, nextEnd);
  const merged: T[] = [];
  for (let index = offset; index < end; index++) {
    merged.push(
      index >= page.offset && index < nextEnd
        ? nextNodes[index - page.offset]
        : oldNodes[index - current.offset],
    );
  }
  // A moved ID indicates a changed ordering. Prefer the new page to avoid inventing
  // contiguous positions by removing duplicates and shifting every following card.
  if (new Set(merged.map((node) => node.id)).size !== merged.length)
    return fresh();

  const trim =
    merged.length > maxItems && page.offset >= current.offset
      ? merged.length - maxItems
      : 0;
  return {
    nodes: merged.slice(trim, trim + maxItems),
    offset: offset + trim,
    total,
  };
}
