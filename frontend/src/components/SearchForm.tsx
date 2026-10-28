// The search as a form: every part optional and general ("restaurants" that offer "pizza" in Italy, "companies"
// with the role "plant head", "insurance companies" that use "Guidewire"). What is filled in becomes the plan
// as typed; the question box above, when also filled, only fills what the form leaves empty.

export type ConditionKind = "uses" | "offers" | "has_role" | "other";
export interface Condition { kind: ConditionKind; value: string }
export interface SearchFormValue {
  find: string; rows: "companies" | "sites" | "people"; conditions: Condition[]; countries: string;
  region: string; parent_company: string; max_results: string; details: string[]; custom: string;
}

export const EMPTY_FORM: SearchFormValue = {
  find: "", rows: "companies", conditions: [], countries: "", region: "", parent_company: "", max_results: "",
  details: [], custom: "",
};

const KINDS: [ConditionKind, string, string][] = [
  ["uses", "uses (a product or technology)", "e.g. Guidewire, SAP S/4HANA"],
  ["offers", "sells or offers", "e.g. pizza, cloud hosting"],
  ["has_role", "has this role or job", "e.g. plant head, CISO"],
  ["other", "other must-have", "e.g. family owned, ISO 13485 certified"],
];
const DETAILS: [string, string][] = [
  ["contact_email", "Email"], ["phone", "Phone"], ["address", "Address"], ["headquarters", "Headquarters"],
  ["country", "Country"], ["industry", "Industry"], ["description", "Description"],
  ["founded_year", "Founding year"], ["social_links", "Social links"], ["product_categories", "Products"],
  ["pricing", "Pricing"], ["source_url", "Source page"],
];
const REGIONS = ["", "europe", "north_america", "asia", "africa", "south_america", "oceania"];

export function formFilled(f: SearchFormValue): boolean {
  return Boolean(f.find.trim() || f.conditions.some((c) => c.value.trim()) || f.countries.trim() || f.region
    || f.parent_company.trim());
}

// The form as the API takes it (empty parts left out).
export function formPayload(f: SearchFormValue): Record<string, unknown> {
  return {
    find: f.find.trim(), rows: f.rows,
    conditions: f.conditions.filter((c) => c.value.trim()).map((c) => ({ kind: c.kind, value: c.value.trim() })),
    countries: f.countries.split(",").map((s) => s.trim()).filter(Boolean), region: f.region || null, parent_company: f.parent_company.trim() || null,
    max_results: f.max_results ? Number(f.max_results) : null, details: f.details,
    custom_details: f.custom.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 8).map((label) => ({ label })),
  };
}

export default function SearchForm({ value, onChange }: { value: SearchFormValue; onChange: (v: SearchFormValue) => void }) {
  const set = (patch: Partial<SearchFormValue>) => onChange({ ...value, ...patch });
  const setCondition = (i: number, patch: Partial<Condition>) =>
    set({ conditions: value.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  return (
    <div className="search-form stack">
      <div className="sentence">
        <div className="clause">
          <span className="clause-word" id="sf-find">Find</span>
          <div className="clause-body">
            <input aria-labelledby="sf-find" value={value.find} placeholder="companies, pharmaceutical companies, restaurants…"
              onChange={(e) => set({ find: e.target.value })} />
          </div>
        </div>
        <div className="clause">
          <span className="clause-word" id="sf-rows">One row is</span>
          <div className="clause-body">
            <select aria-labelledby="sf-rows" value={value.rows} onChange={(e) => set({ rows: e.target.value as SearchFormValue["rows"] })}>
              <option value="companies">a company or organisation</option>
              <option value="sites">a site of one company (plant, office, store)</option>
              <option value="people">a person</option>
            </select>
            {value.rows === "sites" && (
              <input aria-label="Company whose sites to list" value={value.parent_company} placeholder="of which company? e.g. Ford"
                onChange={(e) => set({ parent_company: e.target.value })} />)}
          </div>
        </div>
        <div className="clause">
          <span className="clause-word">Each row must</span>
          <div className="clause-body">
            {value.conditions.map((c, i) => (
              <div className="condition" key={i}>
                <select aria-label={`Condition ${i + 1} kind`} value={c.kind} onChange={(e) => setCondition(i, { kind: e.target.value as ConditionKind })}>
                  {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                </select>
                <input aria-label={`Condition ${i + 1}`} value={c.value} placeholder={KINDS.find(([k]) => k === c.kind)![2]}
                  onChange={(e) => setCondition(i, { value: e.target.value })} />
                <button type="button" className="icon" aria-label={`Remove condition ${i + 1}`}
                  onClick={() => set({ conditions: value.conditions.filter((_c, j) => j !== i) })}>✕</button>
              </div>
            ))}
            <button type="button" className="add" onClick={() => set({ conditions: [...value.conditions, { kind: "uses", value: "" }] })}>
              + {value.conditions.length ? "another condition" : "add a condition"}</button>
          </div>
        </div>
        <div className="clause">
          <span className="clause-word" id="sf-where">In</span>
          <div className="clause-body">
            <input aria-labelledby="sf-where" value={value.countries} placeholder="countries, e.g. United Kingdom, IN, Germany"
              onChange={(e) => set({ countries: e.target.value })} />
            <select aria-label="or a region" value={value.region} onChange={(e) => set({ region: e.target.value })}>
              {REGIONS.map((r) => <option key={r} value={r}>{r ? r.replace("_", " ") : "or a region…"}</option>)}
            </select>
          </div>
        </div>
        <div className="clause">
          <span className="clause-word" id="sf-many">Up to</span>
          <div className="clause-body">
            <input className="narrow" aria-labelledby="sf-many" type="number" min={1} max={1000} value={value.max_results} placeholder="50"
              onChange={(e) => set({ max_results: e.target.value })} />
            <span className="muted small">rows</span>
          </div>
        </div>
      </div>
      <div>
        <p className="section-label">Details for each row <span className="field-hint">name and website are always included</span></p>
        <div className="chips">
          {DETAILS.map(([name, label]) => (
            <label key={name} className="chip">
              <input type="checkbox" checked={value.details.includes(name)}
                onChange={(e) => set({ details: e.target.checked ? [...value.details, name] : value.details.filter((d) => d !== name) })} />
              {label}</label>))}
        </div>
      </div>
      <label>Other details <span className="field-hint">comma separated, up to 8</span>
        <input value={value.custom} placeholder="e.g. plant head, number of employees" onChange={(e) => set({ custom: e.target.value })} /></label>
    </div>
  );
}
