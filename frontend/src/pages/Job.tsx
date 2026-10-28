import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, display, type CrawlUrl, type ExportRow, type Job, type JobEvent, type Page, type Progress,
  type Project, type RecordRow, type Schema } from "../api";
import { Badge, Card, Crumbs, ErrorBox, Pager, Spinner, when } from "../components/ui";
import RecordDrawer from "../components/RecordDrawer";
import ActivityFeed from "../components/ActivityFeed";
import Mission from "../components/Mission";
import { useActivity } from "../useActivity";
import { Download, Retry, Stop } from "../components/icons";

const URL_STATUSES = ["", "queued", "fetched", "skipped", "blocked_robots", "blocked_policy", "failed", "dead"];
type Tab = "activity" | "records" | "urls" | "events";

export default function JobPage({ orgId }: { orgId: string }) {
  const { jobId } = useParams();
  const base = `/orgs/${orgId}`;
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("activity");

  const progress = useQuery({
    queryKey: ["progress", jobId], queryFn: () => api.get<Progress>(`${base}/jobs/${jobId}/progress`),
    refetchInterval: (q) => (q.state.data?.terminal ? false : 2000),
  });
  const job = useQuery({ queryKey: ["job", jobId, progress.data?.state], queryFn: () => api.get<Job>(`${base}/jobs/${jobId}`) });
  const schema = useQuery({ queryKey: ["schema", job.data?.schema_id], enabled: !!job.data,
    queryFn: () => api.get<Schema>(`${base}/schemas/${job.data!.schema_id}`) });
  const project = useQuery({ queryKey: ["project", job.data?.project_id], enabled: !!job.data,
    queryFn: () => api.get<Project>(`${base}/projects/${job.data!.project_id}`) });
  const terminal = progress.data?.terminal ?? false;
  const activity = useActivity(base, jobId!, !terminal);

  const cancel = useMutation({ mutationFn: () => api.post(`${base}/jobs/${jobId}/cancel`), onSuccess: () => qc.invalidateQueries() });
  const retry = useMutation({ mutationFn: () => api.post(`${base}/jobs/${jobId}/retry`), onSuccess: () => qc.invalidateQueries() });
  const c = progress.data?.counters ?? {};
  const state = progress.data?.state ?? "…";
  const tabs: [Tab, string, number | undefined][] = [
    ["activity", "Full log", activity.lines.length], ["records", "Records", progress.data?.records],
    ["urls", "Pages", c.discovered], ["events", "Events", undefined]];

  const crumbs = <Crumbs items={[["Research", "/"], [project.data?.name ?? "Project", job.data ? `/projects/${job.data.project_id}` : null], ["Run", null]]} />;
  const actions = <>
    {!terminal && <button className="danger" onClick={() => cancel.mutate()}
      disabled={cancel.isPending || state === "cancel_requested"}><Stop /> Cancel</button>}
    {(state === "failed" || state === "cancelled") &&
      <button onClick={() => retry.mutate()} disabled={retry.isPending}><Retry /> Retry</button>}
  </>;

  return (
    <div>
      <Mission lines={activity.lines} live={!terminal} state={state} crumbs={crumbs} actions={actions}
        title={schema.data?.spec.title || project.data?.name || "Research run"} question={schema.data?.nl_request}
        elapsed={progress.data?.elapsed_seconds ?? null} createdAt={job.data?.created_at ?? null} focus={schema.data?.spec.discovery.countries ?? []} />
      {progress.data?.error && <div className="error" role="alert"><strong>{progress.data.error}</strong></div>}
      <ErrorBox error={cancel.error || retry.error} />

      <div className="stats">
        <Stat label="Sites found" value={c.discovered} /><Stat label="Pages fetched" value={c.fetched} />
        <Stat label="Queued" value={c.queued} /><Stat label="Skipped" value={c.skipped} />
        <Stat label="Blocked" value={c.blocked} /><Stat label="Failed" value={c.failed} />
        <Stat label="Records" value={progress.data?.records} /><Stat label="Complete records" value={progress.data?.valid_records} />
        <Stat label="Duplicates merged" value={c.records_duplicates} />
      </div>

      {terminal && job.data && <Exports base={base} jobId={jobId!} state={job.data.state} />}

      <div className="tabs" role="tablist" aria-label="Run details">
        {tabs.map(([t, label, n]) =>
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {label}{n != null && n > 0 && <span className="count">{n.toLocaleString()}</span>}</button>)}
      </div>
      {tab === "activity" && <ActivityFeed lines={activity.lines} live={!terminal} error={activity.error} />}
      {tab === "records" && schema.data && <Records base={base} jobId={jobId!} schema={schema.data} terminal={terminal} />}
      {tab === "urls" && <Urls base={base} jobId={jobId!} />}
      {tab === "events" && <Events base={base} jobId={jobId!} live={!terminal} />}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string | undefined }) {
  return <div className="stat"><div className="v">{typeof value === "number" ? value.toLocaleString() : value ?? 0}</div><div className="l">{label}</div></div>;
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
        <input aria-label="Search values" placeholder="Search values" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} aria-label="Status">
          <option value="">All statuses</option><option value="valid">Complete</option>
          <option value="partial">Partial</option><option value="invalid">Missing required</option></select>
        <select value={excluded} onChange={(e) => { setExcluded(e.target.value as typeof excluded); setOffset(0); }} aria-label="Excluded">
          <option value="false">Included</option><option value="true">Excluded</option><option value="">All</option></select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="quality">Best quality first</option><option value="-quality">Worst quality first</option>
          <option value="created">Oldest first</option><option value="updated">Recently edited</option></select>
      </div>
      <div className="table-wrap">
        <table className="records">
          <thead><tr><th>Status</th>{fields.map((f) => <th key={f.name}>{f.label || f.name}</th>)}<th className="num">Quality</th></tr></thead>
          <tbody>{records.data?.items.map((r) => (
            <tr key={r.id} onClick={() => setOpen(r.id)} className={r.excluded ? "excluded clickable" : "clickable"}>
              <td><Badge value={r.status} />{r.user_edited && <span className="small muted"> edited</span>}</td>
              {fields.map((f) => <td key={f.name} className="cell">{display(r.data[f.name])}</td>)}
              <td className="num mono">{Math.round(r.quality_score * 100)}%</td>
            </tr>))}
          </tbody>
        </table>
      </div>
      {records.data && <Pager total={records.data.total} limit={limit} offset={offset} onChange={setOffset} />}
      {records.data?.total === 0 && <p className="empty">{terminal ? "No records match." : "Records appear here as sites are read; they refresh about every 20 seconds."}</p>}
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
      <div className="table-wrap"><table>
        <thead><tr><th>URL</th><th>Found via</th><th className="num">Depth</th><th>Status</th><th>Reason</th></tr></thead>
        <tbody>{urls.data?.items.map((u) => (
          <tr key={u.id}><td className="url small"><a href={u.url} target="_blank" rel="noreferrer noopener">{u.url}</a></td><td className="small">{u.method}</td><td className="num mono">{u.depth}</td>
            <td><Badge value={u.status} /></td><td className="small muted">{u.status_reason}</td></tr>))}
        </tbody>
      </table></div>
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
        <li key={e.id}><span className="muted mono">{when(e.created_at)}</span>
          {e.to_state ? <Badge value={e.to_state} /> : <Badge value={e.type} />} {e.message}</li>))}
      </ul>
      {events.data?.length === 0 && <p className="empty">No events yet.</p>}
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
  if (state !== "completed" && state !== "partially_completed" && state !== "failed") return null;
  const latest = list.data?.find((e) => e.status === "ready" && e.download_url);
  return (
    <Card>
      <div className="export-card">
        <div>
          <h2>Your spreadsheet</h2>
          <p className="muted small" style={{ marginTop: 6 }}>An .xlsx with one sheet of rows plus Evidence, Rejected and Diagnostics sheets.</p>
          <div className="chips" style={{ marginTop: 12 }}>
            <label className="chip"><input type="checkbox" checked disabled /> Complete records</label>
            <label className="chip"><input type="checkbox" checked={partial} onChange={(e) => setPartial(e.target.checked)} /> Partial records</label>
            <label className="chip"><input type="checkbox" checked={invalid} onChange={(e) => setInvalid(e.target.checked)} /> Missing required fields</label>
            <label className="chip"><input type="checkbox" checked={withExcluded} onChange={(e) => setWithExcluded(e.target.checked)} /> Excluded records</label>
          </div>
        </div>
        <div className="page-actions">
          {latest && <a className="btn" href={latest.download_url!}><Download /> Download latest</a>}
          <button className="primary big" onClick={() => create.mutate()} disabled={create.isPending}>
            {create.isPending ? <Spinner /> : <Download />} Create .xlsx</button>
        </div>
      </div>
      <ErrorBox error={create.error} />
      {(list.data?.length ?? 0) > 0 && (
        <details className="more">
          <summary>All exports <span className="muted small">{list.data!.length}</span></summary>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Created</th><th>Status</th><th className="num">Rows</th><th className="num">Size</th><th>Expires</th><th /></tr></thead>
              <tbody>{list.data?.map((e) => (
                <tr key={e.id}><td className="small">{when(e.created_at)}</td><td><Badge value={e.status} /></td><td className="num mono">{e.row_count}</td>
                  <td className="num mono">{e.file_bytes ? `${Math.round(e.file_bytes / 1024)} KB` : ""}</td><td className="small muted">{when(e.expires_at)}</td>
                  <td>{e.download_url && <a href={e.download_url}>Download</a>}
                    {e.error && <span className="error small">{e.error}</span>}</td></tr>))}
              </tbody>
            </table>
          </div>
          <p className="muted small">Download links are tied to your session and expire after five minutes; refresh the page for a new one.</p>
        </details>
      )}
    </Card>
  );
}
