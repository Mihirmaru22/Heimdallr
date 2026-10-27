import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Job, type Page, type Preview, type Project, type Schema, type Spec } from "../api";
import { Badge, Card, ErrorBox, when } from "../components/ui";
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

  return (
    <div>
      <p><Link to="/">Projects</Link> / <strong>{project.data?.name}</strong></p>
      <Card title="1. Describe what you need">
        <textarea rows={3} placeholder={`Ask in your own words, e.g. "${EXAMPLES[0]}"`} value={request}
          onChange={(e) => setRequest(e.target.value)} />
        <button className="link" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Hide the search form" : "Or fill in a search form (what to find, conditions, where, details)"}</button>
        {showForm && <SearchForm value={form} onChange={setForm} />}
        <label>Starting websites (optional, space or line separated)
          <textarea rows={2} value={urls} onChange={(e) => setUrls(e.target.value)} placeholder="https://example.com" /></label>
        <div className="row">
          <button className="primary" disabled={(request.trim().length < 3 && !useForm) || generate.isPending} onClick={() => generate.mutate()}>
            {generate.isPending ? "Reading your question…" : "Plan the research"}</button>
          {EXAMPLES.map((ex, i) => <button key={ex} className="link" onClick={() => setRequest(ex)}>Example {i + 1}</button>)}
        </div>
        <p className="muted small">A free AI model reads your question into a plan (or simple rules, when no free model is
          available); a filled-in form is used as the plan exactly as you typed it. Nothing runs until you check the plan
          below and press Run.</p>
        {generate.data?.notes?.map((n) => <p key={n} className="warn small">{n}</p>)}
        <ErrorBox error={generate.error} />
      </Card>

      {selected && draft && (
        <Card title={<>2. Review the schema <span className="muted small">v{selected.version} · {selected.status}</span></>}
              actions={schemas.data && schemas.data.length > 1 && (
                <select value={selected.id} onChange={(e) => pick(schemas.data!.find((s) => s.id === e.target.value)!)}>
                  {schemas.data.map((s) => <option key={s.id} value={s.id}>v{s.version} ({s.status})</option>)}
                </select>)}>
          {selected.nl_request && <p className="muted">“{selected.nl_request}” · read by {selected.interpreter.startsWith("model:")
            ? `free model ${selected.interpreter.slice(6)}` : selected.interpreter === "rules" ? "rules"
            : selected.interpreter === "form" ? "your search form" : "you"}</p>}
          <SchemaEditor spec={draft} onChange={(s) => { setDraft(s); setPreview(null); }} />
          <ErrorBox error={save.error || check.error || run.error} />
          <div className="row">
            <button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Save</button>
            <button onClick={() => check.mutate()} disabled={check.isPending}>Check plan</button>
            <button className="primary" onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? "Starting…" : "3. Run crawl"}</button>
          </div>
          {preview && (
            <div className="preview">
              <p>Up to <strong>{preview.estimated_max_pages}</strong> pages · discovery: {preview.discovery_providers.join(", ")} ·
                AI calls (at most, free models): <strong>{preview.estimated_llm_calls}</strong></p>
              {preview.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
              {preview.urls.length > 0 && (
                <table><thead><tr><th>Start URL</th><th>Allowed</th><th>Reason</th></tr></thead><tbody>
                  {preview.urls.map((u) => <tr key={u.url}><td className="url">{u.url}</td>
                    <td>{u.allowed ? "yes" : "no"}</td><td className="small">{u.reason}</td></tr>)}
                </tbody></table>)}
            </div>
          )}
        </Card>
      )}

      <Card title="Jobs">
        <table>
          <thead><tr><th>Started</th><th>State</th><th>Pages fetched</th><th>Records</th><th>Error</th></tr></thead>
          <tbody>{jobs.data?.items.map((j) => (
            <tr key={j.id}><td><Link to={`/jobs/${j.id}`}>{when(j.created_at)}</Link></td><td><Badge value={j.state} /></td>
              <td>{j.counters.fetched ?? 0}</td><td>{j.counters.extracted ?? 0}</td><td className="small">{j.error}</td></tr>))}
          </tbody>
        </table>
        {jobs.data?.items.length === 0 && <p className="muted">No jobs yet.</p>}
      </Card>
    </div>
  );
}
