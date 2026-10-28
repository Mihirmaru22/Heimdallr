import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { api } from "../api";
import { BrandMark, ErrorBox, Spinner } from "../components/ui";
import LazyGlobe from "../components/LazyGlobe";
import Ticker from "../components/Ticker";
import { Arrow, Back, Check } from "../components/icons";

export default function LoginPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "register" ? "register" : "login";
  const setMode = (m: "login" | "register") => setParams(m === "register" ? { mode: m } : {}, { replace: true });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await api.post("/auth/login", { email, password });
      else await api.post("/auth/register", { email, password, organization_name: org });
      navigate(params.get("next") || "/", { replace: true });
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="signin force-dark">
      <div className="signin-globe" aria-hidden><LazyGlobe demo labels={false} horizon={0.56} /></div>
      <div className="signin-scrim" aria-hidden />
      <header className="signin-top">
        <Link to="/" className="brand" aria-label="WebData AI home"><BrandMark /> WebData AI</Link>
        <Link to="/" className="btn ghost-btn"><Back /> Home</Link>
      </header>

      <div className="signin-body">
        <section className="signin-copy" aria-label="About WebData AI">
          <h2>Every row comes from a page that was <em>read, checked and cited.</em></h2>
          <ul className="land-rules">
            <li><span aria-hidden><Check size={14} /></span>Free models and open sources</li>
            <li><span aria-hidden><Check size={14} /></span>Watch every search and page live</li>
            <li><span aria-hidden><Check size={14} /></span>Export with proof links and rejected sites</li>
          </ul>
          <Ticker rows={4} className="signin-ticker" />
        </section>

        <main className="signin-card">
          <div className="signin-tabs" role="tablist" aria-label="Sign in or create an account">
            {(["login", "register"] as const).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}>
                {mode === m && <motion.span layoutId="signin-tab" className="signin-tab-bg" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                <span>{m === "login" ? "Sign in" : "Create account"}</span>
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={mode} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22 }}>
              <h1>{mode === "login" ? "Welcome back" : "Start researching"}</h1>
              <p className="signin-sub">{mode === "login" ? "Sign in to pick up your research where you left it."
                : "Create an account and ask your first question in a minute."}</p>
            </motion.div>
          </AnimatePresence>
          <form onSubmit={submit} className="signin-form">
            <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                               autoComplete="email" placeholder="you@company.com" autoFocus /></label>
            <label>Password
              <input type="password" required minLength={mode === "register" ? 10 : 1} value={password}
                     onChange={(e) => setPassword(e.target.value)} placeholder={mode === "register" ? "At least 10 characters" : ""}
                     autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </label>
            {mode === "register" && (
              <label>Organization name <span className="field-hint">optional</span>
                <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="Your team or company" /></label>
            )}
            <ErrorBox error={error} />
            <button className="primary big" disabled={busy}>
              {busy ? <Spinner /> : null}{mode === "login" ? "Sign in" : "Create account"}
              {!busy && <span className="ico-go"><Arrow /></span>}</button>
          </form>
          <p className="signin-switch">
            {mode === "login" ? <>New here? <button type="button" className="link" onClick={() => setMode("register")}>Create an account</button></>
              : <>Already have an account? <button type="button" className="link" onClick={() => setMode("login")}>Sign in</button></>}
          </p>
        </main>
      </div>
    </div>
  );
}
