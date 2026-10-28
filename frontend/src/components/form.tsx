import { useState, type KeyboardEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Chevron, X } from "./icons";

// Building blocks for the question builder and the plan review: bordered sections that open one at a time,
// tile pickers, and a tag input.

export function Section({ n, icon, title, hint, summary, open, onToggle, done, children }: {
  n?: number; icon: ReactNode; title: string; hint?: string; summary?: ReactNode; open: boolean; onToggle: () => void;
  done?: boolean; children: ReactNode;
}) {
  return (
    <section className={`sect ${open ? "is-open" : ""} ${done ? "is-done" : ""}`}>
      <button type="button" className="sect-head" aria-expanded={open} onClick={onToggle}>
        {n != null && <span className="sect-num mono" aria-hidden>{done ? "✓" : String(n).padStart(2, "0")}</span>}
        <span className="sect-icon" aria-hidden>{icon}</span>
        <span className="sect-titles"><b>{title}</b>{hint && <small>{hint}</small>}</span>
        {!open && summary && <span className="sect-summary">{summary}</span>}
        <span className="sect-chev" aria-hidden><Chevron /></span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="sect-body-wrap" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.32, ease: [0.2, 0.75, 0.15, 1] }}>
            <div className="sect-body">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

export function Tiles<T extends string>({ value, options, onChange, label, size = "md" }: {
  value: T; options: { value: T; label: string; hint?: string; icon?: ReactNode }[]; onChange: (v: T) => void; label: string;
  size?: "sm" | "md";
}) {
  return (
    <div className={`tiles tiles-${size}`} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} className="tile" onClick={() => onChange(o.value)}>
          {o.icon && <span className="tile-icon" aria-hidden>{o.icon}</span>}
          <span className="tile-text"><b>{o.label}</b>{o.hint && <small>{o.hint}</small>}</span>
          <span className="tile-check" aria-hidden />
        </button>
      ))}
    </div>
  );
}

// Typed values become removable tags on Enter, comma or Tab; Backspace on an empty box removes the last one.
export function TagInput({ values, onChange, placeholder, label, transform = (s) => s, max = 50 }: {
  values: string[]; onChange: (v: string[]) => void; placeholder?: string; label: string;
  transform?: (s: string) => string; max?: number;
}) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const parts = raw.split(",").map((s) => transform(s.trim())).filter(Boolean);
    if (!parts.length) return;
    onChange([...values, ...parts.filter((p) => !values.includes(p))].slice(0, max));
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === "Enter" || e.key === "," || (e.key === "Tab" && text.trim())) && text.trim()) { e.preventDefault(); add(text); }
    else if (e.key === "Backspace" && !text && values.length) onChange(values.slice(0, -1));
  };
  return (
    <div className="tag-input" onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus()}>
      {values.map((v) => (
        <span key={v} className="tag">{v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}><X size={12} /></button>
        </span>
      ))}
      <input aria-label={label} value={text} placeholder={values.length ? "" : placeholder}
        onChange={(e) => (e.target.value.includes(",") ? add(e.target.value) : setText(e.target.value))}
        onKeyDown={onKey} onBlur={() => add(text)} />
    </div>
  );
}

export function Field({ label, hint, children, wide }: { label: string; hint?: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span className="field-label">{label}{hint && <span className="field-hint"> · {hint}</span>}</span>
      {children}
    </label>
  );
}

export function Toggle({ checked, onChange, children, disabled }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; disabled?: boolean }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track" aria-hidden /> {children}
    </label>
  );
}

// Grouped on/off chips for "details to collect".
export function DetailGroups({ groups, isOn, toggle }: {
  groups: { title: string; icon: ReactNode; items: [string, string][] }[]; isOn: (k: string) => boolean; toggle: (k: string) => void;
}) {
  return (
    <div className="detail-groups">
      {groups.map((g) => (
        <div key={g.title} className="detail-group">
          <div className="detail-group-head"><span aria-hidden>{g.icon}</span>{g.title}</div>
          <div className="chips">
            {g.items.map(([k, label]) => (
              <button key={k} type="button" className="chip" aria-pressed={isOn(k)} onClick={() => toggle(k)}>
                {isOn(k) ? "✓ " : "+ "}{label}</button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
