import { useState } from "react";
import { motion } from "motion/react";
import { DetailGroups, Field, Section, TagInput, Tiles } from "./form";
import { Building, Filter, Globe, List, Pin, Plus, Search, Tag, User, X } from "./icons";

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

const KINDS: [ConditionKind, string, string, string][] = [
  ["uses", "Uses", "a product or technology", "e.g. Guidewire, SAP S/4HANA"],
  ["offers", "Sells or offers", "a product or service", "e.g. pizza, cloud hosting"],
  ["has_role", "Has a role", "a job title on staff", "e.g. plant head, CISO"],
  ["other", "Other must-have", "anything else that must be true", "e.g. family owned, ISO 13485 certified"],
];
export const DETAIL_GROUPS: { title: string; items: [string, string][] }[] = [
  { title: "Contact", items: [["contact_email", "Email"], ["phone", "Phone"], ["address", "Address"]] },
  { title: "Company", items: [["headquarters", "Headquarters"], ["country", "Country"], ["industry", "Industry"],
    ["description", "Description"], ["founded_year", "Founding year"]] },
  { title: "Online and offer", items: [["social_links", "Social links"], ["product_categories", "Products"], ["pricing", "Pricing"],
    ["source_url", "Source page"]] },
];
const DETAIL_LABEL = Object.fromEntries(DETAIL_GROUPS.flatMap((g) => g.items));
export const REGIONS: [string, string][] = [["", "Anywhere"], ["europe", "Europe"], ["north_america", "North America"],
  ["asia", "Asia"], ["africa", "Africa"], ["south_america", "South America"], ["oceania", "Oceania"]];
const ROWS: Record<SearchFormValue["rows"], string> = { companies: "company", sites: "site of one company", people: "person" };
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

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

// The search as a plain-words brief, part by part, for the side panel.
export function briefParts(f: SearchFormValue): { key: string; label: string; value: string | null }[] {
  const conds = f.conditions.filter((c) => c.value.trim())
    .map((c) => `${KINDS.find(([k]) => k === c.kind)![1].toLowerCase()} ${c.value.trim()}`);
  const where = split(f.countries).join(", ") || REGIONS.find(([r]) => r === f.region)?.[1] || "";
  return [
    { key: "find", label: "Find", value: f.find.trim() || null },
    { key: "rows", label: "One row per", value: ROWS[f.rows] + (f.rows === "sites" && f.parent_company.trim() ? ` of ${f.parent_company.trim()}` : "") },
    { key: "must", label: "Each must", value: conds.join(" and ") || null },
    { key: "where", label: "In", value: where && where !== "Anywhere" ? where : null },
    { key: "count", label: "Up to", value: `${f.max_results || 50} rows` },
    { key: "details", label: "With", value: ["name", "website", ...f.details.map((d) => DETAIL_LABEL[d]?.toLowerCase() ?? d), ...split(f.custom)].join(", ") },
  ];
}

export default function SearchForm({ value, onChange }: { value: SearchFormValue; onChange: (v: SearchFormValue) => void }) {
  const [open, setOpen] = useState<string | null>("who");
  const toggle = (k: string) => setOpen(open === k ? null : k);
  const set = (patch: Partial<SearchFormValue>) => onChange({ ...value, ...patch });
  const setCondition = (i: number, patch: Partial<Condition>) =>
    set({ conditions: value.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const conds = value.conditions.filter((c) => c.value.trim());
  const countries = split(value.countries);
  const custom = split(value.custom);
  const regionLabel = REGIONS.find(([r]) => r === value.region)?.[1];

  return (
    <div className="sections">
      <Section n={1} icon={<Search />} title="Who are you looking for?" hint="What kind of organisation, and what one row is"
        open={open === "who"} onToggle={() => toggle("who")} done={!!value.find.trim()}
        summary={value.find.trim() ? <><b>{value.find.trim()}</b> · one row per {ROWS[value.rows]}</> : <span className="muted">not set</span>}>
        <Field label="Find" hint="the kind of organisation">
          <input value={value.find} placeholder="e.g. insurance companies, pharmaceutical companies, restaurants"
            onChange={(e) => set({ find: e.target.value })} />
        </Field>
        <div className="field">
          <span className="field-label">One row in the sheet is</span>
          <Tiles label="One row is" value={value.rows} onChange={(rows) => set({ rows })} options={[
            { value: "companies", label: "A company", hint: "or any organisation", icon: <Building /> },
            { value: "sites", label: "A site of one company", hint: "plant, office, store", icon: <Pin /> },
            { value: "people", label: "A person", hint: "someone in a role", icon: <User /> },
          ]} />
        </div>
        {value.rows === "sites" && (
          <Field label="Which company's sites?">
            <input value={value.parent_company} placeholder="e.g. Ford" onChange={(e) => set({ parent_company: e.target.value })} />
          </Field>
        )}
      </Section>

      <Section n={2} icon={<Filter />} title="What must be true of each row?" hint="Optional conditions, each needs proof"
        open={open === "must"} onToggle={() => toggle("must")} done={conds.length > 0}
        summary={conds.length ? conds.map((c, i) => <span key={i} className="pill">{KINDS.find(([k]) => k === c.kind)![1]} {c.value}</span>)
          : <span className="muted">no conditions</span>}>
        {value.conditions.length === 0 && <p className="muted small">No conditions yet. Add one when every row has to meet a rule, such as using a product.</p>}
        <div className="conditions">
          {value.conditions.map((c, i) => (
            <motion.div className="condition-card" key={i} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <div className="condition-top">
                <span className="mono muted">#{i + 1}</span>
                <div className="segmented" role="radiogroup" aria-label={`Condition ${i + 1} kind`}>
                  {KINDS.map(([k, label]) => (
                    <button key={k} type="button" role="radio" aria-checked={c.kind === k} aria-pressed={c.kind === k}
                      onClick={() => setCondition(i, { kind: k })}>{label}</button>))}
                </div>
                <button type="button" className="icon danger" aria-label={`Remove condition ${i + 1}`}
                  onClick={() => set({ conditions: value.conditions.filter((_c, j) => j !== i) })}><X /></button>
              </div>
              <input aria-label={`Condition ${i + 1}`} value={c.value} placeholder={KINDS.find(([k]) => k === c.kind)![3]}
                onChange={(e) => setCondition(i, { value: e.target.value })} />
              <span className="field-hint">{KINDS.find(([k]) => k === c.kind)![2]}</span>
            </motion.div>
          ))}
        </div>
        <button type="button" className="add" onClick={() => set({ conditions: [...value.conditions, { kind: "uses", value: "" }] })}>
          <Plus /> {value.conditions.length ? "Add another condition" : "Add a condition"}</button>
      </Section>

      <Section n={3} icon={<Globe />} title="Where?" hint="Countries, or a whole region"
        open={open === "where"} onToggle={() => toggle("where")} done={countries.length > 0 || !!value.region}
        summary={countries.length ? countries.map((c) => <span key={c} className="pill">{c}</span>)
          : value.region ? <span className="pill">{regionLabel}</span> : <span className="muted">anywhere</span>}>
        <Field label="Countries" hint="type a name or a two-letter code, press Enter">
          <TagInput label="Countries" values={countries} placeholder="e.g. United Kingdom, IN, Germany"
            onChange={(v) => set({ countries: v.join(", ") })} />
        </Field>
        <div className="field">
          <span className="field-label">Or a region {countries.length > 0 && <span className="field-hint">· countries win when both are set</span>}</span>
          <div className="chips">
            {REGIONS.map(([r, label]) => (
              <button key={r} type="button" className="chip" aria-pressed={value.region === r} onClick={() => set({ region: r })}>{label}</button>))}
          </div>
        </div>
      </Section>

      <Section n={4} icon={<List />} title="What should each row tell you?" hint="Name and website are always included"
        open={open === "details"} onToggle={() => toggle("details")} done={value.details.length + custom.length > 0}
        summary={<span>{value.details.length + custom.length ? `${value.details.length + custom.length} details` : "name and website"} · up to {value.max_results || 50} rows</span>}>
        <DetailGroups groups={DETAIL_GROUPS.map((g, i) => ({ ...g, icon: [<User key="u" />, <Building key="b" />, <Tag key="t" />][i] }))}
          isOn={(k) => value.details.includes(k)}
          toggle={(k) => set({ details: value.details.includes(k) ? value.details.filter((d) => d !== k) : [...value.details, k] })} />
        <Field label="Anything else" hint="your own columns, up to 8">
          <TagInput label="Other details" values={custom} max={8} placeholder="e.g. plant head, number of employees"
            onChange={(v) => set({ custom: v.join(", ") })} />
        </Field>
        <div className="field">
          <span className="field-label">How many rows</span>
          <div className="count-row">
            {["25", "50", "100", "250"].map((n) => (
              <button key={n} type="button" className="chip" aria-pressed={(value.max_results || "50") === n}
                onClick={() => set({ max_results: n })}>{n}</button>))}
            <input type="number" min={1} max={1000} aria-label="Exact number of rows" value={value.max_results} placeholder="50"
              onChange={(e) => set({ max_results: e.target.value })} />
          </div>
        </div>
      </Section>
    </div>
  );
}
