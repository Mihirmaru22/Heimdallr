import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type Job, type Page, type Project } from "../api";
import { Badge, Card, ErrorBox, when } from "../components/ui";

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
    <div className="grid2">
      <Card title="Projects">
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
          <input placeholder="New project name" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="primary" disabled={create.isPending}>Create</button>
        </form>
        <ErrorBox error={create.error || projects.error} />
        <ul className="list">
          {projects.data?.items.map((p) => (
            <li key={p.id}><Link to={`/projects/${p.id}`}>{p.name}</Link>
              <span className="muted small"> created {when(p.created_at)}</span></li>
          ))}
          {projects.data?.items.length === 0 && <li className="muted">No projects yet.</li>}
        </ul>
      </Card>
      <Card title="Recent jobs">
        <table>
          <thead><tr><th>Project</th><th>State</th><th>Pages</th><th>Records</th><th>Started</th></tr></thead>
          <tbody>
            {jobs.data?.items.map((j) => (
              <tr key={j.id}>
                <td><Link to={`/jobs/${j.id}`}>{names.get(j.project_id) ?? "Job"}</Link></td>
                <td><Badge value={j.state} /></td>
                <td>{j.counters.fetched ?? 0}</td>
                <td>{j.counters.extracted ?? 0}</td>
                <td className="small">{when(j.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {jobs.data?.items.length === 0 && <p className="muted">No jobs yet.</p>}
      </Card>
    </div>
  );
}
