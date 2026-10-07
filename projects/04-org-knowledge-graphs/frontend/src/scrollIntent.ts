export type ScrollMode = "zoom" | "pan";

export type WheelInput = {
  deltaX: number;
  deltaY: number;
  deltaMode: number;
  ctrlKey: boolean;
  shiftKey: boolean;
};

export type ScrollIntent =
  | { kind: "zoom"; logDelta: number }
  | { kind: "pan"; dx: number; dy: number };

const LINE_HEIGHT = 16;
const MAX_ZOOM_DELTA = 120;
const ZOOM_SENSITIVITY = 0.004;

/** Interpret explicit controls and wheel axes, without identifying a device. */
export function normalizeWheel(
  input: WheelInput,
  viewportHeight: number,
  mode: ScrollMode,
): ScrollIntent {
  const pageHeight =
    Number.isFinite(viewportHeight) && viewportHeight > 0
      ? viewportHeight
      : 560;
  const unit =
    input.deltaMode === 1
      ? LINE_HEIGHT
      : input.deltaMode === 2
        ? pageHeight
        : 1;
  const pixels = (delta: number) => {
    if (!Number.isFinite(delta)) return 0;
    // Saturate only numerical overflow; preserve finite page-sized pan motion.
    const bounded = Math.max(
      -Number.MAX_SAFE_INTEGER / unit,
      Math.min(Number.MAX_SAFE_INTEGER / unit, delta),
    );
    return bounded * unit;
  };
  const dx = pixels(input.deltaX),
    dy = pixels(input.deltaY);

  // Browsers expose trackpad pinch as Ctrl+wheel. Keep it available in both modes.
  if (input.ctrlKey)
    return {
      kind: "zoom",
      logDelta:
        -Math.max(-MAX_ZOOM_DELTA, Math.min(MAX_ZOOM_DELTA, dy)) *
        ZOOM_SENSITIVITY,
    };

  // Some browsers already translate Shift+wheel to deltaX; do not translate twice.
  if (input.shiftKey) return { kind: "pan", dx: dx || dy, dy: 0 };
  if (mode === "pan" || Math.abs(dx) > Math.abs(dy))
    return { kind: "pan", dx, dy };

  return {
    kind: "zoom",
    logDelta:
      -Math.max(-MAX_ZOOM_DELTA, Math.min(MAX_ZOOM_DELTA, dy)) *
      ZOOM_SENSITIVITY,
  };
}
