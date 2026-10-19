import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Member, type Usage } from "../api";
import { Card, ErrorBox, when } from "../components/ui";
import { useSession } from "../session";

const LIMIT_LABELS: Record<string, string> = {
  max_pages_per_job: "Pages per job", max_depth: "Link depth", max_active_jobs_per_org: "Active jobs at once",
  max_pages_per_org_month: "Pages per month", max_records_per_job: "Records per job", max_export_rows: "Rows per export",
};

export default function SettingsPage({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const { me } = useSession();
  const role = me?.organizations.find((o) => o.id === orgId)?.role;
  const canManage = role === "owner" || role === "admin";
  const usage = useQuery({ queryKey: ["usage", orgId], queryFn: () => api.get<Usage>(`/orgs/${orgId}/usage`) });
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => api.get<Member[]>(`/orgs/${orgId}/members`) });
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState("member");
  const refresh = () => qc.invalidateQueries({ queryKey: ["members", orgId] });
  const add = useMutation({ mutationFn: () => api.post(`/orgs/${orgId}/members`, { email, role: newRole }),
    onSuccess: () => { setEmail(""); refresh(); } });
  const change = useMutation({ mutationFn: ({ id, role }: { id: string; role: string }) =>
    api.patch(`/orgs/${orgId}/members/${id}`, { role }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => api.del(`/orgs/${orgId}/members/${id}`), onSuccess: refresh });
  const u = usage.data;

  return (
    <div className="grid2">
      <Card title={`Usage ${u?.period ?? ""}`}>
        {u && (
          <table><tbody>
            <tr><td>Pages fetched this month</td><td>{u.pages} / {u.limits.max_pages_per_org_month}</td></tr>
            <tr><td>Active jobs</td><td>{u.active_jobs} / {u.limits.max_active_jobs_per_org}</td></tr>
            <tr><td>Rows exported this month</td><td>{u.export_rows}</td></tr>
            <tr><td>AI model requests this month</td><td>{u.llm_requests} (Phase 1 makes none)</td></tr>
            {Object.entries(u.limits).filter(([k]) => !["max_pages_per_org_month", "max_active_jobs_per_org"].includes(k))
              .map(([k, v]) => <tr key={k}><td>{LIMIT_LABELS[k] ?? k}</td><td>{v}</td></tr>)}
          </tbody></table>)}
      </Card>
      <Card title="Members">
        <table>
          <thead><tr><th>Email</th><th>Role</th><th>Since</th><th /></tr></thead>
          <tbody>{members.data?.map((m) => (
            <tr key={m.user_id}><td>{m.email}</td>
              <td>{canManage ? (
                <select value={m.role} onChange={(e) => change.mutate({ id: m.user_id, role: e.target.value })}>
                  <option>owner</option><option>admin</option><option>member</option></select>) : m.role}</td>
              <td className="small">{when(m.created_at)}</td>
              <td>{(canManage || m.user_id === me?.user.id) &&
                <button className="link" onClick={() => remove.mutate(m.user_id)}>{m.user_id === me?.user.id ? "Leave" : "Remove"}</button>}</td>
            </tr>))}
          </tbody>
        </table>
        {canManage && (
          <form className="row" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <input type="email" required placeholder="Email of an existing account" value={email} onChange={(e) => setEmail(e.target.value)} />
            <select value={newRole} onChange={(e) => setNewRole(e.target.value)}><option>member</option><option>admin</option></select>
            <button className="primary">Add</button>
          </form>)}
        <ErrorBox error={add.error || change.error || remove.error} />
      </Card>
    </div>
  );
}
