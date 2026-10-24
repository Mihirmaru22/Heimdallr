import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Card, ErrorBox } from "../components/ui";

interface AdminOrg { id: string; name: string; slug: string; disabled: boolean; limits: Record<string, number>;
  overrides: Record<string, number>; jobs: number }
interface AdminUser { id: string; email: string; display_name: string; is_platform_admin: boolean; disabled: boolean;
  max_active_jobs: number | null }
interface Policy { id: string; domain: string; org_id: string | null; rule: string; reason: string }

export default function AdminPage() {
  const qc = useQueryClient();
  const orgs = useQuery({ queryKey: ["admin", "orgs"], queryFn: () => api.get<AdminOrg[]>("/admin/orgs") });
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: () => api.get<AdminUser[]>("/admin/users") });
  const policies = useQuery({ queryKey: ["admin", "policies"], queryFn: () => api.get<Policy[]>("/admin/domain-policies") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin"] });
  const updOrg = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => api.patch(`/admin/orgs/${id}`, body), onSuccess: refresh });
  const updUser = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => api.patch(`/admin/users/${id}`, body), onSuccess: refresh });
  const [domain, setDomain] = useState("");
  const [reason, setReason] = useState("");
  const addPolicy = useMutation({ mutationFn: () => api.post("/admin/domain-policies", { domain, reason }),
    onSuccess: () => { setDomain(""); setReason(""); refresh(); } });
  const delPolicy = useMutation({ mutationFn: (id: string) => api.del(`/admin/domain-policies/${id}`), onSuccess: refresh });

  const editLimits = (o: AdminOrg) => {
    const text = window.prompt("Limit overrides as JSON (can only lower platform limits)", JSON.stringify(o.overrides));
    if (text === null) return;
    try { updOrg.mutate({ id: o.id, body: { limits: JSON.parse(text || "{}") } }); }
    catch { window.alert("That is not valid JSON"); }
  };

  return (
    <div>
      <ErrorBox error={updOrg.error || updUser.error || addPolicy.error || delPolicy.error} />
      <Card title="Organizations">
        <table><thead><tr><th>Name</th><th>Jobs</th><th>Effective limits</th><th>Status</th><th /></tr></thead>
          <tbody>{orgs.data?.map((o) => (
            <tr key={o.id}><td>{o.name}<div className="small muted">{o.slug}</div></td><td>{o.jobs}</td>
              <td className="small">{Object.entries(o.limits).map(([k, v]) => `${k}=${v}`).join(", ")}</td>
              <td>{o.disabled ? "disabled" : "active"}</td>
              <td className="nowrap"><button className="link" onClick={() => editLimits(o)}>Limits</button>
                <button className="link" onClick={() => updOrg.mutate({ id: o.id, body: { disabled: !o.disabled } })}>
                  {o.disabled ? "Enable" : "Disable"}</button></td></tr>))}
          </tbody></table>
      </Card>
      <Card title="Users">
        <table><thead><tr><th>Email</th><th>Admin</th><th>Job limit</th><th>Status</th><th /></tr></thead>
          <tbody>{users.data?.map((u) => (
            <tr key={u.id}><td>{u.email}</td><td>{u.is_platform_admin ? "yes" : ""}</td>
              <td><input type="number" min={0} defaultValue={u.max_active_jobs ?? ""} placeholder="org default"
                         onBlur={(e) => updUser.mutate({ id: u.id, body: { max_active_jobs: e.target.value === "" ? null : +e.target.value } })} /></td>
              <td>{u.disabled ? "disabled" : "active"}</td>
              <td><button className="link" onClick={() => updUser.mutate({ id: u.id, body: { disabled: !u.disabled } })}>
                {u.disabled ? "Enable" : "Disable"}</button></td></tr>))}
          </tbody></table>
      </Card>
      <Card title="Blocked domains">
        <p className="muted small">Sites on this list are never crawled (for example after an opt-out request).</p>
        <form className="row" onSubmit={(e) => { e.preventDefault(); addPolicy.mutate(); }}>
          <input placeholder="example.com" value={domain} onChange={(e) => setDomain(e.target.value.toLowerCase())} required />
          <input placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button className="primary">Block</button>
        </form>
        <ul className="list">{policies.data?.map((p) => (
          <li key={p.id}>{p.domain} <span className="muted small">{p.reason}</span>{" "}
            <button className="link" onClick={() => delPolicy.mutate(p.id)}>Remove</button></li>))}
        </ul>
      </Card>
    </div>
  );
}
