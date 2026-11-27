import { useEffect, useMemo, useRef, useState } from "react";
import type { Activity } from "./api";

// Replays a finished run's real activity lines, in their recorded order, at a fixed speed (10x by default).
// Nothing is invented: the lines, their order and their timestamps are the stored ones. Time is only
// compressed: a pause longer than GAP_CAP between two lines (waiting on a rate limit, say) counts as GAP_CAP,
// then the whole run plays `speed` times faster.
const GAP_CAP = 15_000;
const TICK = 250;

export interface Replay {
  lines: Activity[];  // the lines replayed so far
  now: number;        // the recorded time the replay has reached (ms), for "is this step still working"
  speed: number;      // recorded seconds per replayed second
  replayMs: number;   // how long the whole replay takes
  progress: number;   // 0..1
  recordedMs: number; // how long the run really took, first line to last
}

export function useReplay(all: Activity[], on: boolean, speed = 10): Replay | null {
  const timeline = useMemo(() => {
    const t = all.map((l) => new Date(l.created_at).getTime());
    const c: number[] = [];
    t.forEach((v, i) => c.push(i === 0 ? 0 : c[i - 1] + Math.min(Math.max(0, v - t[i - 1]), GAP_CAP)));
    return { t, c, total: c.at(-1) ?? 0 };
  }, [all]);
  const started = useRef(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!on) return;
    started.current = performance.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed(performance.now() - started.current), TICK);
    return () => clearInterval(id);
  }, [on, all]);

  if (!on || !all.length) return null;
  const { t, c, total } = timeline;
  const pos = elapsed * speed; // position on the compressed timeline
  // Lines whose compressed time has been reached (binary search: runs can have thousands of lines).
  let lo = 0, hi = c.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (c[mid] <= pos) lo = mid + 1; else hi = mid; }
  const count = Math.max(1, lo);
  const k = count - 1;
  const now = t[k] + Math.min(pos - c[k], GAP_CAP);
  return { lines: all.slice(0, count), now, speed, replayMs: total / speed, progress: total ? Math.min(1, pos / total) : 1,
    recordedMs: (t.at(-1) ?? 0) - (t[0] ?? 0) };
}
