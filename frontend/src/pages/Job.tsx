import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, display, type CrawlUrl, type ExportRow, type Job, type JobEvent, type Page, type Progress,
  type RecordRow, type Schema } from "../api";
import { Badge, Card, ErrorBox, Pager, when } from "../components/ui";
import RecordDrawer from "../components/RecordDrawer";
import ActivityFeed from "../components/ActivityFeed";

const URL_STATUSES = ["", "queued", "fetched", "skipped", "blocked_robots", "blocked_policy", "failed", "dead"];

export default function JobPage({ orgId }: { orgId: string }) {
  const { jobId } = useParams();
  const base = `/orgs/${orgId}`;
  const qc = useQueryClient();
  const [tab, setTab] = useState<"activity" | "records" | "urls" | "events">("activity");

  const progress = useQuery({
    queryKey: ["progress", jobId], queryFn: () => api.get<Progress>(`${base}/jobs/${jobId}/progress`),
    refetchInterval: (q) => (q.state.data?.terminal ? false : 2000),
  });
  const job = useQuery({ queryKey: ["job", jobId, progress.data?.state], queryFn: () => api.get<Job>(`${base}/jobs/${jobId}`) });
  const schema = useQuery({ queryKey: ["schema", job.data?.schema_id], enabled: !!job.data,
    queryFn: () => api.get<Schema>(`${base}/schemas/${job.data!.schema_id}`) });
  const terminal = progress.data?.terminal ?? false;

  const cancel = useMutation({ mutationFn: () => api.post(`${base}/jobs/${jobId}/cancel`), onSuccess: () => qc.invalidateQueries() });
  const retry = useMutation({ mutationFn: () => api.post(`${base}/jobs/${jobId}/retry`), onSuccess: () => qc.invalidateQueries() });
  const c = progress.data?.counters ?? {};

  return (
    <div>
      <p><Link to="/">Projects</Link> / {job.data && <Link to={`/projects/${job.data.project_id}`}>Project</Link>} / Job</p>
      <Card title={<>Job <Badge value={progress.data?.state ?? "…"} /></>} actions={<>
        {!terminal && <button onClick={() => cancel.mutate()} disabled={cancel.isPending || progress.data?.state === "cancel_requested"}>Cancel</button>}
        {(progress.data?.state === "failed" || progress.data?.state === "cancelled") &&
          <button onClick={() => retry.mutate()} disabled={retry.isPending}>Retry</button>}
      </>}>
        <div className="stats">
          <Stat label="Discovered" value={c.discovered} /><Stat label="Fetched" value={c.fetched} />
          <Stat label="Queued" value={c.queued} /><Stat label="Skipped" value={c.skipped} />
          <Stat label="Blocked" value={c.blocked} /><Stat label="Failed" value={c.failed} />
          <Stat label="Records" value={progress.data?.records} /><Stat label="Complete records" value={progress.data?.valid_records} />
          <Stat label="Duplicates merged" value={c.records_duplicates} />
          <Stat label="Elapsed" value={progress.data?.elapsed_seconds != null ? `${Math.round(progress.data.elapsed_seconds)}s` : "–"} />
        </div>
        {progress.data?.error && <p className="error">{progress.data.error}</p>}
        <ErrorBox error={cancel.error || retry.error} />
      </Card>

      <div className="tabs">
        {(["activity", "records", "urls", "events"] as const).map((t) =>
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t === "urls" ? "Pages" : t[0].toUpperCase() + t.slice(1)}</button>)}
      </div>
      {tab === "activity" && <ActivityFeed base={base} jobId={jobId!} live={!terminal} />}
      {tab === "records" && schema.data && <Records base={base} jobId={jobId!} schema={schema.data} terminal={terminal} />}
      {tab === "urls" && <Urls base={base} jobId={jobId!} />}
      {tab === "events" && <Events base={base} jobId={jobId!} live={!terminal} />}
      {terminal && job.data && <Exports base={base} jobId={jobId!} state={job.data.state} />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string | undefined }) {
  return <div className="stat"><div className="v">{value ?? 0}</div><div className="l">{label}</div></div>;
}

function Records({ base, jobId, schema, terminal }: { base: string; jobId: string; schema: Schema; terminal: boolean }) {
  const [status, setStatus] = useState("");
  const [excluded, setExcluded] = useState<"" | "true" | "false">("false");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("quality");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const limit = 50;
  const params = new URLSearchParams({ sort, limit: String(limit), offset: String(offset) });
  if (status) params.append("status", status);
  if (excluded) params.set("excluded", excluded);
  if (q) params.set("q", q);
  const records = useQuery({
    queryKey: ["records", jobId, params.toString()],
    queryFn: () => api.get<Page<RecordRow>>(`${base}/jobs/${jobId}/records?${params}`),
    refetchInterval: terminal ? false : 4000,
  });
  const fields = schema.spec.fields;

  return (
    <Card>
      <div className="row wrap">
        <input placeholder="Search values" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} aria-label="Status">
          <option value="">All statuses</option><option value="valid">Complete</option>
          <option value="partial">Partial</option><option value="invalid">Missing required</option></select>
        <select value={excluded} onChange={(e) => { setExcluded(e.target.value as typeof excluded); setOffset(0); }} aria-label="Excluded">
          <option value="false">Included</option><option value="true">Excluded</option><option value="">All</option></select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="quality">Best quality first</option><option value="-quality">Worst quality first</option>
          <option value="created">Oldest first</option><option value="updated">Recently edited</option></select>
      </div>
      <div className="scroll">
        <table className="records">
          <thead><tr><th>Status</th>{fields.map((f) => <th key={f.name}>{f.label || f.name}</th>)}<th>Quality</th></tr></thead>
          <tbody>{records.data?.items.map((r) => (
            <tr key={r.id} onClick={() => setOpen(r.id)} className={r.excluded ? "excluded clickable" : "clickable"}>
              <td><Badge value={r.status} />{r.user_edited && <span className="small muted"> edited</span>}</td>
              {fields.map((f) => <td key={f.name} className="cell">{display(r.data[f.name])}</td>)}
              <td>{Math.round(r.quality_score * 100)}%</td>
            </tr>))}
          </tbody>
        </table>
      </div>
      {records.data && <Pager total={records.data.total} limit={limit} offset={offset} onChange={setOffset} />}
      {records.data?.total === 0 && <p className="muted">{terminal ? "No records match." : "Records appear here as sites are read; they refresh about every 20 seconds."}</p>}
      {open && <RecordDrawer base={base} recordId={open} schema={schema} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function Urls({ base, jobId }: { base: string; jobId: string }) {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const urls = useQuery({
    queryKey: ["urls", jobId, status, offset],
    queryFn: () => api.get<Page<CrawlUrl>>(`${base}/jobs/${jobId}/urls?limit=${limit}&offset=${offset}${status ? `&status=${status}` : ""}`),
  });
  return (
    <Card>
      <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} aria-label="Page status">
        {URL_STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All pages"}</option>)}</select>
      <table>
        <thead><tr><th>URL</th><th>Found via</th><th>Depth</th><th>Status</th><th>Reason</th></tr></thead>
        <tbody>{urls.data?.items.map((u) => (
          <tr key={u.id}><td className="url">{u.url}</td><td>{u.method}</td><td>{u.depth}</td>
            <td><Badge value={u.status} /></td><td className="small">{u.status_reason}</td></tr>))}
        </tbody>
      </table>
      {urls.data && <Pager total={urls.data.total} limit={limit} offset={offset} onChange={setOffset} />}
    </Card>
  );
}

function Events({ base, jobId, live }: { base: string; jobId: string; live: boolean }) {
  const events = useQuery({ queryKey: ["events", jobId], queryFn: () => api.get<JobEvent[]>(`${base}/jobs/${jobId}/events`),
    refetchInterval: live ? 3000 : false });
  return (
    <Card>
      <ul className="events">{events.data?.map((e) => (
        <li key={e.id}><span className="muted small">{when(e.created_at)}</span>{" "}
          {e.to_state ? <Badge value={e.to_state} /> : <Badge value={e.type} />} {e.message}</li>))}
      </ul>
    </Card>
  );
}

function Exports({ base, jobId, state }: { base: string; jobId: string; state: string }) {
  const qc = useQueryClient();
  const [partial, setPartial] = useState(true);
  const [invalid, setInvalid] = useState(false);
  const [withExcluded, setWithExcluded] = useState(false);
  const list = useQuery({
    queryKey: ["exports", jobId], queryFn: () => api.get<ExportRow[]>(`${base}/jobs/${jobId}/exports`),
    refetchInterval: (q) => (q.state.data?.some((e) => e.status === "pending") ? 1500 : false),
  });
  const create = useMutation({
    mutationFn: () => api.post<ExportRow>(`${base}/jobs/${jobId}/exports`, {
      statuses: ["valid", ...(partial ? ["partial"] : []), ...(invalid ? ["invalid"] : [])],
      include_excluded: withExcluded }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports", jobId] }),
  });
  if (state !== "completed" && state !== "partially_completed") return null;
  return (
    <Card title="Export to Excel">
      <div className="row wrap">
        <label className="check"><input type="checkbox" checked disabled /> Complete records</label>
        <label className="check"><input type="checkbox" checked={partial} onChange={(e) => setPartial(e.target.checked)} /> Partial records</label>
        <label className="check"><input type="checkbox" checked={invalid} onChange={(e) => setInvalid(e.target.checked)} /> Records missing required fields</label>
        <label className="check"><input type="checkbox" checked={withExcluded} onChange={(e) => setWithExcluded(e.target.checked)} /> Excluded records</label>
        <button className="primary" onClick={() => create.mutate()} disabled={create.isPending}>Create .xlsx</button>
      </div>
      <ErrorBox error={create.error} />
      <table>
        <thead><tr><th>Created</th><th>Status</th><th>Rows</th><th>Size</th><th>Expires</th><th /></tr></thead>
        <tbody>{list.data?.map((e) => (
          <tr key={e.id}><td>{when(e.created_at)}</td><td><Badge value={e.status} /></td><td>{e.row_count}</td>
            <td>{e.file_bytes ? `${Math.round(e.file_bytes / 1024)} KB` : ""}</td><td className="small">{when(e.expires_at)}</td>
            <td>{e.download_url && <a href={e.download_url}>Download</a>}
              {e.error && <span className="error small">{e.error}</span>}</td></tr>))}
        </tbody>
      </table>
      <p className="muted small">Download links are tied to your session and expire after five minutes; refresh the page for a new one.</p>
    </Card>
  );
}
