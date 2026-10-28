import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type Job, type Page, type Project } from "../api";
import { ago, Badge, Card, ErrorBox, Spinner } from "../components/ui";
import LazyLens from "../components/LazyLens";
import { Arrow, Plus } from "../components/icons";

export default function ProjectsPage({ orgId }: { orgId: string }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const projects = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => api.get<Page<Project>>(`/orgs/${orgId}/projects?limit=200`),
  });
  const jobs = useQuery({
    queryKey: ["jobs", orgId, "recent"],
    queryFn: () => api.get<Page<Job>>(`/orgs/${orgId}/jobs?limit=10`),
    refetchInterval: 5000,
  });
  const create = useMutation({
    mutationFn: () => api.post<Project>(`/orgs/${orgId}/projects`, { name }),
    onSuccess: (p) => navigate(`/projects/${p.id}`),
  });
  const names = new Map((projects.data?.items ?? []).map((p) => [p.id, p.name]));

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <h1>What should the web tell you today?</h1>
          <p>Start a project, ask your question in plain words, check the plan, and watch every source being read.
            You get a spreadsheet where each row links to its proof.</p>
          <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
            <label className="sr-only" htmlFor="new-project">New project name</label>
            <input id="new-project" placeholder="Name a project, e.g. Guidewire insurers in Europe" value={name}
              onChange={(e) => setName(e.target.value)} />
            <button className="primary big" disabled={create.isPending || !name.trim()}>
              {create.isPending ? <Spinner /> : <Plus />} Start</button>
          </form>
          <ErrorBox error={create.error} />
        </div>
        <LazyLens demo />
        <div className="hero-legend" aria-hidden>
          <span><span className="dot seen" />read</span><span><span className="dot kept" />kept</span>
          <span><span className="dot dropped" />dropped</span>
        </div>
      </section>

      <div className="grid2">
        <Card title={<>Projects <span className="muted small">{projects.data?.total ?? ""}</span></>}>
          <ErrorBox error={projects.error} />
          <ul className="index">
            {projects.data?.items.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`}>
                  <span className="name">{p.name}</span>
                  <span className="meta">{ago(p.updated_at || p.created_at)}</span>
                  <span className="go"><Arrow /></span>
                </Link>
              </li>
            ))}
          </ul>
          {projects.data?.items.length === 0 && <p className="empty">No projects yet. Name one above to begin.</p>}
        </Card>
        <Card title="Recent runs">
          <div className="table-wrap">
            <table>
              <thead><tr><th>Project</th><th>State</th><th className="num">Pages</th><th className="num">Records</th><th>Started</th></tr></thead>
              <tbody>
                {jobs.data?.items.map((j) => (
                  <tr key={j.id} className="clickable" onClick={() => navigate(`/jobs/${j.id}`)}>
                    <td><Link to={`/jobs/${j.id}`} onClick={(e) => e.stopPropagation()}>{names.get(j.project_id) ?? "Run"}</Link></td>
                    <td><Badge value={j.state} /></td>
                    <td className="num mono">{j.counters.fetched ?? 0}</td>
                    <td className="num mono">{j.counters.extracted ?? 0}</td>
                    <td className="small muted nowrap">{ago(j.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {jobs.data?.items.length === 0 && <p className="empty">No runs yet.</p>}
        </Card>
      </div>
    </>
  );
}
