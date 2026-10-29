import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { BrandMark } from "../components/ui";
import LazyGlobe from "../components/LazyGlobe";
import Ticker from "../components/Ticker";
import { Arrow, Building, Check, Cpu, Database, FileText, Globe, Landmark, Link as LinkIcon, News, Search,
  Sliders, Table } from "../components/icons";

// The public home page: what the product does, how a run works, where it looks and what you get back.
// Signed-out visitors land here; Sign in and Get started open the sign-in page.

function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }} transition={{ duration: 0.7, delay, ease: [0.2, 0.75, 0.15, 1] }}>
      {children}
    </motion.div>
  );
}

const STEPS: [string, string, string, ReactNode][] = [
  ["01", "Ask in plain words", "“Insurance companies in Germany that use Guidewire, with phone and headquarters.” Or build it part by part: who, what must be true, where, which details.", <Search size={20} />],
  ["02", "Check the plan", "A free model turns the question into a plan you can read and edit: the columns, the countries, the sources to search and the ones that count as proof.", <Sliders size={20} />],
  ["03", "Watch it run", "Every search, page read, site kept or dropped shows up live on the globe and in the log, with the reason.", <Globe size={20} />],
  ["04", "Get rows with proof", "A spreadsheet where every value links to the page it came from, plus the sites that were rejected and why.", <Table size={20} />],
];

const SOURCES: [string, string, ReactNode][] = [
  ["Company websites", "About, contact and careers pages, read politely", <Building size={18} />],
  ["Web search", "Self-hosted SearXNG and free search APIs", <Search size={18} />],
  ["SEC EDGAR", "US filings, including full-text proof of product use", <Landmark size={18} />],
  ["GLEIF", "Registered legal entities worldwide", <Database size={18} />],
  ["Wikidata", "Open facts about organisations", <Globe size={18} />],
  ["Case studies", "Vendor and partner customer stories", <FileText size={18} />],
  ["News", "Public news coverage via GDELT", <News size={18} />],
  ["Job boards", "Public job ads linked from the company's own site", <LinkIcon size={18} />],
  ["Website code", "Open fingerprints of the software a site runs", <Cpu size={18} />],
];

const RULES = [
  "Free models only, with no paid model calls",
  "robots.txt respected; sites that refuse are skipped, never bypassed",
  "No guessed emails and no LinkedIn scraping",
  "Every kept value cites the page it came from",
];

// Example questions, scrolling past in two rows (pure CSS animation, paused for reduced motion).
const QUESTIONS = [
  "Insurance companies in Germany that use Guidewire, with phone and headquarters",
  "Pharmaceutical companies in India with their contact email and headquarters",
  "Restaurants selling pizza in Italy, Spain and Portugal",
  "Companies in the UK hiring for SAP S/4HANA roles",
  "Manufacturing plants of a carmaker, with each plant's head",
  "Cybersecurity companies in Israel with their founding year",
  "Hospitals in the US that run Epic, with their address",
  "Defense companies in France with an official website",
];

function Marquee() {
  const rows = [QUESTIONS.slice(0, 4), QUESTIONS.slice(4)];
  return (
    <section className="marquee" aria-label="Example questions">
      {rows.map((row, r) => (
        <div key={r} className={`marquee-row ${r ? "rev" : ""}`}>
          <div className="marquee-track">
            {[...row, ...row].map((q, i) => (
              <span key={i} className="marquee-chip" aria-hidden={i >= row.length}><Search size={14} /> {q}</span>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

// Text that types itself once it scrolls into view.
function Typewriter({ text, active }: { text: string; active: boolean }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (!active || reduce) return;
    setN(0);
    const id = setInterval(() => setN((x) => (x >= text.length ? (clearInterval(id), x) : x + 1)), 32);
    return () => clearInterval(id);
  }, [active, text, reduce]);
  return <>{text.slice(0, n)}<span className="caret" aria-hidden /></>;
}

const STORY_Q = "insurance companies in Germany that use Guidewire, with phone and headquarters";

function StoryVisual({ step }: { step: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div key={step} className="story-visual-in" initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -16, scale: 0.98 }} transition={{ duration: 0.45, ease: [0.2, 0.75, 0.15, 1] }}>
        {step === 0 && (
          <div className="mock-ask">
            <span className="mock-label">Your question</span>
            <div className="mock-input"><Typewriter text={STORY_Q} active /></div>
            <div className="mock-parts">
              {["Find: insurance companies", "Must: use Guidewire", "Where: Germany", "Details: phone, headquarters"].map((p, i) => (
                <motion.span key={p} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 2.4 + i * 0.18 }}>{p}</motion.span>
              ))}
            </div>
          </div>
        )}
        {step === 1 && (
          <div className="mock-plan">
            <span className="mock-label">The plan, ready to check</span>
            {([["Columns", ["Company", "Website", "Phone", "Headquarters"]], ["Countries", ["DE"]],
              ["Finds sites", ["Web search", "GLEIF", "Wikidata"]], ["Proves use", ["Case studies", "Job ads", "News"]]] as [string, string[]][]).map(([k, vs], i) => (
              <motion.div key={k} className="mock-plan-row" initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.15 }}>
                <b>{k}</b><div>{vs.map((v) => <span key={v}>{v}</span>)}</div>
              </motion.div>
            ))}
            <motion.div className="mock-plan-ok" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }}><Check size={14} /> Plan checked, nothing has run yet</motion.div>
          </div>
        )}
        {step === 2 && <Ticker rows={6} />}
        {step === 3 && <SheetRows compact />}
      </motion.div>
    </AnimatePresence>
  );
}

// "How it works" as a scroll story: the steps scroll, the visual on the left follows the step in view.
function Story() {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) setStep(Number((e.target as HTMLElement).dataset.step));
    }, { rootMargin: "-45% 0px -45% 0px" });
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);
  return (
    <div className="story">
      <div className="story-visual"><div className="story-visual-frame"><StoryVisual step={step} /></div></div>
      <div className="story-steps">
        {STEPS.map(([n, title, body, icon], i) => (
          <div key={n} ref={(el) => { refs.current[i] = el; }} data-step={i} className={`story-step ${step === i ? "on" : ""}`}
            onMouseEnter={() => setStep(i)}>
            <div className="land-step-top"><span className="mono">{n}</span><span className="land-step-icon">{icon}</span></div>
            <h3>{title}</h3>
            <p>{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Sources around the question, with pulses running in along each line.
function SourceOrbit() {
  const n = SOURCES.length;
  return (
    <div className="orbit" aria-hidden>
      <svg viewBox="-200 -200 400 400">
        <defs>
          <radialGradient id="orbit-core"><stop offset="0" stopColor="#ff7a45" stopOpacity=".5" /><stop offset="1" stopColor="#ff7a45" stopOpacity="0" /></radialGradient>
        </defs>
        <circle r="150" className="orbit-ring" />
        <circle r="95" className="orbit-ring faint" />
        <circle r="70" fill="url(#orbit-core)" />
        {SOURCES.map((_, i) => {
          const a = (i / n) * Math.PI * 2 - Math.PI / 2;
          const x = Math.cos(a) * 150, y = Math.sin(a) * 150;
          return (
            <g key={i}>
              <line x1={x} y1={y} x2="0" y2="0" className="orbit-line" />
              <circle r="2.6" className="orbit-pulse" style={{ offsetPath: `path("M ${x} ${y} L 0 0")`, animationDelay: `${(i * 0.53) % 3}s` }} />
            </g>
          );
        })}
      </svg>
      {SOURCES.map(([name, , icon], i) => {
        const a = (i / n) * Math.PI * 2 - Math.PI / 2;
        return (
          <span key={name} className="orbit-node" style={{ left: `${50 + Math.cos(a) * 37.5}%`, top: `${50 + Math.sin(a) * 37.5}%`, animationDelay: `${i * 0.4}s` }}>
            {icon}<small>{name}</small>
          </span>
        );
      })}
      <div className="orbit-core-label"><BrandMark /><b>Your question</b></div>
    </div>
  );
}

const SHEET: [string, string, string, string, string][] = [
  ["Nordsee Versicherung", "DE", "case study ↗", "confirmed", "ok"],
  ["Alpenland Assekuranz", "DE", "job ad ↗", "confirmed", "ok"],
  ["Rhein Mutual", "DE", "news ↗", "likely", "warn"],
  ["Tarifvergleich Portal", "DE", "–", "rejected: not an insurer", "no"],
];

// The example sheet fills in row by row when it comes into view.
function SheetRows({ compact = false }: { compact?: boolean }) {
  const ref = useRef<HTMLTableElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  // Inside the story panel it is already on screen when it appears.
  const seen = compact || inView;
  return (
    <table ref={ref} className={compact ? "sheet-compact" : ""} aria-label="Example spreadsheet">
      <thead><tr><th>Company</th><th>Country</th><th>Proof</th><th>Status</th></tr></thead>
      <tbody>
        {SHEET.map(([c, cc, proof, status, cls], i) => (
          <motion.tr key={c} className={cls === "no" ? "dim" : ""} initial={{ opacity: 0, x: -10 }}
            animate={seen ? { opacity: 1, x: 0 } : {}} transition={{ delay: 0.2 + i * 0.22, duration: 0.4 }}>
            <td>{c}</td><td>{cc}</td><td className={proof === "–" ? "" : "proof"}>{proof}</td>
            <td><span className={`tag-${cls}`}>{status}</span></td>
          </motion.tr>
        ))}
      </tbody>
    </table>
  );
}

export default function LandingPage() {
  return (
    <div className="landing force-dark">
      <header className="land-nav">
        <Link to="/" className="brand" aria-label="WebData AI home"><BrandMark /> WebData AI</Link>
        <nav aria-label="Sections">
          <a href="#how">How it works</a><a href="#sources">Where it looks</a><a href="#result">What you get</a>
        </nav>
        <div className="land-nav-cta">
          <Link to="/login" className="btn ghost-btn">Sign in</Link>
          <Link to="/login?mode=register" className="btn primary">Get started <span className="ico-go"><Arrow /></span></Link>
        </div>
      </header>

      <section className="land-hero">
        <div className="land-globe" aria-hidden><LazyGlobe demo labels={false} horizon={0.5} /></div>
        <div className="land-hero-scrim" aria-hidden />
        <Reveal className="land-hero-copy">
          <span className="eyebrow-pill"><span className="pulse" aria-hidden /> Research engine on free models and open data</span>
          <h1>Ask the web a question.<br /><em>Keep only what it can prove.</em></h1>
          <p>WebData AI searches open sources, reads the pages, checks every claim and hands you a spreadsheet where each
            row links to its proof.</p>
          <div className="land-cta">
            <Link to="/login?mode=register" className="btn primary big-btn">Start researching <span className="ico-go"><Arrow /></span></Link>
            <a href="#how" className="btn ghost-btn big-btn">See how it works</a>
          </div>
        </Reveal>
        <Reveal className="land-hero-ticker" delay={0.25}><Ticker rows={5} /></Reveal>
        <Reveal className="land-hero-row" delay={0.4}>
          <div className="row-card" aria-label="Example result row">
            <div className="row-card-head"><Table size={14} /> Example row</div>
            <dl>
              <div><dt>Company</dt><dd>Nordsee Versicherung</dd></div>
              <div><dt>Uses</dt><dd>Guidewire PolicyCenter</dd></div>
              <div><dt>Phone</dt><dd className="mono">+49 40 0000 0000</dd></div>
              <div><dt>Proof</dt><dd className="proof"><LinkIcon size={12} /> case study, page 2</dd></div>
            </dl>
          </div>
        </Reveal>
      </section>

      <Marquee />

      <section className="land-section" id="how">
        <Reveal><h2 className="land-h2"><span>How it works</span>Four steps from a question to a sheet you can trust.</h2></Reveal>
        <Story />
      </section>

      <section className="land-section land-orbit-wrap" id="sources">
        <Reveal className="land-orbit-copy">
          <h2 className="land-h2"><span>Where it looks</span>Open and free sources, one at a time, each one tested.</h2>
          <ul className="land-source-list">
            {SOURCES.map(([name, body, icon]) => (
              <li key={name}><span className="land-source-icon">{icon}</span><div><b>{name}</b><small>{body}</small></div></li>
            ))}
          </ul>
        </Reveal>
        <Reveal delay={0.1} className="land-orbit-stage"><SourceOrbit /></Reveal>
      </section>

      <section className="land-section land-result" id="result">
        <Reveal className="land-result-copy">
          <h2 className="land-h2"><span>What you get</span>A spreadsheet that shows its working.</h2>
          <ul className="land-rules">
            {RULES.map((r) => <li key={r}><span aria-hidden><Check size={14} /></span>{r}</li>)}
          </ul>
        </Reveal>
        <Reveal delay={0.15} className="sheet-mock">
          <div className="sheet-tabs" aria-hidden><span className="on">Results</span><span>Evidence</span><span>Rejected</span><span>Diagnostics</span></div>
          <SheetRows />
          <p className="sheet-note">Example data. Real exports also list every source page and why each site was dropped.</p>
        </Reveal>
      </section>

      <section className="land-final">
        <div className="land-final-glow" aria-hidden />
        <div className="land-final-grid" aria-hidden />
        <Reveal className="land-final-in">
          <span className="land-final-mark"><BrandMark /></span>
          <h2>Ready to ask your first question?</h2>
          <p>Type it the way you would ask a colleague. You check the plan before anything runs.</p>
          <div className="land-cta land-cta-center">
            <Link to="/login?mode=register" className="btn primary big-btn">Create an account <span className="ico-go"><Arrow /></span></Link>
            <Link to="/login" className="btn ghost-btn big-btn">I already have one</Link>
          </div>
        </Reveal>
      </section>
      <footer className="land-foot"><BrandMark /> WebData AI · free models, open sources</footer>
    </div>
  );
}
