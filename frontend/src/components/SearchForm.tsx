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
    <div className="search-form">
      <div className="row">
        <label>Find
          <input value={value.find} placeholder="companies, pharmaceutical companies, restaurants…"
            onChange={(e) => set({ find: e.target.value })} /></label>
        <label>One row is
          <select value={value.rows} onChange={(e) => set({ rows: e.target.value as SearchFormValue["rows"] })}>
            <option value="companies">a company or organisation</option>
            <option value="sites">a site of one company (plant, office, store)</option>
            <option value="people">a person</option>
          </select></label>
        {value.rows === "sites" && (
          <label>Company
            <input value={value.parent_company} placeholder="e.g. Ford" onChange={(e) => set({ parent_company: e.target.value })} /></label>)}
      </div>
      <p className="muted small">Each row must…</p>
      {value.conditions.map((c, i) => (
        <div className="row" key={i}>
          <select value={c.kind} onChange={(e) => setCondition(i, { kind: e.target.value as ConditionKind })}>
            {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          <input value={c.value} placeholder={KINDS.find(([k]) => k === c.kind)![2]}
            onChange={(e) => setCondition(i, { value: e.target.value })} />
          <button className="link" onClick={() => set({ conditions: value.conditions.filter((_c, j) => j !== i) })}>remove</button>
        </div>
      ))}
      <button className="link" onClick={() => set({ conditions: [...value.conditions, { kind: "uses", value: "" }] })}>
        + add a condition</button>
      <div className="row">
        <label>Countries
          <input value={value.countries} placeholder="e.g. United Kingdom, IN, Germany"
            onChange={(e) => set({ countries: e.target.value })} /></label>
        <label>or region
          <select value={value.region} onChange={(e) => set({ region: e.target.value })}>
            {REGIONS.map((r) => <option key={r} value={r}>{r ? r.replace("_", " ") : "—"}</option>)}
          </select></label>
        <label>How many
          <input type="number" min={1} max={1000} value={value.max_results} placeholder="50"
            onChange={(e) => set({ max_results: e.target.value })} /></label>
      </div>
      <p className="muted small">Details for each row (name and website are always included)</p>
      <div className="row wrap">
        {DETAILS.map(([name, label]) => (
          <label key={name} className="check">
            <input type="checkbox" checked={value.details.includes(name)}
              onChange={(e) => set({ details: e.target.checked ? [...value.details, name] : value.details.filter((d) => d !== name) })} />
            {label}</label>))}
      </div>
      <label>Other details (comma separated)
        <input value={value.custom} placeholder="e.g. plant head, number of employees" onChange={(e) => set({ custom: e.target.value })} /></label>
    </div>
  );
}
