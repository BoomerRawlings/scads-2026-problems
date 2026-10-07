/** Keys must include the snapshot and every query parameter affecting a response. */
export function createChartCache<T>(
  load: (key: string, signal: AbortSignal) => Promise<T>,
  capacity = 24,
) {
  if (!Number.isInteger(capacity) || capacity < 0)
    throw new RangeError("Cache capacity must be a nonnegative integer");
  const resolved = new Map<string, T>();
  const pending = new Map<
    string,
    { promise: Promise<T>; controller: AbortController }
  >();

  function get(key: string): Promise<T> {
    if (resolved.has(key)) {
      const value = resolved.get(key)!;
      resolved.delete(key);
      resolved.set(key, value);
      return Promise.resolve(value);
    }
    const existing = pending.get(key);
    if (existing) return existing.promise;

    const controller = new AbortController();
    const abortError = () =>
      new DOMException("Chart request canceled", "AbortError");
    let rejectAborted: () => void;
    const aborted = new Promise<T>((_resolve, reject) => {
      rejectAborted = () => reject(abortError());
      controller.signal.addEventListener("abort", rejectAborted, {
        once: true,
      });
    });
    // The microtask captures synchronous loader errors and avoids dispatching a
    // request cleared immediately after get(). The race also cancels consumers
    // whose loaders do not themselves honor AbortSignal.
    const loading = Promise.resolve().then(() => {
      if (controller.signal.aborted) throw abortError();
      return load(key, controller.signal);
    });
    const entry = {
      controller,
      promise: Promise.race([loading, aborted])
        .then((value) => {
          if (pending.get(key) === entry && !controller.signal.aborted) {
            resolved.set(key, value);
            while (resolved.size > capacity)
              resolved.delete(resolved.keys().next().value!);
          }
          return value;
        })
        .finally(() => {
          controller.signal.removeEventListener("abort", rejectAborted);
          if (pending.get(key) === entry) pending.delete(key);
        }),
    };
    pending.set(key, entry);
    return entry.promise;
  }

  return {
    get,
    /** Observe a cached response without making it more recently used. */
    peek: (key: string): T | undefined => resolved.get(key),
    clear() {
      resolved.clear();
      for (const entry of pending.values()) entry.controller.abort();
      pending.clear();
    },
  };
}
