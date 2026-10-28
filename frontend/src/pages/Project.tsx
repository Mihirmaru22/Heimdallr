import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Job, type Page, type Preview, type Project, type Schema, type Spec } from "../api";
import { ago, Badge, Card, Crumbs, ErrorBox, Spinner } from "../components/ui";
import LazyLens from "../components/LazyLens";
import { Arrow, Check, Search, Spark } from "../components/icons";
import SchemaEditor from "../components/SchemaEditor";
import SearchForm, { EMPTY_FORM, formFilled, formPayload, type SearchFormValue } from "../components/SearchForm";

const EXAMPLES = [
  "pharmaceutical companies in India with their contact email, phone and headquarters",
  "companies in the USA that use Teamcenter, with contact info and address",
  "list the manufacturing plants of Ford with plant head and contact information",
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
  const [showForm, setShowForm] = useState(false);
  const useForm = showForm && formFilled(form);
  const [urls, setUrls] = useState("");
  const [selected, setSelected] = useState<Schema | null>(null);
  const [draft, setDraft] = useState<Spec | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    if (!selected && schemas.data?.length) { setSelected(schemas.data[0]); setDraft(schemas.data[0].spec); }
  }, [schemas.data, selected]);

  const pick = (s: Schema) => { setSelected(s); setDraft(s.spec); setPreview(null); };
  const refresh = () => qc.invalidateQueries({ queryKey: ["schemas", projectId] });

  const generate = useMutation({
    mutationFn: () => api.post<Schema>(`${base}/projects/${projectId}/schemas/generate`,
      { request, start_urls: urls.split(/\s+/).filter(Boolean), form: useForm ? formPayload(form) : null }),
    onSuccess: (s) => { pick(s); refresh(); },
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
  const step = !selected ? 1 : 2;

  return (
    <div>
      <Crumbs items={[["Research", "/"], [project.data?.name ?? "Project", null]]} />
      <div className="page-head">
        <div>
          <h1>{project.data?.name ?? " "}</h1>
          {project.data?.description && <p>{project.data.description}</p>}
        </div>
      </div>
      <ol className="steps" aria-label="Progress">
        <li className={step > 1 ? "done" : "current"}>Ask a question</li>
        <li className={step === 2 ? "current" : ""}>Check the plan</li>
        <li className={ran ? "done" : ""}>Run and review</li>
      </ol>

      <Card className="ask-card">
        <div className="ask">
          <div className="ask-main">
            <div className="mode-row">
              <h2>What do you want to find?</h2>
              <div className="segmented" role="group" aria-label="How to ask">
                <button type="button" aria-pressed={!showForm} onClick={() => setShowForm(false)}>In your words</button>
                <button type="button" aria-pressed={showForm} onClick={() => setShowForm(true)}>With the form</button>
              </div>
            </div>
            <div className="ask-box">
              <label className="sr-only" htmlFor="ask">Your question</label>
              <textarea id="ask" rows={showForm ? 2 : 3} value={request} onChange={(e) => setRequest(e.target.value)}
                placeholder={showForm ? "Anything the form doesn't cover (optional)" : `Ask in your own words, e.g. "${EXAMPLES[0]}"`} />
            </div>
            {!showForm && (
              <div className="examples">
                <span>Try</span>
                {EXAMPLES.map((ex) => <button key={ex} type="button" className="chip" onClick={() => setRequest(ex)}>{ex}</button>)}
              </div>
            )}
            {showForm && (
              <div style={{ marginTop: 16 }}>
                <p className="muted small">Fill in what you know. What you type here is used exactly; the question box only fills what the form leaves empty.</p>
                <SearchForm value={form} onChange={setForm} />
              </div>
            )}
            <details className="more">
              <summary>Starting websites <span className="muted small">optional</span></summary>
              <textarea rows={2} aria-label="Starting websites, space or line separated" value={urls}
                onChange={(e) => setUrls(e.target.value)} placeholder="https://example.com  https://another.example" />
            </details>
            <div className="action-row">
              <button className="primary big" disabled={(request.trim().length < 3 && !useForm) || generate.isPending} onClick={() => generate.mutate()}>
                {generate.isPending ? <><Spinner /> Reading your question…</> : <><Spark /> Plan the research</>}</button>
              <p className="muted">A free model turns your question into a plan (or simple rules when none is available).
                Nothing runs until you check the plan and press Run.</p>
            </div>
            {generate.data?.notes?.map((n) => <p key={n} className="note warn">{n}</p>)}
            <ErrorBox error={generate.error} />
          </div>
          <LazyLens demo />
        </div>
      </Card>

      {selected && draft && (
        <Card title={<>Check the plan <span className="badge muted">v{selected.version} · {selected.status}</span></>}
              actions={schemas.data && schemas.data.length > 1 && (
                <select aria-label="Plan version" value={selected.id} onChange={(e) => pick(schemas.data!.find((s) => s.id === e.target.value)!)}>
                  {schemas.data.map((s) => <option key={s.id} value={s.id}>v{s.version} ({s.status})</option>)}
                </select>)}>
          {selected.nl_request && <div className="plan-head"><q>{selected.nl_request}</q>
            <span>read by {selected.interpreter.startsWith("model:")
              ? `free model ${selected.interpreter.slice(6)}` : selected.interpreter === "rules" ? "rules"
              : selected.interpreter === "form" ? "your search form" : "you"}</span></div>}
          <SchemaEditor spec={draft} onChange={(s) => { setDraft(s); setPreview(null); }} />
          {preview && (
            <div className="preview">
              <div className="preview-stats">
                <div><b>{preview.estimated_max_pages.toLocaleString()}</b><span>pages at most</span></div>
                <div><b>{preview.estimated_llm_calls.toLocaleString()}</b><span>free model calls at most</span></div>
                <div><b>{preview.discovery_providers.length}</b><span>sources: {preview.discovery_providers.join(", ")}</span></div>
              </div>
              {preview.warnings.map((w) => <p key={w} className="note warn">{w}</p>)}
              {preview.urls.length > 0 && (
                <div className="table-wrap"><table><thead><tr><th>Start URL</th><th>Allowed</th><th>Reason</th></tr></thead><tbody>
                  {preview.urls.map((u) => <tr key={u.url}><td className="url">{u.url}</td>
                    <td><Badge value={u.allowed ? "ready" : "blocked_policy"} /></td><td className="small">{u.reason}</td></tr>)}
                </tbody></table></div>)}
            </div>
          )}
          <ErrorBox error={save.error || check.error || run.error} />
          <div className="sticky-actions">
            <button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              {dirty && <span className="dirty-dot" aria-hidden />}{dirty ? "Save changes" : "Saved"}</button>
            <button onClick={() => check.mutate()} disabled={check.isPending}>
              {check.isPending ? <Spinner /> : <Check />} Check plan</button>
            <span className="spacer" />
            <button className="primary big" onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? <><Spinner /> Starting…</> : <><Search /> Run the research <span className="ico-go"><Arrow /></span></>}</button>
          </div>
        </Card>
      )}

      <Card title="Runs">
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
        {jobs.data?.items.length === 0 && <p className="empty">No runs yet. Plan the research above, then press Run.</p>}
      </Card>
    </div>
  );
}
