import type { ReactNode } from "react";
import type { Loadable } from "../data/useLoad";
import s from "./StateView.module.css";

interface Props<T> { value: Loadable<T>; children: (data: T) => ReactNode }

/** Every data view goes through here: a skeleton while loading, an error with a retry, then the content. */
export function StateView<T>({ value, children }: Props<T>) {
  if (value.state === "loading") {
    return (
      <div className={s.skeleton} role="status" aria-label="Loading the lab report">
        <div className={s.barWide} /><div className={s.bar} /><div className={s.block} />
      </div>
    );
  }
  if (value.state === "error") {
    return (
      <div className={s.error} role="alert">
        <p>{value.message}</p>
        <button onClick={value.retry}>Try again</button>
      </div>
    );
  }
  return <>{children(value.data)}</>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className={s.empty}>{children}</p>;
}
