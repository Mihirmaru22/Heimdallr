import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { Activity } from "../api";
import { KIND, hue } from "./ActivityFeed";
import { AnimatedNumber } from "./AnimatedNumber";
import { duration } from "./ui";
import { External } from "./icons";
import LazyGlobe from "./LazyGlobe";
import "./research.css";

// The run screen as a live research view. Every row is a step the worker really took, grouped the way a
// person would follow it: each search source is one step, each website is one step. A step that is still
// moving shows what it is doing right now; a finished one folds into one line. Nothing here is simulated:
// when the worker is quiet, the screen is quiet and says for how long.

export type ResearchStat = { label: string; value: number; cls?: string; hint?: string };

type Block = {
  key: string;
  type: "source" | "site" | "note";
  name: string; // the source key or the website
  lines: Activity[];
  first: number; // index of the block's first line, for ordering
  lastAt: number; // ms timestamp of its latest line
};

// A step is "working" while lines keep arriving for it; after this long without one it counts as settled.
const ACTIVE_MS = 12_000;
const SHOWN_BLOCKS = 80;

const at = (l: Activity) => new Date(l.created_at).getTime();
const short = (url: string) => url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
const path = (url: string) => { try { const u = new URL(url); return (u.pathname + u.search) || "/"; } catch { return url; } };
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

// Proof checks (job ads, site code, a customer story) report under their own source but are about a website.
const ABOUT_A_SITE = new Set(["proof", "jobs"]);

function group(lines: Activity[]): Block[] {
  const blocks = new Map<string, Block>();
  let checkedSite: string | null = null; // the website a proof check was last reading, for the verdict that follows
  lines.forEach((l, i) => {
    const source = typeof l.data.source === "string" ? l.data.source : null;
    let site = l.data.site ?? null;
    // A verdict links to where the proof is (a job board, a vendor page); it belongs to the website being checked.
    if (source && ABOUT_A_SITE.has(source)) {
      if (site && blocks.has(`site:${site}`)) checkedSite = site;
      else if (checkedSite) site = checkedSite;
    }
    let key: string, type: Block["type"], name: string;
    if (source && !ABOUT_A_SITE.has(source)) [key, type, name] = [`src:${source}`, "source", source];
    else if (site) [key, type, name] = [`site:${site}`, "site", site];
    else [key, type, name] = [`note:${l.id}`, "note", ""];
    let b = blocks.get(key);
    if (!b) blocks.set(key, (b = { key, type, name, lines: [], first: i, lastAt: 0 }));
    b.lines.push(l);
    b.lastAt = at(l);
  });
  return [...blocks.values()].sort((a, b) => a.first - b.first);
}

function useNow(on: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [on]);
  return now;
}

function Favicon({ site }: { site: string }) {
  return site
    ? <span className="rs-fav" style={{ "--h": hue(site) } as CSSProperties} title={site}>{site.replace(/^www\./, "")[0]?.toUpperCase()}</span>
    : <span className="rs-fav blank" />;
}

function Spinner() {
  return <span className="rs-spin" aria-hidden />;
}

function Elapsed({ elapsed, since, live, now }: { elapsed: number | null; since: string | null; live: boolean; now: number }) {
  // The API's elapsed time is anchored when it arrives and counted on locally, so the clock moves every second.
  const anchor = useRef<{ at: number; base: number } | null>(null);
  if (elapsed != null && (!anchor.current || Math.abs(anchor.current.base - elapsed) > 2.5)) anchor.current = { at: Date.now(), base: elapsed };
  let s: number | null = elapsed;
  if (live && elapsed != null && anchor.current) s = anchor.current.base + (now - anchor.current.at) / 1000;
  else if (live && elapsed == null && since) s = (now - new Date(since).getTime()) / 1000;
  return <span className="rs-clock mono" aria-label="Elapsed">{s == null ? "0s" : duration(Math.max(0, s))}</span>;
}

// One action inside a step: an icon, what was done, a link to the page when there is one.
function Action({ l, fresh }: { l: Activity; fresh: boolean }) {
  const reduce = useReducedMotion();
  const k = KIND[l.data.kind] ?? KIND.read;
  const url = typeof l.data.url === "string" ? l.data.url : null;
  return (
    <motion.li className={`rs-act k-${k.cls}`} initial={fresh && !reduce ? { opacity: 0, x: -8 } : false}
      animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25 }}>
      <span className="rs-act-time mono">{clock(l.created_at)}</span>
      <span className={`rs-act-icon ${k.cls}`} aria-label={k.label}>{k.icon}</span>
      <span className="rs-act-msg">{l.message}
        {url && <a href={url} target="_blank" rel="noreferrer noopener" className="rs-open" aria-label="Open page"><External size={11} /></a>}
      </span>
    </motion.li>
  );
}

function summary(b: Block, working: boolean): { icon: ReactNode; title: ReactNode; sub?: string; cls: string } {
  const count = (kind: string) => b.lines.filter((l) => l.data.kind === kind).length;
  const last = b.lines.at(-1)!;
  if (b.type === "note") {
    const k = KIND[last.data.kind] ?? KIND.read;
    return { icon: <span className={`rs-act-icon ${k.cls}`}>{k.icon}</span>, title: last.message, cls: "note" };
  }
  if (b.type === "source") {
    const queued = count("queued");
    const reads = count("read");
    const head = b.lines.find((l) => l.data.kind === "search") ?? b.lines[0];
    const bits = [reads && `${reads} page${reads === 1 ? "" : "s"} opened`, queued && `${queued} site${queued === 1 ? "" : "s"} lined up`]
      .filter(Boolean).join(" · ");
    return { icon: working ? <Spinner /> : <span className="rs-done info">⌕</span>, title: head.message,
      sub: working ? last.message : bits || last.message, cls: "source" };
  }
  const reads = count("read");
  const finds = count("found");
  const decision = [...b.lines].reverse().find((l) => !l.data.source && (l.data.kind === "kept" || l.data.kind === "dropped"));
  const verb = working ? "Working on" : decision?.data.kind === "dropped" ? "Dropped" : decision ? "Kept" : reads ? "Read" : "Checked";
  const cls = working ? "site working" : decision?.data.kind === "dropped" ? "site dropped" : decision ? "site kept" : "site";
  const bits = [reads && `${reads} page${reads === 1 ? "" : "s"}`, finds && `${finds} find${finds === 1 ? "" : "s"}`].filter(Boolean).join(" · ");
  return {
    icon: working ? <Spinner /> : <span className={`rs-done ${decision?.data.kind === "dropped" ? "warn" : decision ? "ok" : "muted"}`}>
      {decision?.data.kind === "dropped" ? "✕" : decision ? "✓" : "·"}</span>,
    title: <><Favicon site={b.name} /><span className="rs-verb">{verb}</span> <b>{b.name.replace(/^www\./, "")}</b>
      {bits && <span className="rs-bits mono">{bits}</span>}</>,
    sub: working ? undefined : decision?.message,
    cls,
  };
}

function Step({ b, working, freshFrom }: { b: Block; working: boolean; freshFrom: number }) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const s = summary(b, working);
  if (b.type === "note") {
    return <motion.li className="rs-step note" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}>
      {s.icon}<span>{s.title}</span></motion.li>;
  }
  // While a step works, its newest actions stream underneath it; once settled it folds to one line.
  const tail = working ? b.lines.filter((l) => l.data.kind !== "queued").slice(-4) : open ? b.lines : [];
  const lined = b.type === "source" ? b.lines.filter((l) => l.data.kind === "queued" && l.data.site).map((l) => l.data.site as string) : [];
  return (
    <motion.li className={`rs-step ${s.cls}`} layout={!reduce ? "position" : false}
      initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <button type="button" className="rs-head" onClick={() => setOpen((o) => !o)} aria-expanded={working || open}>
        <span className="rs-icon">{s.icon}</span>
        <span className="rs-title">
          <span className={working ? "rs-shimmer" : ""}>{s.title}</span>
          {s.sub && <span className="rs-sub">{s.sub}</span>}
        </span>
        {!working && <span className="rs-more muted small">{open ? "hide" : `${b.lines.length} step${b.lines.length === 1 ? "" : "s"}`}</span>}
      </button>
      {lined.length > 0 && (working || !open) && (
        <div className="rs-stack" aria-label="Sites lined up">
          {lined.slice(0, 14).map((site) => <Favicon key={site} site={site} />)}
          {lined.length > 14 && <span className="muted small mono">+{lined.length - 14}</span>}
        </div>
      )}
      {tail.length > 0 && (
        <ul className="rs-acts">
          <AnimatePresence initial={false}>
            {tail.map((l) => <Action key={l.id} l={l} fresh={l.id > freshFrom} />)}
          </AnimatePresence>
          {working && b.lines.at(-1)?.data.kind === "read" && (
            <li className="rs-act opening"><span className="rs-act-time" /><Spinner />
              <span className="rs-act-msg rs-shimmer">Opening {short(String(b.lines.at(-1)!.data.url ?? ""))}</span></li>
          )}
        </ul>
      )}
    </motion.li>
  );
}

export default function Research({ lines, live, state, title, question, elapsed, createdAt, focus, stats, summary: done, actions, crumbs }: {
  lines: Activity[]; live: boolean; focus: string[]; state: string; title: string; question?: string; elapsed: number | null;
  createdAt: string | null; stats: ResearchStat[]; summary?: string; actions: ReactNode; crumbs: ReactNode;
}) {
  const now = useNow(live);
  const blocks = useMemo(() => group(lines), [lines]);
  // The globe draws the same lines: a beam per search, a dot per page read, a flare per site kept.
  const signals = useMemo(() => lines.map((l) => ({ id: l.id, kind: l.data.kind, site: l.data.site,
    source: (l.data.source as string | undefined) ?? null, at: l.created_at })), [lines]);
  const [all, setAll] = useState(false);
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  // Lines already on screen when the page opened are history; only newer ones animate in.
  const firstSeen = useRef<number | null>(null);
  if (firstSeen.current == null && (lines.length || !live)) firstSeen.current = lines.at(-1)?.id ?? 0;

  const isWorking = (b: Block) => live && b.type !== "note" && now - b.lastAt < ACTIVE_MS;
  const working = blocks.filter(isWorking);
  const hidden = all ? 0 : Math.max(0, blocks.length - SHOWN_BLOCKS);
  const shown = hidden ? blocks.slice(hidden) : blocks;
  const current = lines.at(-1);
  const quiet = current ? Math.max(0, Math.round((now - at(current)) / 1000)) : 0;

  const evidence = lines.filter((l) => l.data.source && (l.data.kind === "kept" || l.data.kind === "dropped"));
  const accepted = evidence.filter((l) => l.data.kind === "kept").length;
  const sources = blocks.filter((b) => b.type === "source").length;
  const sites = blocks.filter((b) => b.type === "site").length;

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines, follow, now]);

  return (
    <section className="rs" aria-label="Live research">
      <div className="rs-stage force-dark">
      <LazyGlobe signals={signals} focus={focus} className="rs-globe" />
      <div className="rs-scrim" aria-hidden />
      <div className="rs-stage-grid">
      <header className="rs-top">
        <div className="rs-title-block">
          {crumbs}
          <h1>{title}</h1>
          {question && question !== title && <p className="rs-question">“{question}”</p>}
        </div>
        <div className="rs-top-right">
          <span className={`rs-state ${live ? "is-live" : ""}`}><span className="rs-state-dot" aria-hidden />{state.replace(/_/g, " ")}</span>
          <Elapsed elapsed={elapsed} since={createdAt} live={live} now={now} />
          <div className="rs-actions">{actions}</div>
        </div>
      </header>

      <div className="rs-now" aria-live="polite">
        {live ? <Spinner /> : <span className="rs-done ok">✓</span>}
        <div className="rs-now-body">
          <span className="rs-now-label">
            {live ? (working.length > 1 ? `Working on ${working.length} things at once` : "Working") : "Finished"}
            {live && current && <span className="mono"> · last step {quiet}s ago</span>}
          </span>
          <span className={`rs-now-text ${live ? "rs-shimmer" : ""}`}>
            {live ? current?.message ?? "Getting the plan ready…" : done ?? current?.message ?? "No steps were recorded."}
          </span>
        </div>
        <div className="rs-tally mono" aria-label="So far">
          <span><b><AnimatedNumber value={sources} /></b> sources</span>
          <span><b><AnimatedNumber value={sites} /></b> websites</span>
          <span><b><AnimatedNumber value={accepted} /></b>/<AnimatedNumber value={evidence.length} /> proofs accepted</span>
        </div>
      </div>
      <div className="rs-rail-card rs-progress" aria-label="In progress">
        <span className="rs-label">In progress</span>
        {working.length === 0 && <p className="muted small">{live ? "Nothing moving this second." : "Nothing running."}</p>}
        <ul className="rs-lanes">
          <AnimatePresence initial={false}>
            {working.filter((b) => b.type === "site").slice(-8).map((b) => {
              const read = [...b.lines].reverse().find((l) => l.data.kind === "read" && l.data.url);
              return (
                <motion.li key={b.key} className="rs-lane" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}>
                  <Favicon site={b.name} />
                  <span className="rs-lane-body"><b>{b.name.replace(/^www\./, "")}</b>
                    <span className="mono muted">{read ? path(String(read.data.url)) : KIND[b.lines.at(-1)!.data.kind]?.label ?? ""}</span>
                  </span>
                  <span className="rs-bar" aria-hidden />
                </motion.li>
              );
            })}
            {working.filter((b) => b.type === "source").map((b) => (
              <motion.li key={b.key} className="rs-lane" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
                <span className="rs-fav src">⌕</span>
                <span className="rs-lane-body"><b>{(b.lines.find((l) => l.data.kind === "search") ?? b.lines[0]).message}</b></span>
                <span className="rs-bar" aria-hidden />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      </div>
      <div className="rs-legend" aria-hidden>
        <span><i className="lg search" />search</span><span><i className="lg seen" />page read</span><span><i className="lg kept" />kept</span>
        <span><i className="lg found" />detail found</span><span><i className="lg dropped" />dropped</span>
        {focus.length > 0 && <span><i className="lg focus" />{focus.join(", ")}</span>}
      </div>
      </div>
      </div>

      <div className="rs-body">
        <div className="rs-stream-wrap">
          <div className="rs-stream" ref={box} role="log" aria-live="off" tabIndex={0}
            onScroll={(e) => { const el = e.currentTarget; setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 60); }}>
            {hidden > 0 && <button type="button" className="rs-earlier" onClick={() => setAll(true)}>Show {hidden.toLocaleString()} earlier steps</button>}
            {shown.length === 0 && <p className="rs-empty">{live ? <><Spinner /> Waiting for the first step…</> : "No steps were recorded for this run."}</p>}
            <ol className="rs-steps">
              {shown.map((b) => <Step key={b.key} b={b} working={isWorking(b)} freshFrom={firstSeen.current ?? 0} />)}
            </ol>
          </div>
          {!follow && <button type="button" className="rs-jump" onClick={() => setFollow(true)}>Jump to latest ↓</button>}
        </div>

        <aside className="rs-rail" aria-label="Run totals">
          <div className="rs-rail-card">
            <span className="rs-label">Totals</span>
            <dl className="rs-stats">
              {stats.map(({ label, value, cls = "", hint }) => (
                <div key={label} className={`rs-stat ${cls}`} title={hint}><dt>{label}</dt><dd className="mono"><AnimatedNumber value={value} /></dd></div>
              ))}
            </dl>
          </div>
          {evidence.length > 0 && (
            <div className="rs-rail-card">
              <span className="rs-label">Latest proof checks</span>
              <ul className="rs-proofs">
                {evidence.slice(-5).reverse().map((l) => (
                  <li key={l.id} className={l.data.kind === "kept" ? "rs-yes" : "rs-no"}>
                    <span>{l.data.kind === "kept" ? "✓" : "✕"}</span>
                    <span className="small">{l.message.length > 180 ? `${l.message.slice(0, 180)}…` : l.message}
                      {typeof l.data.url === "string" && <a href={l.data.url} target="_blank" rel="noreferrer noopener" className="rs-open" aria-label="Open source"><External size={11} /></a>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
