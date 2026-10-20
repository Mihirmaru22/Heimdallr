import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

type Running = { sha: string; branch: string; committed_at?: string; started_at?: string; host?: string };
type VersionReport = {
  expected: string; code_on_disk: (Running & { dirty: boolean }) | null; api: Running; workers: Running[];
  frontend: string | null; up_to_date: boolean; problems: string[];
};

const short = (sha?: string) => (sha && sha !== "unknown" ? sha.slice(0, 7) : "unknown");

// Compares the API, the Celery workers and this page with the code checked out on disk, every minute,
// and warns when any of them still runs older code (the usual cause: a worker that was not restarted).
export function VersionBanner() {
  const report = useVersion();
  if (!report.data || report.data.up_to_date) return null;
  return (
    <div className="error version-banner" role="alert">
      <strong>Running old code.</strong> {report.data.problems.join(" ")}{" "}
      <span className="muted small">Checked out: {short(report.data.expected)}</span>
    </div>
  );
}

export function VersionFooter() {
  const { data } = useVersion();
  if (!data) return null;
  const branch = data.code_on_disk?.branch || data.api.branch;
  const ok = (sha?: string) => (sha === data.expected ? "✓" : `✗ ${short(sha)}`);
  const page = data.frontend === "dev" ? "dev server" : ok(data.frontend ?? undefined);
  return (
    <footer className="muted small version-footer"
            title={`API started ${data.api.started_at ?? ""}; commit date ${data.code_on_disk?.committed_at ?? ""}`}>
      Code: {branch ? `${branch} @ ` : ""}{short(data.expected)}{data.code_on_disk?.dirty ? " (uncommitted changes)" : ""}
      {" · "}API {ok(data.api.sha)}
      {" · "}worker {data.workers.length ? data.workers.map((w) => ok(w.sha)).join(" ") : "not running"}
      {" · "}page {page}
    </footer>
  );
}

function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: () => api.get<VersionReport>(`/version?frontend=${encodeURIComponent(__BUILD_SHA__)}`),
    refetchInterval: 60_000,
    retry: false,
  });
}
