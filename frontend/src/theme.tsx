import { useEffect, useState } from "react";
import { localStorageGet, localStorageSet } from "./session";

// Light, dark or follow the system. The choice is remembered per browser and applied as html[data-theme];
// "system" removes the attribute so the prefers-color-scheme tokens in styles.css take over.

export type ThemeChoice = "system" | "light" | "dark";

export function applyStoredTheme() {
  apply((localStorageGet("wd_theme") as ThemeChoice | null) ?? "system");
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function useTheme(): [ThemeChoice, (t: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(
    () => (localStorageGet("wd_theme") as ThemeChoice | null) ?? "system");
  useEffect(() => { apply(choice); localStorageSet("wd_theme", choice); }, [choice]);
  return [choice, setChoice];
}

// True when the page is currently drawn dark, whichever way that was decided.
export function isDark(): boolean {
  const t = document.documentElement.getAttribute("data-theme");
  if (t) return t === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}
