import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { BrandMark, ErrorBox, Spinner } from "../components/ui";
import LazyLens from "../components/LazyLens";
import ThemeSwitch from "../components/ThemeSwitch";
import { Arrow } from "../components/icons";

export default function LoginPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"login" | "register">("login");
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
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <section className="auth-stage" aria-label="About WebData AI">
        <LazyLens demo />
        <div className="brand"><BrandMark /> WebData AI</div>
        <div>
          <p className="auth-title">Ask the web a question. <em>Keep</em> only what it can prove.</p>
          <p className="muted" style={{ maxWidth: "44ch", marginTop: 16 }}>
            Every row in your spreadsheet comes from a page that was read, checked and cited. Free models, open sources.</p>
        </div>
        <div className="auth-foot">
          <span><span className="dot seen" />site read</span>
          <span><span className="dot kept" />kept, with proof</span>
          <span><span className="dot dropped" />dropped</span>
        </div>
      </section>
      <main className="auth-panel">
        <form onSubmit={submit} className="auth-form">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div className="segmented" role="group" aria-label="Sign in or create an account">
              <button type="button" aria-pressed={mode === "login"} onClick={() => setMode("login")}>Sign in</button>
              <button type="button" aria-pressed={mode === "register"} onClick={() => setMode("register")}>Create account</button>
            </div>
            <ThemeSwitch />
          </div>
          <h1>{mode === "login" ? "Welcome back" : "Start researching"}</h1>
          <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                             autoComplete="email" placeholder="you@company.com" /></label>
          <label>Password
            <input type="password" required minLength={mode === "register" ? 10 : 1} value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" && <span className="field-hint">At least 10 characters.</span>}
          </label>
          {mode === "register" && (
            <label>Organization name <span className="field-hint">optional</span>
              <input value={org} onChange={(e) => setOrg(e.target.value)} /></label>
          )}
          <ErrorBox error={error} />
          <button className="primary big" disabled={busy}>
            {busy ? <Spinner /> : null}{mode === "login" ? "Sign in" : "Create account"}
            {!busy && <span className="ico-go"><Arrow /></span>}</button>
        </form>
      </main>
    </div>
  );
}
