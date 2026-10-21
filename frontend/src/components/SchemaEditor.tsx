import { useEffect, useState } from "react";
import type { FieldSpec, Spec } from "../api";

const TYPES = ["string", "text", "url", "email", "phone", "number", "integer", "date", "boolean", "list"];
const DISCOVERY: [string, string][] = [["seeds", "start URLs"], ["wikidata", "Wikidata"], ["searxng", "web search (SearXNG)"], ["sec_edgar", "SEC EDGAR (US listed)"], ["gleif", "GLEIF (global register)"]];
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

const REGIONS = ["", "europe", "north_america", "asia", "africa", "south_america", "oceania"];

// Countries are typed as "US, GB, IN" and saved when the box loses focus, so commas survive typing.
function CountriesInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => setText(value.join(", ")), [value]);
  return <input value={text} placeholder="e.g. US, GB, IN" onChange={(e) => setText(e.target.value)}
    onBlur={() => onChange(text.split(/[,\s]+/).map((c) => c.trim().toUpperCase()).filter(Boolean))} />;
}

// Edits the fields table and the common crawl settings; everything else is in the JSON view.
export default function SchemaEditor({ spec, onChange }: { spec: Spec; onChange: (s: Spec) => void }) {
  const [json, setJson] = useState(JSON.stringify(spec, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
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

  return (
    <div>
      <div className="row wrap details">
        <span className="small">Details to collect:</span>
        {DETAILS.map((d) => (
          <label key={d[0]} className="check"><input type="checkbox" checked={spec.fields.some((f) => f.semantic === d[3])}
            onChange={() => toggleDetail(d)} /> {d[1]}</label>
        ))}
      </div>
      <table className="fields">
        <thead><tr><th /><th>Name</th><th>Column label</th><th>Type</th><th>Extractor</th>
          <th title="Record is invalid without it">Required</th><th title="Used to merge duplicates">Dedupe</th><th /></tr></thead>
        <tbody>
          {spec.fields.map((f, i) => (
            <tr key={i}>
              <td className="nowrap">
                <button className="icon" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">↑</button>
                <button className="icon" disabled={i === spec.fields.length - 1} onClick={() => move(i, 1)} aria-label="Move down">↓</button>
              </td>
              <td><input value={f.name} onChange={(e) => rename(i, e.target.value)}
                title="lowercase letters, digits and _ (applied as you type)" /></td>
              <td><input value={f.label ?? ""} onChange={(e) => setField(i, { label: e.target.value })} /></td>
              <td><select value={f.type} onChange={(e) => setField(i, { type: e.target.value })}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}</select></td>
              <td><select value={f.semantic ?? "none"} onChange={(e) => setField(i, { semantic: e.target.value })}>
                {SEMANTICS.map((t) => <option key={t} value={t}>{t === "none" ? "label / rules" : t}</option>)}</select></td>
              <td className="c"><input type="checkbox" checked={!!f.required} onChange={(e) => setField(i, { required: e.target.checked })} /></td>
              <td className="c"><input type="checkbox" checked={spec.deduplication_keys.includes(f.name)} onChange={() => toggleKey(f.name)} /></td>
              <td><button className="icon" onClick={() => onChange({ ...spec, fields: spec.fields.filter((_, j) => j !== i),
                deduplication_keys: spec.deduplication_keys.filter((k) => k !== f.name) })} aria-label="Remove field">✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={() => onChange({ ...spec, fields: [...spec.fields, { name: `field_${spec.fields.length + 1}`, type: "string", semantic: "none" }] })}>
        Add field
      </button>

      <div className="settings">
        <label>Start URLs (one per line)
          <textarea rows={4} value={spec.crawl.start_urls.join("\n")}
                    onChange={(e) => crawl({ start_urls: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })} />
        </label>
        <div className="row wrap">
          <label>Max pages<input type="number" min={1} value={spec.crawl.max_pages} onChange={(e) => crawl({ max_pages: +e.target.value })} /></label>
          <label>Max depth<input type="number" min={0} value={spec.crawl.max_depth} onChange={(e) => crawl({ max_depth: +e.target.value })} /></label>
          <label>Pages per site<input type="number" min={1} value={spec.crawl.max_pages_per_site} onChange={(e) => crawl({ max_pages_per_site: +e.target.value })} /></label>
          <label>One record per<select value={spec.record_scope} onChange={(e) => onChange({ ...spec, record_scope: e.target.value as Spec["record_scope"] })}>
            <option value="site">website</option><option value="page">page</option></select></label>
          <label className="check"><input type="checkbox" checked={spec.crawl.use_sitemaps} onChange={(e) => crawl({ use_sitemaps: e.target.checked })} /> Use sitemaps</label>
          <label className="check"><input type="checkbox" checked={spec.crawl.follow_links} onChange={(e) => crawl({ follow_links: e.target.checked })} /> Follow links</label>
        </div>
        <div className="row wrap">
          <span className="small">Find websites with:</span>
          {DISCOVERY.map(([key, label]) => (
            <label key={key} className="check"><input type="checkbox" checked={spec.discovery.providers.includes(key)}
              onChange={(e) => onChange({ ...spec, discovery: { ...spec.discovery, providers: e.target.checked
                ? [...spec.discovery.providers, key] : spec.discovery.providers.filter((p) => p !== key) } })} /> {label}</label>
          ))}
          <label>Industry<input value={spec.discovery.industry ?? ""} placeholder="e.g. pharmaceutical"
            onChange={(e) => onChange({ ...spec, discovery: { ...spec.discovery, industry: e.target.value || null } })} /></label>
          <label title="Two-letter codes: US, GB, IN, DE...">Countries
            <CountriesInput value={spec.discovery.countries} onChange={(countries) => discovery({ countries })} /></label>
          <label>Region<select value={spec.discovery.region ?? ""} onChange={(e) => discovery({ region: e.target.value || null })}>
            {REGIONS.map((r) => <option key={r} value={r}>{r ? r.replace("_", " ") : "any"}</option>)}</select></label>
          <label className="check" title="Leave out any company not confirmed to be in these countries">
            <input type="checkbox" checked={spec.discovery.strict_countries ?? true} disabled={!spec.discovery.countries.length}
              onChange={(e) => discovery({ strict_countries: e.target.checked })} /> Only these countries</label>
          <label title="Only companies that use this (filter arrives in the next step)">Uses technology
            <input value={spec.discovery.technology ?? ""} placeholder="e.g. Teamcenter"
              onChange={(e) => discovery({ technology: e.target.value || null })} /></label>
          <label title="For sites (plants, offices) of one company">Sites of company
            <input value={spec.discovery.parent_company ?? ""} placeholder="e.g. Ford"
              onChange={(e) => discovery({ parent_company: e.target.value || null })} /></label>
          <label>Max websites<input type="number" min={1} value={spec.discovery.max_results}
            onChange={(e) => onChange({ ...spec, discovery: { ...spec.discovery, max_results: +e.target.value } })} /></label>
        </div>
        <p className="muted small">Discovery: {spec.discovery.providers.join(", ")}
          {spec.discovery.industry && <> · industry “{spec.discovery.industry}”</>}
          {spec.discovery.technology && <> · uses “{spec.discovery.technology}”</>}
          {spec.discovery.parent_company && <> · sites of “{spec.discovery.parent_company}”</>}
          {spec.discovery.region && <> · region {spec.discovery.region}</>}
          {spec.discovery.countries.length > 0 && <> · {spec.discovery.countries.join(", ")}
            {(spec.discovery.strict_countries ?? true) ? " only" : " preferred"}</>}
          {" "}· up to {spec.discovery.max_results} sites</p>
      </div>

      <button className="link" onClick={() => setShowJson(!showJson)}>{showJson ? "Hide" : "Show"} full JSON</button>
      {showJson && (
        <div>
          <textarea className="mono" rows={18} value={json} onChange={(e) => {
            setJson(e.target.value);
            try { onChange(JSON.parse(e.target.value)); setJsonError(null); } catch (err) { setJsonError(String(err)); }
          }} />
          {jsonError && <p className="error small">{jsonError}</p>}
        </div>
      )}
    </div>
  );
}
