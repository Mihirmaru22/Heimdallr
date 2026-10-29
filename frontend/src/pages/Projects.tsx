import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type Job, type Page, type Project, type Usage } from "../api";
import { ago, Badge, ErrorBox, Spinner } from "../components/ui";
import LazyGlobe from "../components/LazyGlobe";
import { AnimatedNumber } from "../components/Mission";
import { Arrow, Folder, Plus } from "../components/icons";

const LIVE = new Set(["created", "validating", "planning", "queued", "running", "waiting_quota", "validating_results", "exporting"]);

// The signed-in dashboard: start a project, this month at a glance, your projects with their latest run,
// and the recent runs.
export default function ProjectsPage({ orgId }: { orgId: string }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const projects = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => api.get<Page<Project>>(`/orgs/${orgId}/projects?limit=200`),
  });
  const jobs = useQuery({
    queryKey: ["jobs", orgId, "recent"],
    queryFn: () => api.get<Page<Job>>(`/orgs/${orgId}/jobs?limit=12`),
    refetchInterval: 5000,
  });
  const usage = useQuery({ queryKey: ["usage", orgId], queryFn: () => api.get<Usage>(`/orgs/${orgId}/usage`) });
  const create = useMutation({
    mutationFn: () => api.post<Project>(`/orgs/${orgId}/projects`, { name }),
    onSuccess: (p) => navigate(`/projects/${p.id}`),
  });
  const items = projects.data?.items ?? [];
  const runs = jobs.data?.items ?? [];
  const names = new Map(items.map((p) => [p.id, p.name]));
  // The latest run of each project (runs come newest first).
  const latest = new Map<string, Job>();
  for (const j of runs) if (!latest.has(j.project_id)) latest.set(j.project_id, j);
  const live = runs.filter((j) => LIVE.has(j.state));
  const u = usage.data;
  const stats: [string, number | undefined, string][] = [
    ["Projects", projects.data?.total, ""],
    ["Runs going now", u?.active_jobs ?? live.length, "accent"],
    ["Pages read this month", u?.pages, ""],
    ["Rows exported this month", u?.export_rows, "ok"],
    ["Free model calls this month", u?.llm_requests, "info"],
  ];

  return (
    <div className="dash">
      <section className="dash-hero">
        <div className="dash-hero-copy">
          <span className="dash-kicker">Research</span>
          <h1>What should the web tell you today?</h1>
          <p>Name a project, ask in plain words, check the plan, then watch every source being read.</p>
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
            <label className="sr-only" htmlFor="new-project">New project name</label>
            <input id="new-project" placeholder="Name a project, e.g. Guidewire insurers in Europe" value={name}
              onChange={(e) => setName(e.target.value)} />
            <button className="primary big" disabled={create.isPending || !name.trim()}>
              {create.isPending ? <Spinner /> : <Plus />} New project</button>
          </form>
          <ErrorBox error={create.error} />
        </div>
        <div className="dash-hero-globe" aria-hidden><LazyGlobe demo labels={false} /></div>
      </section>

      <section className="dash-stats" aria-label="This month">
        {stats.map(([label, n, cls]) => (
          <div key={label} className={`dash-stat ${cls}`}>
            <b className="mono">{n == null ? "–" : <AnimatedNumber value={n} />}</b>
            <span>{label}</span>
          </div>
        ))}
      </section>

      <div className="dash-grid">
        <section className="dash-panel" aria-labelledby="dash-projects">
          <header className="dash-panel-head">
            <h2 id="dash-projects">Projects <span className="count">{projects.data?.total ?? ""}</span></h2>
          </header>
          <ErrorBox error={projects.error} />
          <div className="proj-grid">
            {items.map((p) => {
              const j = latest.get(p.id);
              return (
                <Link key={p.id} to={`/projects/${p.id}`} className="proj-card">
                  <span className="proj-icon" aria-hidden><Folder size={18} /></span>
                  <span className="proj-name">{p.name}</span>
                  <span className="proj-meta">Updated {ago(p.updated_at || p.created_at)}</span>
                  <span className="proj-run">
                    {j ? <><Badge value={j.state} /><span className="mono">{j.counters.fetched ?? 0} pages · {j.counters.extracted ?? 0} rows</span></>
                      : <span className="muted">No runs yet</span>}
                  </span>
                  <span className="proj-go" aria-hidden><Arrow /></span>
                </Link>
              );
            })}
            <button type="button" className="proj-card proj-new" onClick={() => document.getElementById("new-project")?.focus()}>
              <span className="proj-icon" aria-hidden><Plus size={18} /></span>
              <span className="proj-name">New project</span>
              <span className="proj-meta">Name it above, then ask your question</span>
            </button>
          </div>
        </section>

        <section className="dash-panel" aria-labelledby="dash-runs">
          <header className="dash-panel-head">
            <h2 id="dash-runs">Recent runs</h2>
            {live.length > 0 && <span className="live-pill"><span className="pulse" aria-hidden /> {live.length} live</span>}
          </header>
          <ol className="run-list">
            {runs.map((j) => (
              <li key={j.id}>
                <Link to={`/jobs/${j.id}`} className={`run-item ${LIVE.has(j.state) ? "is-live" : ""}`}>
                  <span className={`run-dot s-${j.state}`} aria-hidden />
                  <span className="run-main">
                    <b>{names.get(j.project_id) ?? "Run"}</b>
                    <small>{ago(j.created_at)} · <span className="mono">{j.counters.fetched ?? 0}</span> pages · <span className="mono">{j.counters.extracted ?? 0}</span> rows</small>
                  </span>
                  <Badge value={j.state} />
                </Link>
              </li>
            ))}
          </ol>
          {runs.length === 0 && <p className="empty">No runs yet. Open a project and press Run.</p>}
        </section>
      </div>
    </div>
  );
}
