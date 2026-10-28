import { useEffect, useRef, useState, type CSSProperties } from "react";
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
