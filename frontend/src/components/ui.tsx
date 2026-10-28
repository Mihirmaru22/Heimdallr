import type { ReactNode } from "react";
import { Link } from "react-router-dom";
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
  dead: "bad", skipped: "muted", ready: "ok", pending: "muted", queued: "muted", draft: "muted",
  delivered: "ok", country_unconfirmed: "warn", filter_not_met: "warn", elsewhere: "muted", weak_proof: "muted",
  no_proof: "muted",
};
const LIVE = new Set(["created", "validating", "planning", "queued", "running", "waiting_quota", "validating_results", "exporting"]);

export function Badge({ value }: { value: string }) {
  return <span className={`badge ${STATE_CLASS[value] ?? "info"} ${LIVE.has(value) ? "live" : ""}`}>{value.replace(/_/g, " ")}</span>;
}

export function Card({ title, actions, children, className = "" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && <div className="card-head"><h2>{title}</h2><div>{actions}</div></div>}
      {children}
    </section>
  );
}

export function Pager({ total, limit, offset, onChange }:
  { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return <p className="muted small pager">{total.toLocaleString()} total</p>;
  return (
    <div className="pager">
      <span className="muted small">{offset + 1}–{Math.min(offset + limit, total)} of {total.toLocaleString()}</span>
      <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <button disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

export function Crumbs({ items }: { items: [string, string | null][] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {items.map(([label, to], i) => (
        <span key={i} style={{ display: "contents" }}>
          {i > 0 && <span className="sep" aria-hidden>/</span>}
          {to ? <Link to={to}>{label}</Link> : <span aria-current="page">{label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden />;
}

// The globe drawn flat: a globe, an orbit, the beacon at the core and one lit site.
export function BrandMark({ className = "brand-mark" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" strokeWidth="2" />
      <ellipse cx="16" cy="16" rx="14.5" ry="5" fill="none" stroke="currentColor" strokeWidth="1.4" transform="rotate(-24 16 16)" />
      <circle cx="16" cy="16" r="4" fill="var(--accent)" />
      <circle cx="25.5" cy="10.5" r="1.8" fill="currentColor" />
    </svg>
  );
}

export function when(ts: string | null | undefined): string {
  return ts ? new Date(ts).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
}

export function ago(ts: string | null | undefined): string {
  if (!ts) return "";
  const s = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.round(s / 86400)} days ago`;
  return new Date(ts).toLocaleDateString([], { dateStyle: "medium" });
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "–";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}
