import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { animate, AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { Activity } from "../api";
import LazyGlobe from "./LazyGlobe";
import { KIND, hue } from "./ActivityFeed";
import { duration } from "./ui";

// The run screen's stage: the globe full width, with the live state laid over it. Everything here comes
// from the job's activity lines and progress; nothing is simulated.

export function AnimatedNumber({ value }: { value: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduce) { setShown(value); from.current = value; return; }
    const ctl = animate(from.current, value, { duration: 0.8, ease: [0.2, 0.75, 0.15, 1], onUpdate: (v) => setShown(Math.round(v)) });
    from.current = value;
    return () => ctl.stop();
  }, [value, reduce]);
  return <>{shown.toLocaleString()}</>;
}

// The clock and the "on this step for Ns" counter tick on their own, so the rest of the screen only
// re-renders when new activity arrives.
function Clock({ elapsed, since, live }: { elapsed: number | null; since: string | null; live: boolean }) {
  useTick(live);
  // Before crawling starts the API has no elapsed time yet; count from when the run was created.
  const anchor = useRef<{ at: number; base: number } | null>(null);
  if (elapsed != null && (!anchor.current || Math.abs(anchor.current.base - elapsed) > 2.5)) anchor.current = { at: Date.now(), base: elapsed };
  let clock: number | null = elapsed;
  if (live && elapsed != null && anchor.current) clock = anchor.current.base + (Date.now() - anchor.current.at) / 1000;
  else if (live && elapsed == null && since) clock = Math.max(0, (Date.now() - new Date(since).getTime()) / 1000);
  return <div className="hud-clock mono" aria-label="Elapsed">{clock == null ? "00:00" : duration(clock)}</div>;
}

function Since({ at }: { at: string }) {
  useTick(true);
  return <em className="mono"> · {Math.max(0, Math.round((Date.now() - new Date(at).getTime()) / 1000))}s</em>;
}

// What the run is doing before its first activity line, by state.
const WAITING: Record<string, string> = {
  created: "Starting the run…",
  validating: "Checking the plan and starting websites…",
  planning: "Finding starting pages: asking search sources and registries…",
  queued: "Waiting for a worker to pick the run up…",
};

function useTick(on: boolean) {
  const [, setN] = useState(0);
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setN((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [on]);
}

// A URL that "decodes" into place, so the reading column looks like the crawler at work.
function Decode({ text }: { text: string }) {
  const reduce = useReducedMotion();
  const [out, setOut] = useState(reduce ? text : "");
  useEffect(() => {
    if (reduce) { setOut(text); return; }
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789/._-";
    let frame = 0;
    const total = Math.min(26, 8 + text.length / 3);
    const id = setInterval(() => {
      frame++;
      const k = Math.floor((frame / total) * text.length);
      setOut(text.slice(0, k) + Array.from(text.slice(k, k + 6), () => chars[(Math.random() * chars.length) | 0]).join(""));
      if (frame >= total) { clearInterval(id); setOut(text); }
    }, 28);
    return () => clearInterval(id);
  }, [text, reduce]);
  return <>{out}</>;
}

export default function Mission({ lines, live, state, title, question, elapsed, createdAt, focus, actions, crumbs }: {
  lines: Activity[]; live: boolean; state: string; title: string; question?: string; elapsed: number | null;
  createdAt: string | null; focus: string[]; actions: ReactNode; crumbs: ReactNode;
}) {
  const signals = useMemo(() => lines.map((l) => ({ id: l.id, kind: l.data.kind, site: l.data.site,
    source: (l.data.source as string | undefined) ?? null, at: l.created_at })), [lines]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    const sources = new Set<string>();
    const kept = new Set<string>();
    for (const l of lines) {
      c[l.data.kind] = (c[l.data.kind] ?? 0) + 1;
      if (l.data.kind === "search" && l.data.source) sources.add(String(l.data.source));
      if (l.data.kind === "kept" && l.data.site) kept.add(l.data.site);
    }
    return { ...c, sources: sources.size, keptSites: kept.size } as Record<string, number>;
  }, [lines]);
  const current = lines.at(-1);
  const reading = lines.filter((l) => l.data.kind === "read" && l.data.url).slice(-9);
  const wire = lines.filter((l) => l.data.kind !== "read").slice(-8);
  const k = current ? KIND[current.data.kind] ?? KIND.read : null;

  const stats: [string, number, string][] = [
    ["sources searched", counts.sources || counts.search || 0, "info"],
    ["pages read", counts.read ?? 0, ""],
    ["sites kept", counts.keptSites, "accent"],
    ["details found", counts.found ?? 0, "ok"],
    ["dropped", (counts.dropped ?? 0) + (counts.skipped ?? 0), "muted"],
    ["blocked or failed", (counts.blocked ?? 0) + (counts.failed ?? 0), "bad"],
  ];

  return (
    <section className="mission force-dark" aria-label="Live research">
      <LazyGlobe signals={signals} focus={focus} className="mission-globe" />
      <div className="mission-scrim" aria-hidden />
      <div className="hud">
        <header className="hud-top">
          <div className="hud-title">
            {crumbs}
            <h1>{title}</h1>
            {question && question !== title && <p className="hud-question">“{question}”</p>}
          </div>
          <div className="hud-right">
            <div className={`hud-state ${live ? "is-live" : ""}`}>
              <span className="hud-state-dot" aria-hidden /> {state.replace(/_/g, " ")}
            </div>
            <Clock elapsed={elapsed} since={createdAt} live={live} />
            <div className="hud-actions">{actions}</div>
          </div>
        </header>

        <div className="hud-now" aria-live="polite">
          <span className={live ? "pulse" : "done-dot"} aria-hidden />
          <div className="hud-now-body">
            <span className="hud-now-kind">{live ? (k ? k.label : state.replace(/_/g, " ")) : "Finished"}{live && current && <Since at={current.created_at} />}</span>
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span key={current?.id ?? "none"} className="hud-now-text"
                initial={{ opacity: 0, y: 14, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -14, filter: "blur(6px)" }} transition={{ duration: 0.35, ease: [0.2, 0.75, 0.15, 1] }}>
                {current ? current.message : live ? WAITING[state] ?? "Getting the plan ready…" : "No steps were recorded."}
              </motion.span>
            </AnimatePresence>
          </div>
        </div>

        <div className="hud-reading" aria-label="Pages being read">
          <span className="hud-label">Reading</span>
          <ol>
            {reading.map((l, i) => (
              <li key={l.id} style={{ opacity: 0.25 + (i / Math.max(1, reading.length - 1)) * 0.75 }} className="mono">
                <Decode text={(l.data.url as string).replace(/^https?:\/\/(www\.)?/, "")} />
              </li>
            ))}
            {reading.length === 0 && <li className="mono muted">waiting for the first page…</li>}
          </ol>
        </div>

        <aside className="hud-wire" aria-label="Latest finds and decisions">
          <span className="hud-label">Live wire</span>
          <ul>
            <AnimatePresence initial={false} mode="popLayout">
              {wire.map((l) => {
                const kk = KIND[l.data.kind] ?? KIND.read;
                const site = l.data.site ?? "";
                return (
                  <motion.li key={l.id} layout className={`wire-line k-${kk.cls}`}
                    initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }}
                    exit={{ opacity: 0, x: -20 }} transition={{ type: "spring", stiffness: 420, damping: 34 }}>
                    <span className={`feed-icon ${kk.cls}`} aria-label={kk.label}>{kk.icon}</span>
                    {site ? <span className="feed-site" style={{ "--h": hue(site) } as CSSProperties}>{site.replace(/^www\./, "")[0]?.toUpperCase()}</span>
                      : <span className="feed-site blank" />}
                    <span className="wire-msg">{l.message}</span>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
        </aside>

        <footer className="hud-stats">
          {stats.map(([label, n, cls]) => (
            <div key={label} className={`hud-stat ${cls}`}>
              <b className="mono"><AnimatedNumber value={n} /></b>
              <span>{label}</span>
            </div>
          ))}
        </footer>
        <div className="hud-legend" aria-hidden>
          <span><i className="lg seen" />read</span><span><i className="lg kept" />kept</span><span><i className="lg found" />details</span>
          <span><i className="lg dropped" />dropped</span><span><i className="lg search" />search beam</span>
          {focus.length > 0 && <span><i className="lg focus" />{focus.join(", ")}</span>}
        </div>
      </div>
    </section>
  );
}
