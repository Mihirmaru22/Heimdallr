import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ErrorBox } from "../components/ui";

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
      <h1>WebData AI</h1>
      <p className="muted">Turn a plain-language request into a reviewed, sourced Excel file.</p>
      <form onSubmit={submit} className="card">
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                           autoComplete="email" /></label>
        <label>Password<input type="password" required minLength={mode === "register" ? 10 : 1} value={password}
                              onChange={(e) => setPassword(e.target.value)}
                              autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {mode === "register" && (
          <label>Organization name (optional)<input value={org} onChange={(e) => setOrg(e.target.value)} /></label>
        )}
        <ErrorBox error={error} />
        <button className="primary" disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "No account? Create one" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
