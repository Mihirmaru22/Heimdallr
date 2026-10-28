import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { Activity } from "../api";
import { External } from "./icons";

// The live research feed: every line is a step the worker really took (searched a source, read a page,
// kept or dropped a site, found a detail), shown within about a second of it happening.

export const KIND: Record<string, { icon: string; cls: string; label: string }> = {
  search: { icon: "⌕", cls: "info", label: "Search" },
  queued: { icon: "+", cls: "muted", label: "Queued" },
  read: { icon: "→", cls: "muted", label: "Reading" },
  kept: { icon: "✓", cls: "ok", label: "Kept" },
  found: { icon: "★", cls: "ok", label: "Found" },
  links: { icon: "⇢", cls: "muted", label: "Links" },
  records: { icon: "▦", cls: "info", label: "Records" },
  dropped: { icon: "✕", cls: "warn", label: "Dropped" },
  skipped: { icon: "–", cls: "muted", label: "Skipped" },
  blocked: { icon: "⊘", cls: "warn", label: "Blocked" },
  failed: { icon: "!", cls: "bad", label: "Problem" },
};
const FILTERS: Record<string, (k: string) => boolean> = {
  All: () => true,
  Finds: (k) => k === "found" || k === "kept" || k === "records",
  Searches: (k) => k === "search",
  Dropped: (k) => k === "dropped" || k === "skipped",
  Problems: (k) => k === "failed" || k === "blocked",
};

export function hue(site: string) {
  let h = 0;
  for (const ch of site) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function useCounts(lines: Activity[]) {
  return useMemo(() => {
    const c: Record<string, number> = {};
    for (const l of lines) c[l.data.kind] = (c[l.data.kind] ?? 0) + 1;
    return c;
  }, [lines]);
}

// "Now" line: the step the worker is on, and how long it has been on it, ticking every second.
export function NowLine({ lines, live }: { lines: Activity[]; live: boolean }) {
  const current = lines.at(-1);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [live]);
  const since = current ? Math.max(0, Math.round((Date.now() - new Date(current.created_at).getTime()) / 1000)) : 0;
  const k = current ? KIND[current.data.kind] ?? KIND.read : null;
  return (
    <div className={`now ${live ? "is-live" : ""}`} aria-live="polite">
      {live ? <span className="pulse" aria-hidden /> : <span className="done-dot" aria-hidden />}
      <div className="now-body">
        <span className="now-kind">{live ? (k ? k.label : "Starting") : "Finished"}</span>
        <span className="now-text" key={current?.id}>{live ? (current ? current.message : "Getting the plan ready…")
          : current ? `Last step: ${current.message}` : "No steps were recorded."}</span>
      </div>
      {live && current && <span className="now-since mono" title="Time on this step">{since}s</span>}
    </div>
  );
}

export function Tally({ counts }: { counts: Record<string, number> }) {
  const items: [string, number, string][] = [
    ["searches", counts.search ?? 0, "info"],
    ["pages read", counts.read ?? 0, "muted"],
    ["sites kept", counts.kept ?? 0, "ok"],
    ["dropped", (counts.dropped ?? 0) + (counts.skipped ?? 0), "warn"],
    ["pages with details", counts.found ?? 0, "ok"],
    ["blocked or failed", (counts.blocked ?? 0) + (counts.failed ?? 0), "bad"],
  ];
  return (
    <dl className="tally">
      {items.map(([label, n, cls]) => (
        <div key={label} className={`tally-item ${cls}`}><dt>{label}</dt><dd className="mono">{n.toLocaleString()}</dd></div>
      ))}
    </dl>
  );
}

export default function ActivityFeed({ lines, live, error }: { lines: Activity[]; live: boolean; error: string | null }) {
  const [filter, setFilter] = useState("All");
  const [showReads, setShowReads] = useState(true);
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, follow, filter, showReads]);

  const shown = lines.filter((l) => FILTERS[filter](l.data.kind) && (showReads || l.data.kind !== "read"));

  return (
    <section className="feed-panel" aria-label="Live research feed">
      <div className="feed-controls">
        <div className="segmented" role="group" aria-label="Show">
          {Object.keys(FILTERS).map((f) =>
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>)}
        </div>
        <label className="switch">
          <input type="checkbox" checked={showReads} onChange={(e) => setShowReads(e.target.checked)} />
          <span className="switch-track" aria-hidden /> Every page read</label>
      </div>
      <div className="feed" ref={box} role="log" aria-live="off" tabIndex={0}
        onScroll={(e) => {
          const el = e.currentTarget;
          setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}>
        {shown.length === 0 && <p className="feed-empty">{live ? "Waiting for the first step…" : "No activity recorded for this job."}</p>}
        {shown.map((l) => {
          const k = KIND[l.data.kind] ?? KIND.read;
          const site = l.data.site ?? "";
          return (
            <div key={l.id} className={`feed-line k-${k.cls}`}>
              <span className="feed-time mono">{time(l.created_at)}</span>
              <span className={`feed-icon ${k.cls}`} title={k.label} aria-label={k.label}>{k.icon}</span>
              {site ? <span className="feed-site" style={{ "--h": hue(site) } as CSSProperties} title={site}>
                {site.replace(/^www\./, "")[0]?.toUpperCase()}</span> : <span className="feed-site blank" />}
              <span className="feed-msg">
                {l.message}
                {l.data.url && l.data.kind !== "read" && (
                  <a href={l.data.url} target="_blank" rel="noreferrer noopener" className="feed-open" aria-label="Open page">
                    <External size={12} /></a>)}
              </span>
            </div>
          );
        })}
      </div>
      {!follow && <button type="button" className="jump" onClick={() => setFollow(true)}>Jump to latest ↓</button>}
      {error && <p className="error small">Live feed paused: {error}. Retrying…</p>}
    </section>
  );
}
