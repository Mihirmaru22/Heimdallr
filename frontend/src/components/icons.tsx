import type { ReactNode } from "react";

// A small hand-drawn stroke icon set (24px grid, 1.6 stroke), so the app needs no icon library.

function Svg({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className="ico">
      {children}
    </svg>
  );
}

type P = { size?: number };
export const Sun = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Svg>;
export const Moon = (p: P) => <Svg {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></Svg>;
export const Monitor = (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></Svg>;
export const Plus = (p: P) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>;
export const Arrow = (p: P) => <Svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Svg>;
export const Back = (p: P) => <Svg {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></Svg>;
export const Check = (p: P) => <Svg {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></Svg>;
export const X = (p: P) => <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>;
export const External = (p: P) => <Svg {...p}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>;
export const Download = (p: P) => <Svg {...p}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></Svg>;
export const Search = (p: P) => <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></Svg>;
export const Spark = (p: P) => <Svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5" /></Svg>;
export const Stop = (p: P) => <Svg {...p}><rect x="6" y="6" width="12" height="12" rx="2" /></Svg>;
export const Retry = (p: P) => <Svg {...p}><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" /></Svg>;
export const Out = (p: P) => <Svg {...p}><path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l4-4-4-4M14 12H4" /></Svg>;
export const Folder = (p: P) => <Svg {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></Svg>;
export const Sliders = (p: P) => <Svg {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></Svg>;
export const Table = (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" /></Svg>;
export const Globe = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" /></Svg>;
