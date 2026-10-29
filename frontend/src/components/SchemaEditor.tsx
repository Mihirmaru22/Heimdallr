import { useEffect, useState, type ReactNode } from "react";
import type { FieldSpec, Spec } from "../api";
import { Field, Section, TagInput, Toggle } from "./form";
import { Building, Code, Cpu, Database, FileText, Filter, Gauge, Globe, Landmark, Link, List, News, Search, Shield, Tag, User } from "./icons";
import { REGIONS } from "./SearchForm";

const TYPES = ["string", "text", "url", "email", "phone", "number", "integer", "date", "boolean", "list"];
// Where websites come from: [key, name, what it is, finds or proves].
const SOURCES: [string, string, string, "finds" | "proves", ReactNode][] = [
  ["seeds", "Start URLs", "Only the websites you list", "finds", <Link key="l" />],
  ["wikidata", "Wikidata", "Open knowledge base of organisations", "finds", <Database key="d" />],
  ["searxng", "Web search", "SearXNG plus the search APIs set up", "finds", <Search key="s" />],
  ["sec_edgar", "SEC EDGAR", "US-listed companies by industry code", "finds", <Landmark key="e" />],
  ["gleif", "GLEIF", "Global register of legal entities", "finds", <Globe key="g" />],
  ["sec_filings", "SEC filings", "A company's own filings name the product", "proves", <FileText key="f" />],
  ["case_studies", "Case studies", "Vendor customer stories name the company", "proves", <Shield key="c" />],
  ["news", "News (GDELT)", "News articles report the company using it", "proves", <News key="n" />],
];
const SEMANTICS = ["none", "company_name", "website_url", "contact_email", "phone", "address", "headquarters",
  "country", "description", "page_title", "social_links", "pricing", "founded_year", "product_categories",
  "industry", "source_url"];

// Field names become Excel columns and JSON keys, so they are kept snake_case as the user types:
// "Company Industry" -> "company_industry".
const toFieldName = (raw: string) =>
  raw.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/_+/g, "_").replace(/^[^a-z]+/, "").slice(0, 63);

// Details people tick instead of editing the table: [field name, label, type, extractor].
const DETAILS: [string, string, string, string][] = [
  ["company_name", "Company name", "string", "company_name"], ["website_url", "Website", "url", "website_url"],
  ["contact_email", "Email", "email", "contact_email"], ["phone", "Phone", "phone", "phone"],
  ["address", "Address", "string", "address"], ["headquarters", "Headquarters", "string", "headquarters"],
  ["country", "Country", "string", "country"], ["industry", "Industry", "string", "industry"],
  ["description", "Description", "text", "description"], ["founded_year", "Founding year", "integer", "founded_year"],
  ["social_links", "Social links", "list", "social_links"], ["product_categories", "Products", "list", "product_categories"],
  ["pricing", "Pricing", "string", "pricing"], ["source_url", "Source page", "url", "source_url"],
];

const DETAIL_GROUPS: { title: string; icon: ReactNode; keys: string[] }[] = [
  { title: "Identity", icon: <Building />, keys: ["company_name", "website_url"] },
  { title: "Contact", icon: <User />, keys: ["contact_email", "phone", "address"] },
  { title: "Company", icon: <Tag />, keys: ["headquarters", "country", "industry", "description", "founded_year"] },
  { title: "Online and offer", icon: <Globe />, keys: ["social_links", "product_categories", "pricing", "source_url"] },
];

export default function SchemaEditor({ spec, onChange }: { spec: Spec; onChange: (s: Spec) => void }) {
  const [open, setOpen] = useState<string | null>("details");
  const toggle = (k: string) => setOpen(open === k ? null : k);
  const [json, setJson] = useState(JSON.stringify(spec, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  useEffect(() => setJson(JSON.stringify(spec, null, 2)), [spec]);

  const setField = (i: number, patch: Partial<FieldSpec>) =>
    onChange({ ...spec, fields: spec.fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) });
  const rename = (i: number, raw: string) => {
    const old = spec.fields[i].name;
    const name = toFieldName(raw);
    onChange({ ...spec, fields: spec.fields.map((f, j) => (j === i ? { ...f, name } : f)),
      deduplication_keys: spec.deduplication_keys.map((k) => (k === old ? name : k)) });
  };
  const move = (i: number, d: -1 | 1) => {
    const fields = [...spec.fields];
    const [f] = fields.splice(i, 1);
    fields.splice(i + d, 0, f);
    onChange({ ...spec, fields });
  };
  const toggleKey = (name: string) => {
    const keys = spec.deduplication_keys.includes(name)
      ? spec.deduplication_keys.filter((k) => k !== name) : [...spec.deduplication_keys, name];
    onChange({ ...spec, deduplication_keys: keys });
  };
  const toggleDetail = ([name, , type, semantic]: [string, string, string, string]) => {
    const has = spec.fields.some((f) => f.semantic === semantic);
    if (has) {
      const gone = spec.fields.filter((f) => f.semantic === semantic).map((f) => f.name);
      if (gone.length === spec.fields.length) return; // keep at least one field
      onChange({ ...spec, fields: spec.fields.filter((f) => f.semantic !== semantic),
        deduplication_keys: spec.deduplication_keys.filter((k) => !gone.includes(k)) });
    } else {
      onChange({ ...spec, fields: [...spec.fields, { name, type, semantic }] });
    }
  };
  const crawl = (patch: Partial<Spec["crawl"]>) => onChange({ ...spec, crawl: { ...spec.crawl, ...patch } });
  const discovery = (patch: Partial<Spec["discovery"]>) =>
    onChange({ ...spec, discovery: { ...spec.discovery, ...patch } });

  const on = (semantic: string) => spec.fields.some((f) => f.semantic === semantic);
  const d = spec.discovery;
  const finds = SOURCES.filter(([k, , , kind]) => kind === "finds" && d.providers.includes(k)).length;
  const proves = SOURCES.filter(([k, , , kind]) => kind === "proves" && d.providers.includes(k)).length;

  return (
    <div className="sections">
      <Section n={1} icon={<List />} title="What each row holds" hint="The columns of your spreadsheet"
        open={open === "details"} onToggle={() => toggle("details")} done
        summary={<span>{spec.fields.length} columns: {spec.fields.slice(0, 4).map((f) => f.label || f.name).join(", ")}{spec.fields.length > 4 ? "…" : ""}</span>}>
        <div className="detail-groups">
          {DETAIL_GROUPS.map((g) => (
            <div key={g.title} className="detail-group">
              <div className="detail-group-head"><span aria-hidden>{g.icon}</span>{g.title}</div>
              <div className="chips">
                {g.keys.map((k) => { const det = DETAILS.find((x) => x[3] === k)!; return (
                  <button key={k} type="button" className="chip" aria-pressed={on(k)} onClick={() => toggleDetail(det)}>
                    {on(k) ? "✓ " : "+ "}{det[1]}</button>); })}
              </div>
            </div>
          ))}
        </div>
        <details className="more">
          <summary>Edit columns one by one <span className="muted small">names, types, required, duplicates</span></summary>
          <div className="table-wrap">
            <table className="fields">
              <thead><tr><th /><th>Name</th><th>Column label</th><th>Type</th><th>Extractor</th>
                <th className="c" title="Record is invalid without it">Required</th><th className="c" title="Used to merge duplicates">Dedupe</th><th /></tr></thead>
              <tbody>
                {spec.fields.map((f, i) => (
                  <tr key={i}>
                    <td className="nowrap">
                      <button type="button" className="icon" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">↑</button>
                      <button type="button" className="icon" disabled={i === spec.fields.length - 1} onClick={() => move(i, 1)} aria-label="Move down">↓</button>
                    </td>
                    <td><input aria-label="Field name" value={f.name} onChange={(e) => rename(i, e.target.value)}
                      title="lowercase letters, digits and _ (applied as you type)" /></td>
                    <td><input aria-label="Column label" value={f.label ?? ""} onChange={(e) => setField(i, { label: e.target.value })} /></td>
                    <td><select aria-label="Type" value={f.type} onChange={(e) => setField(i, { type: e.target.value })}>
                      {TYPES.map((t) => <option key={t}>{t}</option>)}</select></td>
                    <td><select aria-label="Extractor" value={f.semantic ?? "none"} onChange={(e) => setField(i, { semantic: e.target.value })}>
                      {SEMANTICS.map((t) => <option key={t} value={t}>{t === "none" ? "label / rules" : t}</option>)}</select></td>
                    <td className="c"><input type="checkbox" aria-label="Required" checked={!!f.required} onChange={(e) => setField(i, { required: e.target.checked })} /></td>
                    <td className="c"><input type="checkbox" aria-label="Dedupe key" checked={spec.deduplication_keys.includes(f.name)} onChange={() => toggleKey(f.name)} /></td>
                    <td><button type="button" className="icon danger" onClick={() => onChange({ ...spec, fields: spec.fields.filter((_, j) => j !== i),
                      deduplication_keys: spec.deduplication_keys.filter((k) => k !== f.name) })} aria-label="Remove field">✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="add" onClick={() => onChange({ ...spec, fields: [...spec.fields, { name: `field_${spec.fields.length + 1}`, type: "string", semantic: "none" }] })}>
            + Add a column
          </button>
        </details>
      </Section>

      <Section n={2} icon={<Filter />} title="Who qualifies" hint="Industry, a product they must use, or one company's sites"
        open={open === "who"} onToggle={() => toggle("who")} done={!!(d.industry || d.technology || d.parent_company)}
        summary={<>{d.industry && <span className="pill">{d.industry}</span>}{d.technology && <span className="pill">uses {d.technology}</span>}
          {d.parent_company && <span className="pill">sites of {d.parent_company}</span>}
          {!d.industry && !d.technology && !d.parent_company && <span className="muted">any organisation</span>}</>}>
        <div className="form-grid">
          <Field label="Industry"><input value={d.industry ?? ""} placeholder="e.g. pharmaceutical"
            onChange={(e) => discovery({ industry: e.target.value || null })} /></Field>
          <Field label="Sites of company" hint="plants, offices"><input value={d.parent_company ?? ""} placeholder="e.g. Ford"
            onChange={(e) => discovery({ parent_company: e.target.value || null })} /></Field>
        </div>
        <div className="subcard">
          <div className="subcard-head"><Cpu /> <b>Must use a product</b> <span className="field-hint">only rows with written proof are kept</span></div>
          <div className="form-grid">
            <Field label="Product or technology"><input value={d.technology ?? ""} placeholder="e.g. Teamcenter"
              onChange={(e) => discovery({ technology: e.target.value || null })} /></Field>
            <Field label="Also written as" hint="up to 8">
              <TagInput label="Also written as" values={d.technology_aliases ?? []} max={8} placeholder={d.technology ? "e.g. Siemens Teamcenter" : "set a product first"}
                onChange={(v) => discovery({ technology_aliases: v })} />
            </Field>
          </div>
        </div>
      </Section>

      <Section n={3} icon={<Globe />} title="Where" hint="Countries or a region"
        open={open === "where"} onToggle={() => toggle("where")} done={d.countries.length > 0 || !!d.region}
        summary={d.countries.length ? <>{d.countries.map((c) => <span key={c} className="pill">{c}</span>)}<span className="muted">{(d.strict_countries ?? true) ? "only" : "preferred"}</span></>
          : d.region ? <span className="pill">{d.region.replace("_", " ")}</span> : <span className="muted">anywhere</span>}>
        <Field label="Countries" hint="two-letter codes: US, GB, IN, DE">
          <TagInput label="Countries" values={d.countries} transform={(c) => c.toUpperCase()} placeholder="e.g. US, GB, IN"
            onChange={(countries) => discovery({ countries })} />
        </Field>
        <Toggle checked={d.strict_countries ?? true} disabled={!d.countries.length} onChange={(v) => discovery({ strict_countries: v })}>
          Leave out anything not confirmed to be in these countries</Toggle>
        <div className="field">
          <span className="field-label">Or a region</span>
          <div className="chips">
            {REGIONS.map(([r, label]) => (
              <button key={r} type="button" className="chip" aria-pressed={(d.region ?? "") === r} onClick={() => discovery({ region: r || null })}>{label}</button>))}
          </div>
        </div>
      </Section>

      <Section n={4} icon={<Database />} title="Sources" hint="Where websites are found, and where proof comes from"
        open={open === "sources"} onToggle={() => toggle("sources")} done={d.providers.length > 0}
        summary={<span>{finds} to find sites{proves ? ` · ${proves} to prove use` : ""}</span>}>
        {(["finds", "proves"] as const).map((kind) => (
          <div key={kind} className="field">
            <span className="field-label">{kind === "finds" ? "Find websites with" : "Prove product use with"}</span>
            <div className="source-grid">
              {SOURCES.filter((x) => x[3] === kind).map(([key, name, desc, , icon]) => {
                const active = d.providers.includes(key);
                return (
                  <button key={key} type="button" className="source-card" aria-pressed={active}
                    onClick={() => discovery({ providers: active ? d.providers.filter((p) => p !== key) : [...d.providers, key] })}>
                    <span className="source-icon" aria-hidden>{icon}</span>
                    <span className="source-text"><b>{name}</b><small>{desc}</small></span>
                    <span className="tile-check" aria-hidden />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </Section>

      <Section n={5} icon={<Gauge />} title="Limits" hint="How far the crawler goes"
        open={open === "limits"} onToggle={() => toggle("limits")} done
        summary={<span>up to {d.max_results} sites · {spec.crawl.max_pages} pages · depth {spec.crawl.max_depth}</span>}>
        <div className="form-grid">
          <Field label="Max websites"><input type="number" min={1} value={d.max_results} onChange={(e) => discovery({ max_results: +e.target.value })} /></Field>
          <Field label="Max pages"><input type="number" min={1} value={spec.crawl.max_pages} onChange={(e) => crawl({ max_pages: +e.target.value })} /></Field>
          <Field label="Pages per site"><input type="number" min={1} value={spec.crawl.max_pages_per_site} onChange={(e) => crawl({ max_pages_per_site: +e.target.value })} /></Field>
          <Field label="Link depth"><input type="number" min={0} value={spec.crawl.max_depth} onChange={(e) => crawl({ max_depth: +e.target.value })} /></Field>
          <Field label="One record per"><select value={spec.record_scope} onChange={(e) => onChange({ ...spec, record_scope: e.target.value as Spec["record_scope"] })}>
            <option value="site">website</option><option value="page">page</option></select></Field>
        </div>
        <div className="row wrap">
          <Toggle checked={spec.crawl.use_sitemaps} onChange={(v) => crawl({ use_sitemaps: v })}>Use sitemaps</Toggle>
          <Toggle checked={spec.crawl.follow_links} onChange={(v) => crawl({ follow_links: v })}>Follow links</Toggle>
        </div>
        <Field label="Start URLs" hint="one per line">
          <textarea rows={3} value={spec.crawl.start_urls.join("\n")}
            onChange={(e) => crawl({ start_urls: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })} />
        </Field>
      </Section>

      <Section icon={<Code />} title="Full plan as JSON" hint="For checking exactly what will run"
        open={open === "json"} onToggle={() => toggle("json")}>
        <textarea className="json" rows={18} spellCheck={false} value={json} onChange={(e) => {
          setJson(e.target.value);
          try { onChange(JSON.parse(e.target.value)); setJsonError(null); } catch (err) { setJsonError(String(err)); }
        }} />
        {jsonError && <p className="error small">{jsonError}</p>}
      </Section>
    </div>
  );
}
