import { lazy, Suspense } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { localStorageSet, useSession } from "./session";
import { VersionBanner, VersionFooter } from "./components/VersionCheck";
import { BrandMark } from "./components/ui";
import { Out } from "./components/icons";
import ThemeSwitch from "./components/ThemeSwitch";

// Each page loads on first visit, so visitors don't download the app and signed-in users don't download
// the public pages.
const LoginPage = lazy(() => import("./pages/Login"));
const LandingPage = lazy(() => import("./pages/Landing"));
const ProjectsPage = lazy(() => import("./pages/Projects"));
const ProjectPage = lazy(() => import("./pages/Project"));
const JobPage = lazy(() => import("./pages/Job"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const AdminPage = lazy(() => import("./pages/Admin"));
const pageFallback = <div className="center"><BrandMark className="brand-mark" /></div>;

export default function App() {
  const { me, loading, orgId } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  if (loading) return <div className="center"><BrandMark className="brand-mark" /></div>;
  if (!me) {
    // Signed out: the home page at "/", the sign-in page at /login; any other link asks to sign in first.
    const next = location.pathname !== "/" && location.pathname !== "/login" ? location.pathname : "";
    return (
      <Suspense fallback={pageFallback}><Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} replace />} />
      </Routes></Suspense>
    );
  }

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    qc.clear();
    navigate("/");
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const initial = (me.user.display_name || me.user.email).trim()[0]?.toUpperCase() ?? "?";

  return (
    <div className="shell">
      <a href="#main" className="skip">Skip to content</a>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="WebData AI home"><BrandMark /> <span className="brand-name">WebData AI</span> <small>free models</small></Link>
        <nav className="topnav" aria-label="Main">
          <NavLink to="/" end>Research</NavLink>
          <NavLink to="/settings">Organization</NavLink>
          {me.user.is_platform_admin && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="spacer" />
        <ThemeSwitch />
        {me.organizations.length > 1 && (
          <select aria-label="Organization" value={orgId ?? ""}
                  onChange={(e) => { localStorageSet("wd_org", e.target.value); qc.invalidateQueries(); navigate("/"); }}>
            {me.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        )}
        <div className="user">
          <span className="avatar" title={me.user.email} aria-hidden>{initial}</span>
          <span className="user-email">{me.user.email}</span>
          <button className="icon" onClick={logout} aria-label="Sign out" title="Sign out"><Out /></button>
        </div>
      </header>
      <VersionBanner />
      <main className="page" id="main">
        <div className="page-in" key={location.pathname}>
          {!orgId ? <p>You are not a member of any organization.</p> : (
            <Suspense fallback={<div className="page-loading" aria-busy="true" />}><Routes>
              <Route path="/" element={<ProjectsPage orgId={orgId} />} />
              <Route path="/projects/:projectId" element={<ProjectPage orgId={orgId} />} />
              <Route path="/jobs/:jobId" element={<JobPage orgId={orgId} />} />
              <Route path="/settings" element={<SettingsPage orgId={orgId} />} />
              {me.user.is_platform_admin && <Route path="/admin" element={<AdminPage />} />}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes></Suspense>
          )}
        </div>
      </main>
      <VersionFooter />
    </div>
  );
}
