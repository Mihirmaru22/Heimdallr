import { lazy, Suspense, type ComponentProps } from "react";

// three.js is the biggest dependency, so the lens loads in its own chunk after the page is up.
const Lens = lazy(() => import("./Lens"));

export default function LazyLens(props: ComponentProps<typeof Lens>) {
  return (
    <Suspense fallback={<div className={`lens lens-placeholder ${props.className ?? ""}`} />}>
      <Lens {...props} />
    </Suspense>
  );
}
