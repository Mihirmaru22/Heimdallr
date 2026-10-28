import { useEffect, useRef } from "react";
import { GlobeScene, type GlobeSignal } from "../geo/scene";

export type { GlobeSignal };

// React wrapper for the research globe. Signals are handed over by id, so the scene sees each step once.
// Steps older than a few seconds when they arrive (a page opened mid-run) are applied quietly, without
// beams and ripples, so opening a run does not replay its whole history as fireworks.
export default function Globe({ signals, demo = false, focus, labels = true, className = "" }:
  { signals?: GlobeSignal[]; demo?: boolean; focus?: string[]; labels?: boolean; className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<GlobeScene | null>(null);
  const seen = useRef(0);

  useEffect(() => {
    let s: GlobeScene;
    try {
      s = new GlobeScene(host.current!, { demo, labels });
    } catch {
      host.current!.classList.add("globe-fallback");
      return;
    }
    scene.current = s;
    return () => { s.dispose(); scene.current = null; seen.current = 0; };
  }, [demo, labels]);

  const focusKey = (focus ?? []).join(",");
  useEffect(() => { scene.current?.setFocus(focusKey ? focusKey.split(",") : []); }, [focusKey]);

  useEffect(() => {
    const s = scene.current;
    if (!s || !signals) return;
    const now = Date.now();
    const unseen = signals.filter((sig) => sig.id > seen.current);
    unseen.forEach((sig, i) => {
      seen.current = sig.id;
      const fresh = !sig.at || now - new Date(sig.at).getTime() < 8000;
      // A burst of many fresh lines (a catch-up page) animates only its last few.
      s.feed(sig, fresh && i >= unseen.length - 24);
    });
    s.render();
  }, [signals]);

  return <div ref={host} className={`globe ${className}`} />;
}
