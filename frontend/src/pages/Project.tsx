import { useEffect, useRef, useState, type ReactElement } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { api, type Job, type Page, type Preview, type Project, type Schema, type Spec } from "../api";
import { ago, Badge, Card, Crumbs, ErrorBox, Spinner } from "../components/ui";
import SchemaEditor from "../components/SchemaEditor";
import SearchForm, { briefParts, EMPTY_FORM, formFilled, formPayload, type SearchFormValue } from "../components/SearchForm";
import { Arrow, Building, Check, Cpu, Link as LinkIcon, Pin, Search, Spark } from "../components/icons";

const EXAMPLES: [string, string, ReactElement][] = [
  ["Companies with contact details", "pharmaceutical companies in India with their contact email, phone and headquarters", <Building key="b" />],
  ["Users of a product, with proof", "companies in the USA that use Teamcenter, with contact info and address", <Cpu key="c" />],
  ["Sites of one company", "list the manufacturing plants of Ford with plant head and contact information", <Pin key="p" />],
];

export default function ProjectPage({ orgId }: { orgId: string }) {
  const { projectId } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const base = `/orgs/${orgId}`;
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.get<Project>(`${base}/projects/${projectId}`) });
  const schemas = useQuery({ queryKey: ["schemas", projectId], queryFn: () => api.get<Schema[]>(`${base}/projects/${projectId}/schemas`) });
  const jobs = useQuery({ queryKey: ["jobs", projectId], queryFn: () => api.get<Page<Job>>(`${base}/jobs?project_id=${projectId}`),
    refetchInterval: 5000 });

  const [request, setRequest] = useState("");
  const [form, setForm] = useState<SearchFormValue>(EMPTY_FORM);
  const useForm = formFilled(form);
  const [urls, setUrls] = useState("");
  const [selected, setSelected] = useState<Schema | null>(null);
  const [draft, setDraft] = useState<Spec | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [asking, setAsking] = useState(false);
  const planRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selected && schemas.data?.length) { setSelected(schemas.data[0]); setDraft(schemas.data[0].spec); }
  }, [schemas.data, selected]);

  const pick = (s: Schema) => { setSelected(s); setDraft(s.spec); setPreview(null); };
  const refresh = () => qc.invalidateQueries({ queryKey: ["schemas", projectId] });

  const generate = useMutation({
    mutationFn: () => api.post<Schema>(`${base}/projects/${projectId}/schemas/generate`,
      { request, start_urls: urls.split(/\s+/).filter(Boolean), form: useForm ? formPayload(form) : null }),
    onSuccess: (s) => {
      pick(s); refresh(); setAsking(false);
      setTimeout(() => planRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    },
  });
  const save = useMutation({
    mutationFn: () => api.put<Schema>(`${base}/schemas/${selected!.id}`, { spec: draft }),
    onSuccess: (s) => { pick(s); refresh(); },
  });
  const check = useMutation({
    mutationFn: async () => {
      const s = await api.put<Schema>(`${base}/schemas/${selected!.id}`, { spec: draft });
      pick(s); refresh();
      return api.get<Preview>(`${base}/schemas/${s.id}/preview`);
    },
    onSuccess: setPreview,
  });
  const run = useMutation({
    mutationFn: async () => {
      const s = await api.put<Schema>(`${base}/schemas/${selected!.id}`, { spec: draft });
      return api.post<Job>(`${base}/jobs`, { schema_id: s.id }, { "Idempotency-Key": crypto.randomUUID() });
    },
    onSuccess: (job) => navigate(`/jobs/${job.id}`),
  });
  const dirty = selected && draft && JSON.stringify(selected.spec) !== JSON.stringify(draft);
  const ran = (jobs.data?.items.length ?? 0) > 0;
  const showAsk = !selected || asking;
  const canPlan = request.trim().length >= 3 || useForm;
  const brief = briefParts(form);

  return (
    <div>
      <Crumbs items={[["Research", "/"], [project.data?.name ?? "Project", null]]} />
      <div className="page-head">
        <div>
          <h1>{project.data?.name ?? " "}</h1>
          <p>{selected ? "Check the plan, then run it. You can change the question at any time." : "Describe what you want; the more you fill in, the tighter the plan."}</p>
        </div>
      </div>
      <ol className="stepper" aria-label="Progress">
        <li className={selected ? "done" : "current"}><span>1</span> Ask</li>
        <li className={selected ? (ran ? "done" : "current") : ""}><span>2</span> Check the plan</li>
        <li className={ran ? "done" : ""}><span>3</span> Run and review</li>
      </ol>

      <div className="builder">
        <div className="builder-main">
          <AnimatePresence initial={false} mode="popLayout">
            {showAsk ? (
              <motion.div key="ask" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
                <section className="panel question-panel">
                  <div className="panel-head">
                    <span className="panel-kicker">Your question</span>
                    {selected && <button type="button" className="link" onClick={() => setAsking(false)}>Back to the plan</button>}
                  </div>
                  <label className="sr-only" htmlFor="ask">Your question</label>
                  <textarea id="ask" className="question-box" rows={3} value={request} onChange={(e) => setRequest(e.target.value)}
                    placeholder="Ask in your own words. For example: insurance companies in Germany that use Guidewire, with phone and headquarters" />
                  <div className="example-grid">
                    {EXAMPLES.map(([title, text, icon]) => (
                      <button key={title} type="button" className="example" onClick={() => setRequest(text)}>
                        <span className="example-icon" aria-hidden>{icon}</span>
                        <span><b>{title}</b><small>{text}</small></span>
                      </button>
                    ))}
                  </div>
                </section>

                <div className="divider"><span>and, or instead, build it part by part</span></div>
                <p className="muted small builder-note">Parts you fill in here are used exactly as typed. The question above fills whatever you leave empty.</p>
                <SearchForm value={form} onChange={setForm} />

                <section className="panel slim">
                  <div className="panel-head">
                    <span className="panel-kicker"><LinkIcon size={14} /> Starting websites</span><span className="field-hint">optional</span>
                  </div>
                  <textarea rows={2} aria-label="Starting websites, space or line separated" value={urls}
                    onChange={(e) => setUrls(e.target.value)} placeholder="https://example.com  https://another.example" />
                </section>
                {generate.data?.notes?.map((n) => <p key={n} className="note warn">{n}</p>)}
                <ErrorBox error={generate.error} />
              </motion.div>
            ) : (
              <motion.div key="asked" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}>
                <section className="panel asked">
                  <div>
                    <span className="panel-kicker">Your question</span>
                    <p className="asked-q">“{selected!.nl_request || "Plan edited by hand"}”</p>
                    <span className="muted small">Read by {selected!.interpreter.startsWith("model:")
                      ? `free model ${selected!.interpreter.slice(6)}` : selected!.interpreter === "rules" ? "rules"
                      : selected!.interpreter === "form" ? "your search form" : "you"}</span>
                  </div>
                  <button type="button" onClick={() => setAsking(true)}>Change the question</button>
                </section>
              </motion.div>
            )}
          </AnimatePresence>

          {selected && draft && !asking && (
            <div ref={planRef} className="plan-block">
              <div className="plan-title">
                <h2>Check the plan</h2>
                <span className="badge muted">v{selected.version} · {selected.status}</span>
                {schemas.data && schemas.data.length > 1 && (
                  <select aria-label="Plan version" value={selected.id} onChange={(e) => pick(schemas.data!.find((s) => s.id === e.target.value)!)}>
                    {schemas.data.map((s) => <option key={s.id} value={s.id}>v{s.version} ({s.status})</option>)}
                  </select>)}
              </div>
              <SchemaEditor spec={draft} onChange={(s) => { setDraft(s); setPreview(null); }} />
            </div>
          )}

          <Card title="Runs" className="runs-card">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Started</th><th>State</th><th className="num">Pages fetched</th><th className="num">Records</th><th>Error</th></tr></thead>
                <tbody>{jobs.data?.items.map((j) => (
                  <tr key={j.id} className="clickable" onClick={() => navigate(`/jobs/${j.id}`)}>
                    <td><Link to={`/jobs/${j.id}`} onClick={(e) => e.stopPropagation()}>{ago(j.created_at)}</Link></td>
                    <td><Badge value={j.state} /></td>
                    <td className="num mono">{j.counters.fetched ?? 0}</td><td className="num mono">{j.counters.extracted ?? 0}</td>
                    <td className="small error">{j.error}</td></tr>))}
                </tbody>
              </table>
            </div>
            {jobs.data?.items.length === 0 && <p className="empty">No runs yet. Plan the research, then press Run.</p>}
          </Card>
        </div>

        <aside className="rail">
          {showAsk ? (
            <section className="panel brief">
              <span className="panel-kicker">Research brief</span>
              {request.trim() && <p className="brief-q">“{request.trim()}”</p>}
              <ul className="brief-list">
                {brief.map((b) => (
                  <li key={b.key} className={b.value ? "set" : ""}>
                    <span className="brief-label">{b.label}</span>
                    <span className="brief-value">{b.value ?? (request.trim() ? "from your question" : "not set")}</span>
                  </li>
                ))}
              </ul>
              <button className="primary big wide" disabled={!canPlan || generate.isPending} onClick={() => generate.mutate()}>
                {generate.isPending ? <><Spinner /> Reading your question…</> : <><Spark /> Plan the research</>}</button>
              <p className="muted small">A free model turns this into a plan. Nothing runs until you check it and press Run.</p>
            </section>
          ) : draft && selected ? (
            <section className="panel brief">
              <span className="panel-kicker">Ready to run</span>
              <ul className="brief-list">
                <li className="set"><span className="brief-label">Columns</span><span className="brief-value">{draft.fields.length}</span></li>
                <li className="set"><span className="brief-label">Sources</span><span className="brief-value">{draft.discovery.providers.join(", ") || "none"}</span></li>
                <li className={draft.discovery.countries.length || draft.discovery.region ? "set" : ""}><span className="brief-label">Where</span>
                  <span className="brief-value">{draft.discovery.countries.join(", ") || draft.discovery.region?.replace("_", " ") || "anywhere"}</span></li>
                {draft.discovery.technology && <li className="set"><span className="brief-label">Must use</span><span className="brief-value">{draft.discovery.technology}</span></li>}
                <li className="set"><span className="brief-label">Up to</span><span className="brief-value">{draft.discovery.max_results} sites · {draft.crawl.max_pages} pages</span></li>
              </ul>
              {preview && (
                <motion.div className="preview" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="preview-stats">
                    <div><b>{preview.estimated_max_pages.toLocaleString()}</b><span>pages at most</span></div>
                    <div><b>{preview.estimated_llm_calls.toLocaleString()}</b><span>free model calls at most</span></div>
                  </div>
                  {preview.warnings.map((w) => <p key={w} className="note warn">{w}</p>)}
                  {preview.urls.filter((u) => !u.allowed).map((u) => <p key={u.url} className="note warn">{u.url}: {u.reason}</p>)}
                </motion.div>
              )}
              <ErrorBox error={save.error || check.error || run.error} />
              <button className="primary big wide" onClick={() => run.mutate()} disabled={run.isPending}>
                {run.isPending ? <><Spinner /> Starting…</> : <><Search /> Run the research <span className="ico-go"><Arrow /></span></>}</button>
              <div className="rail-row">
                <button onClick={() => check.mutate()} disabled={check.isPending}>{check.isPending ? <Spinner /> : <Check />} Check plan</button>
                <button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                  {dirty && <span className="dirty-dot" aria-hidden />}{dirty ? "Save changes" : "Saved"}</button>
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
