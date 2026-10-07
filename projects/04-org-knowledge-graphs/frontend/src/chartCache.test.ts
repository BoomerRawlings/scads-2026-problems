import { describe, expect, it, vi } from "vitest";
import { createChartCache } from "./chartCache";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((accept, decline) => {
    resolve = accept;
    reject = decline;
  });
  return { promise, resolve, reject };
}

describe("snapshot-scoped chart response cache", () => {
  it("deduplicates concurrent consumers and returns completed data synchronously through peek", async () => {
    const response = deferred<{ nodes: number }>();
    const load = vi.fn(() => response.promise);
    const cache = createChartCache(load);
    const first = cache.get("/chart?snapshot=1");
    const second = cache.get("/chart?snapshot=1");
    expect(first).toBe(second);
    expect(cache.peek("/chart?snapshot=1")).toBeUndefined();
    await Promise.resolve();
    expect(load).toHaveBeenCalledTimes(1);
    const result = { nodes: 100 };
    response.resolve(result);
    expect(await first).toBe(result);
    expect(cache.peek("/chart?snapshot=1")).toBe(result);
    expect(await cache.get("/chart?snapshot=1")).toBe(result);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("keeps snapshot and pagination responses distinct and evicts least-recently used results", async () => {
    const load = vi.fn(async (key: string) => key);
    const cache = createChartCache(load, 2);
    const one = "/chart?snapshot=1&offset=0";
    const two = "/chart?snapshot=2&offset=0";
    const three = "/chart?snapshot=2&offset=30";
    await cache.get(one);
    await cache.get(two);
    await cache.get(one);
    await cache.get(three);
    expect(cache.peek(one)).toBe(one);
    expect(cache.peek(two)).toBeUndefined();
    expect(cache.peek(three)).toBe(three);
    expect(load).toHaveBeenCalledTimes(3);
    await cache.get(two);
    expect(load).toHaveBeenCalledTimes(4);
    expect(cache.peek(one)).toBeUndefined();
  });

  it("never aborts active consumers merely to enforce the resolved-result bound", async () => {
    const slow = deferred<string>();
    let slowSignal!: AbortSignal;
    const cache = createChartCache(async (key, signal) => {
      if (key === "slow") {
        slowSignal = signal;
        return slow.promise;
      }
      return key;
    }, 1);
    const waiting = cache.get("slow");
    await cache.get("quick");
    await cache.get("quicker");
    expect(slowSignal.aborted).toBe(false);
    slow.resolve("completed");
    expect(await waiting).toBe("completed");
    expect(cache.peek("slow")).toBe("completed");
    expect(cache.peek("quicker")).toBeUndefined();
  });

  it("does not retain failures and permits a same-key retry", async () => {
    const load = vi
      .fn<(key: string, signal: AbortSignal) => Promise<string>>()
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce("recovered");
    const cache = createChartCache(load);
    await expect(cache.get("chart")).rejects.toThrow("temporary failure");
    expect(cache.peek("chart")).toBeUndefined();
    expect(await cache.get("chart")).toBe("recovered");
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("clear aborts every request and stale completions cannot overwrite a fresh same-key response", async () => {
    const old = deferred<string>();
    const another = deferred<string>();
    const fresh = deferred<string>();
    const signals: AbortSignal[] = [];
    let call = 0;
    const cache = createChartCache((_key, signal) => {
      signals.push(signal);
      return [old, another, fresh][call++].promise;
    });
    const first = cache.get("chart");
    const second = cache.get("other");
    const firstAbort = expect(first).rejects.toMatchObject({
      name: "AbortError",
    });
    const secondAbort = expect(second).rejects.toMatchObject({
      name: "AbortError",
    });
    await Promise.resolve();
    cache.clear();
    const replacement = cache.get("chart");
    await firstAbort;
    await secondAbort;
    expect(signals.slice(0, 2).every((signal) => signal.aborted)).toBe(true);
    expect(signals[2].aborted).toBe(false);
    old.resolve("stale");
    another.reject(new Error("late network error after abort"));
    await Promise.resolve();
    expect(cache.peek("chart")).toBeUndefined();
    expect(cache.get("chart")).toBe(replacement);
    fresh.resolve("fresh");
    expect(await replacement).toBe("fresh");
    expect(cache.peek("chart")).toBe("fresh");
    cache.clear();
    expect(cache.peek("chart")).toBeUndefined();
  });

  it("clearing immediately prevents even dispatching the queued loader", async () => {
    const load = vi.fn(async () => "unused");
    const cache = createChartCache(load);
    const pending = cache.get("chart");
    const rejection = expect(pending).rejects.toMatchObject({
      name: "AbortError",
    });
    cache.clear();
    await rejection;
    expect(load).not.toHaveBeenCalled();
  });

  it("supports zero retention and rejects invalid capacity", async () => {
    const load = vi.fn(async () => "result");
    const cache = createChartCache(load, 0);
    await cache.get("chart");
    expect(cache.peek("chart")).toBeUndefined();
    await cache.get("chart");
    expect(load).toHaveBeenCalledTimes(2);
    for (const invalid of [-1, 1.5, NaN, Infinity])
      expect(() => createChartCache(load, invalid)).toThrow(RangeError);
  });
});
