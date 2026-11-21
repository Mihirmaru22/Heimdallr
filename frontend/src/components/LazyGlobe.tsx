import { lazy, Suspense, useEffect, useState, type ComponentProps } from "react";

// three.js and the globe are the biggest dependencies, so they load in their own chunk, and only once the
// page has painted and the browser is idle, so the text and controls come first.
const Globe = lazy(() => import("./Globe"));

export default function LazyGlobe(props: ComponentProps<typeof Globe>) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const w = window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setReady(true), { timeout: 1200 });
      return () => w.cancelIdleCallback?.(id);
    }
    const t = setTimeout(() => setReady(true), 300);
    return () => clearTimeout(t);
  }, []);
  const fallback = <div className={`globe globe-fallback ${props.className ?? ""}`} />;
  if (!ready) return fallback;
  return <Suspense fallback={fallback}><Globe {...props} /></Suspense>;
}
