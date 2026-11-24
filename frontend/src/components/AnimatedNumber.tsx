import { useEffect, useRef, useState } from "react";
import { animate, useReducedMotion } from "motion/react";

// A number that counts up to its new value instead of jumping.
export function AnimatedNumber({ value }: { value: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduce) { setShown(value); from.current = value; return; }
    const ctl = animate(from.current, value, { duration: 0.8, ease: [0.2, 0.75, 0.15, 1], onUpdate: (v) => setShown(Math.round(v)) });
    from.current = value;
    return () => ctl.stop();
  }, [value, reduce]);
  return <>{shown.toLocaleString()}</>;
}
