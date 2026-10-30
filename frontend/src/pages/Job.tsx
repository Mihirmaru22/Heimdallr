import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, display, type CompanyRow, type CrawlUrl, type ExportRow, type Job, type Page, type Progress,
  type Project, type RecordRow, type Schema } from "../api";
import { Badge, Card, Crumbs, ErrorBox, Pager, Spinner, when } from "../components/ui";
import RecordDrawer from "../components/RecordDrawer";
import ActivityFeed from "../components/ActivityFeed";
import Mission, { type MissionStat } from "../components/Mission";
import { useActivity } from "../useActivity";
import { Download, Retry, Stop } from "../components/icons";

const URL_STATUSES = ["", "queued", "fetched", "skipped", "blocked_robots", "blocked_policy", "failed", "dead"];
type Tab = "records" | "companies" | "activity" | "urls";

export default function JobPage({ orgId }: { orgId: string }) {
  const { jobId } = useParams();
  const base = `/orgs/${orgId}`;
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("records");

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
  const rows = progress.data?.records ?? 0;
  const notRead = (c.skipped ?? 0) + (c.blocked ?? 0) + (c.failed ?? 0);
  // The run's numbers, shown once. They come from the job's counters, the same totals the export uses.
  const stats: MissionStat[] = [
    ...(!terminal ? [{ label: "pages waiting", value: c.queued ?? 0, cls: "info", hint: "Pages lined up to be read next." }] : []),
    { label: "pages read", value: c.fetched ?? 0, hint: "Pages downloaded and read." },
    { label: "pages not read", value: notRead, cls: "muted",
      hint: `${c.skipped ?? 0} outside the plan or not needed, ${c.blocked ?? 0} refused by the site, ${c.failed ?? 0} failed to load.` },
    { label: "rows", value: rows, cls: "accent", hint: "One row per company or entity found. These go in your spreadsheet." },
    { label: "rows with every field", value: progress.data?.valid_records ?? 0, cls: "ok",
      hint: "Rows where every required column was filled." },
  ];
  const tabs: [Tab, string, number | undefined][] = [
    ["records", "Rows", rows], ["companies", "Companies", undefined],
    ["activity", "Decisions log", undefined], ["urls", "Pages", c.discovered]];

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
        elapsed={progress.data?.elapsed_seconds ?? null} createdAt={job.data?.created_at ?? null} focus={schema.data?.spec.discovery.countries ?? []}
        stats={stats} summary={`${rows.toLocaleString()} row${rows === 1 ? "" : "s"}, ${(progress.data?.valid_records ?? 0).toLocaleString()} with every field, from ${(c.fetched ?? 0).toLocaleString()} pages read.`} />
      {progress.data?.error && <div className="error" role="alert"><strong>{progress.data.error}</strong></div>}
      <ErrorBox error={cancel.error || retry.error} />

      {terminal && job.data && <Exports base={base} jobId={jobId!} state={job.data.state} />}

      <div className="tabs" role="tablist" aria-label="Run details">
        {tabs.map(([t, label, n]) =>
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
            {label}{n != null && n > 0 && <span className="count">{n.toLocaleString()}</span>}</button>)}
      </div>
      {tab === "activity" && <ActivityFeed lines={activity.lines} live={!terminal} error={activity.error} />}
      {tab === "companies" && <Companies base={base} jobId={jobId!} terminal={terminal} />}
      {tab === "records" && schema.data && <Records base={base} jobId={jobId!} schema={schema.data} terminal={terminal} />}
      {tab === "urls" && <Urls base={base} jobId={jobId!} />}
    </div>
  );
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
          <option value="">All statuses</option><option value="valid">Every field</option>
          <option value="partial">Some fields</option><option value="invalid">Missing required fields</option></select>
        <select value={excluded} onChange={(e) => { setExcluded(e.target.value as typeof excluded); setOffset(0); }} aria-label="Excluded">
          <option value="false">In the sheet</option><option value="true">Excluded</option><option value="">All rows</option></select>
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
      {records.data?.total === 0 && <p className="empty">{terminal ? "No rows match." : "Rows appear here as sites are read; they refresh about every 20 seconds."}</p>}
      {open && <RecordDrawer base={base} recordId={open} schema={schema} onClose={() => setOpen(null)} />}
    </Card>
  );
}

// Every company the run came across, with the one decision about it and why (nothing found is dropped silently).
const OUTCOMES = ["", "delivered", "country unconfirmed", "filter not met", "elsewhere", "weak proof", "no proof"];

function Companies({ base, jobId, terminal }: { base: string; jobId: string; terminal: boolean }) {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const companies = useQuery({
    queryKey: ["companies", jobId, status, offset, terminal],
    queryFn: () => api.get<Page<CompanyRow>>(`${base}/jobs/${jobId}/companies?limit=${limit}&offset=${offset}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  });
  return (
    <Card>
      <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} aria-label="Outcome">
        {OUTCOMES.map((s) => <option key={s} value={s}>{s || "All companies"}</option>)}</select>
      <div className="table-wrap"><table>
        <thead><tr><th>Company</th><th>Outcome</th><th>Proof</th><th>Country</th><th>Why</th></tr></thead>
        <tbody>{companies.data?.items.map((co) => (
          <tr key={co.id}>
            <td>{co.name}{co.website && <div className="url small"><a href={co.website} target="_blank" rel="noreferrer noopener">{co.website}</a></div>}</td>
            <td><Badge value={co.status.replace(/ /g, "_")} /></td>
            <td className="small">{co.proof_url ? <a href={co.proof_url} target="_blank" rel="noreferrer noopener">{co.proof_verdict || "link"}</a> : co.proof_verdict}</td>
            <td className="small mono">{co.country}</td>
            <td className="small muted">{co.reasons.join(" · ")}</td></tr>))}
        </tbody>
      </table></div>
      {companies.data && <Pager total={companies.data.total} limit={limit} offset={offset} onChange={setOffset} />}
      {companies.data?.total === 0 && <p className="empty">{terminal ? "No companies were found." : "Companies and their outcomes appear when the run ends."}</p>}
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
            <label className="chip"><input type="checkbox" checked disabled /> Rows with every field</label>
            <label className="chip"><input type="checkbox" checked={partial} onChange={(e) => setPartial(e.target.checked)} /> Rows with some fields</label>
            <label className="chip"><input type="checkbox" checked={invalid} onChange={(e) => setInvalid(e.target.checked)} /> Rows missing required fields</label>
            <label className="chip"><input type="checkbox" checked={withExcluded} onChange={(e) => setWithExcluded(e.target.checked)} /> Excluded rows</label>
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
