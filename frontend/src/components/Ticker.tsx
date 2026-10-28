import { useEffect, useState, type CSSProperties } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { KIND, hue } from "./ActivityFeed";

// A sample run, played on the public pages so a visitor sees what a run looks like before signing in.
// It is labelled as an example and its sites are made up; the real feed lives on the run page.
const SAMPLE: [string, string, string][] = [
  ["search", "", "Searched SearXNG for “insurance companies in Germany using Guidewire” (18 hits)"],
  ["read", "rhein-mutual.de", "Reading rhein-mutual.de/unternehmen"],
  ["search", "", "Asked GLEIF for registered insurers in DE (240 entities)"],
  ["read", "nordsee-versicherung.de", "Reading nordsee-versicherung.de/presse"],
  ["kept", "nordsee-versicherung.de", "Kept nordsee-versicherung.de: case study names Guidewire PolicyCenter"],
  ["found", "nordsee-versicherung.de", "Found phone and headquarters on nordsee-versicherung.de/kontakt"],
  ["dropped", "tarifvergleich-portal.de", "Dropped tarifvergleich-portal.de: a comparison site, not an insurer"],
  ["read", "alpenland-assekuranz.de", "Reading alpenland-assekuranz.de/ueber-uns"],
  ["blocked", "example-insurer.de", "example-insurer.de refused the crawler (robots.txt): skipped"],
  ["kept", "alpenland-assekuranz.de", "Kept alpenland-assekuranz.de: job ad asks for Guidewire ClaimCenter experience"],
  ["records", "", "2 rows written, each with its proof link"],
];

export default function Ticker({ rows = 5, className = "" }: { rows?: number; className?: string }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(rows);
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => setN((x) => x + 1), 1700);
    return () => clearInterval(id);
  }, [reduce]);
  const lines = Array.from({ length: rows }, (_, i) => {
    const k = n - rows + i;
    return { key: k, line: SAMPLE[((k % SAMPLE.length) + SAMPLE.length) % SAMPLE.length] };
  });
  return (
    <div className={`ticker ${className}`} aria-label="Example of a run">
      <div className="ticker-head">
        <span className="pulse" aria-hidden /> <b>Example run</b>
        <span className="mono">insurers in Germany using Guidewire</span>
      </div>
      <ul>
        <AnimatePresence initial={false} mode="popLayout">
          {lines.map(({ key, line: [kind, site, msg] }) => {
            const kk = KIND[kind] ?? KIND.read;
            return (
              <motion.li key={key} layout className={`k-${kk.cls}`}
                initial={{ opacity: 0, y: 16, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.4, ease: [0.2, 0.75, 0.15, 1] }}>
                <span className={`feed-icon ${kk.cls}`} aria-hidden>{kk.icon}</span>
                {site ? <span className="feed-site" style={{ "--h": hue(site) } as CSSProperties}>{site[0].toUpperCase()}</span>
                  : <span className="feed-site blank" />}
                <span className="ticker-msg">{msg}</span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
    </div>
  );
}
