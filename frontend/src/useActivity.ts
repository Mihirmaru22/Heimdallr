import { useEffect, useRef, useState } from "react";
import { api, type Activity } from "./api";

const MAX_LINES = 3000;

// The job's activity lines, polled every second while it runs. Shared by the feed and the lens so both
// show the same steps at the same moment.
export function useActivity(base: string, jobId: string, live: boolean) {
  const [lines, setLines] = useState<Activity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const lastId = useRef(0);

  useEffect(() => { lastId.current = 0; setLines([]); }, [base, jobId]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const fresh = await api.get<Activity[]>(`${base}/jobs/${jobId}/activity?after_id=${lastId.current}&limit=500`);
        if (stopped) return;
        setError(null);
        if (fresh.length) {
          lastId.current = fresh[fresh.length - 1].id;
          setLines((old) => [...old, ...fresh].slice(-MAX_LINES));
          // A full page means more lines are waiting: fetch them right away instead of in a second.
          if (fresh.length === 500) { timer = setTimeout(poll, 0); return; }
        }
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
      // Keep polling while the job runs; once it has finished, one more pass picks up the last lines.
      if (!stopped && live) timer = setTimeout(poll, 1000);
    };
    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [base, jobId, live]);

  return { lines, error };
}
