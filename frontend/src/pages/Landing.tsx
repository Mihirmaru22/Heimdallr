import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { BrandMark } from "../components/ui";
import LazyGlobe from "../components/LazyGlobe";
import Ticker from "../components/Ticker";
import { Arrow, Building, Check, Cpu, Database, FileText, Globe, Landmark, Link as LinkIcon, News, Search, Shield,
  Sliders, Table } from "../components/icons";

// The public home page: what the product does, how a run works, where it looks and what you get back.
// Signed-out visitors land here; Sign in and Get started open the sign-in page.

function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.7, delay, ease: [0.2, 0.75, 0.15, 1] }}>
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

      <section className="land-section" id="how">
        <Reveal><h2 className="land-h2"><span>How it works</span>Four steps from a question to a sheet you can trust.</h2></Reveal>
        <div className="land-steps">
          {STEPS.map(([n, title, body, icon], i) => (
            <Reveal key={n} delay={i * 0.08} className="land-step">
              <div className="land-step-top"><span className="mono">{n}</span><span className="land-step-icon">{icon}</span></div>
              <h3>{title}</h3>
              <p>{body}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="land-section" id="sources">
        <Reveal><h2 className="land-h2"><span>Where it looks</span>Open and free sources, one at a time, each one tested.</h2></Reveal>
        <div className="land-sources">
          {SOURCES.map(([name, body, icon], i) => (
            <Reveal key={name} delay={(i % 3) * 0.06} className="land-source">
              <span className="land-source-icon">{icon}</span>
              <div><b>{name}</b><small>{body}</small></div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="land-section land-result" id="result">
        <Reveal className="land-result-copy">
          <h2 className="land-h2"><span>What you get</span>A spreadsheet that shows its working.</h2>
          <ul className="land-rules">
            {RULES.map((r) => <li key={r}><span aria-hidden><Check size={14} /></span>{r}</li>)}
          </ul>
        </Reveal>
        <Reveal delay={0.15} className="sheet-mock" >
          <div className="sheet-tabs" aria-hidden><span className="on">Results</span><span>Evidence</span><span>Rejected</span><span>Diagnostics</span></div>
          <table aria-label="Example spreadsheet">
            <thead><tr><th>Company</th><th>Country</th><th>Proof</th><th>Status</th></tr></thead>
            <tbody>
              <tr><td>Nordsee Versicherung</td><td>DE</td><td className="proof">case study ↗</td><td><span className="tag-ok">confirmed</span></td></tr>
              <tr><td>Alpenland Assekuranz</td><td>DE</td><td className="proof">job ad ↗</td><td><span className="tag-ok">confirmed</span></td></tr>
              <tr><td>Rhein Mutual</td><td>DE</td><td className="proof">news ↗</td><td><span className="tag-warn">likely</span></td></tr>
              <tr className="dim"><td>Tarifvergleich Portal</td><td>DE</td><td>–</td><td><span className="tag-no">rejected: not an insurer</span></td></tr>
            </tbody>
          </table>
          <p className="sheet-note">Example data. Real exports also list every source page and why each site was dropped.</p>
        </Reveal>
      </section>

      <section className="land-final">
        <Reveal>
          <Shield size={28} />
          <h2>Ready to ask your first question?</h2>
          <div className="land-cta center">
            <Link to="/login?mode=register" className="btn primary big-btn">Create an account <span className="ico-go"><Arrow /></span></Link>
            <Link to="/login" className="btn ghost-btn big-btn">I already have one</Link>
          </div>
        </Reveal>
      </section>
      <footer className="land-foot"><BrandMark /> WebData AI · free models, open sources</footer>
    </div>
  );
}
