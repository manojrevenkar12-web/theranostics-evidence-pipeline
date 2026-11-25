import { useCallback, useEffect, useState } from "react";

export type Loadable<T> = { state: "loading" } | { state: "error"; message: string; retry: () => void } | { state: "ready"; data: T };

export function useLoad<T>(load: () => Promise<T>): Loadable<T> {
  const [v, setV] = useState<Loadable<T>>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  useEffect(() => {
    let alive = true;
    setV({ state: "loading" });
    load().then(
      (data) => alive && setV({ state: "ready", data }),
      (e: unknown) => alive && setV({ state: "error", message: e instanceof Error ? e.message : String(e), retry }),
    );
    return () => { alive = false; };
  }, [load, attempt, retry]);
  return v;
}
