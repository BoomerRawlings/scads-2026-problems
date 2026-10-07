import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { RefObject } from "react";
import { cameraSettled, stepCamera } from "./cameraMotion";
import { zoomAt } from "./semanticZoom";
import type { Camera, Point, Viewport } from "./semanticZoom";

/** Animate only the SVG camera; cards and evidence do not rerender every frame. */
export function useSmoothCamera(
  svgRef: RefObject<SVGSVGElement | null>,
  viewport: Viewport,
) {
  const cameraRef = useRef<Camera>({ x: 0, y: 0, scale: 1 });
  const targetRef = useRef<Camera>({ x: 0, y: 0, scale: 1 });
  const [viewCamera, setViewCamera] = useState<Camera>({
    x: 0,
    y: 0,
    scale: 1,
  });
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const frameRef = useRef<number | null>(null);
  const frameTimeRef = useRef(0);
  const publishedTimeRef = useRef(0);
  const publishTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reducedMotionRef = useRef(false);
  const tickRef = useRef<(time: number) => void>(() => {});

  const draw = useCallback(() => {
    const camera = cameraRef.current;
    const size = viewportRef.current;
    svgRef.current?.setAttribute(
      "viewBox",
      `${camera.x} ${camera.y} ${size.width / camera.scale} ${size.height / camera.scale}`,
    );
  }, [svgRef]);

  const cancelFrame = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
  }, []);

  // Expose enough camera state for culling/prefetch without putting every card
  // through React on every frame. A trailing update preserves the final pan.
  const publish = useCallback((force = false) => {
    const elapsed = performance.now() - publishedTimeRef.current;
    const commit = () => {
      if (publishTimerRef.current !== null)
        clearTimeout(publishTimerRef.current);
      publishTimerRef.current = null;
      publishedTimeRef.current = performance.now();
      const next = { ...cameraRef.current };
      setViewCamera((previous) =>
        previous.x === next.x &&
        previous.y === next.y &&
        previous.scale === next.scale
          ? previous
          : next,
      );
    };
    if (force || elapsed >= 100) commit();
    else if (publishTimerRef.current === null)
      publishTimerRef.current = setTimeout(commit, 100 - elapsed);
  }, []);

  tickRef.current = (time) => {
    frameRef.current = null;
    cameraRef.current = stepCamera(
      cameraRef.current,
      targetRef.current,
      time - frameTimeRef.current,
      reducedMotionRef.current,
    );
    frameTimeRef.current = time;
    draw();
    const settled = cameraSettled(cameraRef.current, targetRef.current);
    if (settled || time - publishedTimeRef.current >= 100) publish();
    if (!settled)
      frameRef.current = requestAnimationFrame((next) => tickRef.current(next));
  };

  const moveTo = useCallback(
    (
      camera: Camera,
      options: { immediate?: boolean; publish?: boolean } = {},
    ) => {
      if (
        !Number.isFinite(camera.x) ||
        !Number.isFinite(camera.y) ||
        !Number.isFinite(camera.scale) ||
        camera.scale <= 0
      )
        return;
      targetRef.current = { ...camera };
      if (options.immediate || reducedMotionRef.current) {
        cancelFrame();
        cameraRef.current = { ...camera };
        draw();
        // Scene changes must cull against the new camera before the next paint.
        // Ordinary immediate pointer panning retains the publication throttle.
        publish(options.publish);
      } else if (frameRef.current === null) {
        frameTimeRef.current = performance.now();
        frameRef.current = requestAnimationFrame((time) =>
          tickRef.current(time),
        );
      }
    },
    [cancelFrame, draw, publish],
  );

  const zoomTo = useCallback(
    (nextScale: number, point: Point) => {
      moveTo(zoomAt(targetRef.current, nextScale, point));
    },
    [moveTo],
  );

  /** Positive pixel deltas scroll toward the right/bottom of the chart. */
  const panBy = useCallback(
    (dxPixels: number, dyPixels: number, immediate = false) => {
      const camera = targetRef.current;
      moveTo(
        {
          ...camera,
          x: camera.x + dxPixels / camera.scale,
          y: camera.y + dyPixels / camera.scale,
        },
        { immediate },
      );
    },
    [moveTo],
  );

  const stop = useCallback(() => {
    cancelFrame();
    targetRef.current = { ...cameraRef.current };
    publish();
  }, [cancelFrame, publish]);

  useLayoutEffect(() => {
    draw();
  }, [draw, viewport.width, viewport.height]);

  useEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const update = () => {
      reducedMotionRef.current = preference?.matches ?? false;
      if (reducedMotionRef.current)
        moveTo(targetRef.current, { immediate: true });
    };
    update();
    preference?.addEventListener("change", update);
    return () => {
      preference?.removeEventListener("change", update);
      cancelFrame();
      if (publishTimerRef.current !== null)
        clearTimeout(publishTimerRef.current);
      publishTimerRef.current = null;
    };
  }, [cancelFrame, moveTo]);

  return {
    cameraRef,
    targetRef,
    viewCamera,
    scale: viewCamera.scale,
    moveTo,
    zoomTo,
    panBy,
    stop,
  };
}
