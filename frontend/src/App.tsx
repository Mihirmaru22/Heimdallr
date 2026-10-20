import { Link, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { localStorageSet, useSession } from "./session";
import LoginPage from "./pages/Login";
import ProjectsPage from "./pages/Projects";
import ProjectPage from "./pages/Project";
import JobPage from "./pages/Job";
import SettingsPage from "./pages/Settings";
import AdminPage from "./pages/Admin";
import { VersionBanner, VersionFooter } from "./components/VersionCheck";

export default function App() {
  const { me, loading, orgId } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  if (loading) return <div className="center muted">Loading…</div>;
  if (!me) return <LoginPage />;

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    qc.clear();
    navigate("/");
    qc.invalidateQueries({ queryKey: ["me"] });
  };

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">WebData AI</Link>
        <nav>
          <NavLink to="/" end>Projects</NavLink>
          <NavLink to="/settings">Organization</NavLink>
          {me.user.is_platform_admin && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="spacer" />
        {me.organizations.length > 1 && (
          <select aria-label="Organization" value={orgId ?? ""}
                  onChange={(e) => { localStorageSet("wd_org", e.target.value); qc.invalidateQueries(); navigate("/"); }}>
            {me.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        )}
        <span className="muted small">{me.user.email}</span>
        <button className="link" onClick={logout}>Sign out</button>
      </header>
      <VersionBanner />
      <main>
        {!orgId ? <p>You are not a member of any organization.</p> : (
          <Routes>
            <Route path="/" element={<ProjectsPage orgId={orgId} />} />
            <Route path="/projects/:projectId" element={<ProjectPage orgId={orgId} />} />
            <Route path="/jobs/:jobId" element={<JobPage orgId={orgId} />} />
            <Route path="/settings" element={<SettingsPage orgId={orgId} />} />
            {me.user.is_platform_admin && <Route path="/admin" element={<AdminPage />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
      <VersionFooter />
    </div>
  );
}
