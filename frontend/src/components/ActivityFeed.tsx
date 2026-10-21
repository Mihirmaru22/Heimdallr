import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Activity } from "../api";

// The live research feed: every line is a step the worker really took (searched a source, read a page,
// kept or dropped a site, found a detail), shown within about a second of it happening.

const KIND: Record<string, { icon: string; cls: string; label: string }> = {
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
  Dropped: (k) => k === "dropped" || k === "skipped",
  Problems: (k) => k === "failed" || k === "blocked",
};
const MAX_LINES = 3000;

function hue(site: string) {
  let h = 0;
  for (const ch of site) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function ActivityFeed({ base, jobId, live }: { base: string; jobId: string; live: boolean }) {
  const [lines, setLines] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("All");
  const [showReads, setShowReads] = useState(true);
  const [follow, setFollow] = useState(true);
  const lastId = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const fresh = await api.get<Activity[]>(`${base}/jobs/${jobId}/activity?after_id=${lastId.current}&limit=500`);
        if (stopped) return;
        setError(null);
        if (fresh.length) {
          lastId.current = fresh[fresh.length - 1].id;
          setLines((old) => [...old, ...fresh].slice(-MAX_LINES));
        }
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
      // Keep polling while the job runs; once it has finished, one more pass picks up the last lines.
      if (!stopped && live) timer = setTimeout(poll, 1000);
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [base, jobId, live]);

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, follow, filter, showReads]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const l of lines) c[l.data.kind] = (c[l.data.kind] ?? 0) + 1;
    return c;
  }, [lines]);
  const shown = lines.filter((l) => FILTERS[filter](l.data.kind) && (showReads || l.data.kind !== "read"));
  const current = lines.at(-1);

  return (
    <section className="card activity">
      <div className="activity-now">
        {live ? <span className="pulse" aria-hidden /> : <span className="done-dot" aria-hidden />}
        <span className="now-text">{live ? (current ? current.message : "Starting…") : "Finished"}</span>
      </div>
      <div className="activity-tally small">
        <span>{counts.read ?? 0} pages read</span>
        <span className="ok">{counts.kept ?? 0} sites kept</span>
        <span className="warn">{counts.dropped ?? 0} dropped</span>
        <span className="ok">{counts.found ?? 0} pages with details</span>
        <span className="muted">{(counts.blocked ?? 0) + (counts.failed ?? 0)} blocked or failed</span>
      </div>
      <div className="row wrap activity-controls">
        {Object.keys(FILTERS).map((f) =>
          <button key={f} className={filter === f ? "chip active" : "chip"} onClick={() => setFilter(f)}>{f}</button>)}
        <label className="check small"><input type="checkbox" checked={showReads}
          onChange={(e) => setShowReads(e.target.checked)} /> Show every page read</label>
        {!follow && <button className="link small" onClick={() => setFollow(true)}>Jump to latest ↓</button>}
      </div>
      <div className="feed" ref={box} role="log" aria-live="polite"
        onScroll={(e) => {
          const el = e.currentTarget;
          setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
        }}>
        {shown.length === 0 && <p className="muted small">{live ? "Waiting for the first step…" : "No activity recorded for this job."}</p>}
        {shown.map((l) => {
          const k = KIND[l.data.kind] ?? KIND.read;
          const site = l.data.site ?? "";
          return (
            <div key={l.id} className={`feed-line ${k.cls}`}>
              <span className="feed-time">{time(l.created_at)}</span>
              <span className={`feed-icon ${k.cls}`} title={k.label}>{k.icon}</span>
              {site ? <span className="feed-site" style={{ background: `hsl(${hue(site)} 55% 45%)` }} title={site}>
                {site[0]?.toUpperCase()}</span> : <span className="feed-site blank" />}
              <span className="feed-msg">
                {l.message}
                {l.data.url && l.data.kind !== "read" && <> <a href={l.data.url} target="_blank" rel="noreferrer noopener"
                  className="small">open</a></>}
              </span>
            </div>
          );
        })}
      </div>
      {error && <p className="error small">Live feed paused: {error}. Retrying…</p>}
    </section>
  );
}
