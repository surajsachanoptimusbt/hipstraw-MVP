"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Fetch now, then every `ms` milliseconds while the component is shown. `refresh` fetches at once. */
export function usePoll<T>(fetcher: () => Promise<T>, ms: number, key: string = "") {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      const next = await fetchRef.current();
      setData(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      if (alive) await refresh();
    };
    tick();
    const t = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [ms, key, refresh]);

  return { data, error, refresh, setData };
}
