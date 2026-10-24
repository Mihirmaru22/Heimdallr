import type { ReactNode } from "react";
import { ApiError } from "../api";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  return (
    <div className="error" role="alert">
      <strong>{e.message || "Something went wrong"}</strong>
      {e.errors && e.errors.length > 0 && (
        <ul>{e.errors.map((x, i) => <li key={i}>{x.loc.filter((p) => p !== "body").join(".")}: {x.msg}</li>)}</ul>
      )}
    </div>
  );
}

const STATE_CLASS: Record<string, string> = {
  completed: "ok", partially_completed: "warn", failed: "bad", cancelled: "muted", cancel_requested: "muted",
  valid: "ok", partial: "warn", invalid: "bad", fetched: "ok", blocked_robots: "warn", blocked_policy: "bad",
  dead: "bad", skipped: "muted", ready: "ok", pending: "muted",
};

export function Badge({ value }: { value: string }) {
  return <span className={`badge ${STATE_CLASS[value] ?? "info"}`}>{value.replace(/_/g, " ")}</span>;
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && <div className="card-head"><h2>{title}</h2><div>{actions}</div></div>}
      {children}
    </section>
  );
}

export function Pager({ total, limit, offset, onChange }:
  { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return <p className="muted small">{total} total</p>;
  return (
    <div className="pager">
      <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <span className="muted small">{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
      <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

export function when(ts: string | null | undefined): string {
  return ts ? new Date(ts).toLocaleString() : "";
}
