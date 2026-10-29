import { lazy, Suspense, type ComponentProps } from "react";

// three.js and the map data are the biggest dependencies, so the globe loads in its own chunk.
const Globe = lazy(() => import("./Globe"));

export default function LazyGlobe(props: ComponentProps<typeof Globe>) {
  return (
    <Suspense fallback={<div className={`globe globe-fallback ${props.className ?? ""}`} />}>
      <Globe {...props} />
    </Suspense>
  );
}
