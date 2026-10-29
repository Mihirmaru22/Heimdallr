import type { ReactElement } from "react";
import { useTheme, type ThemeChoice } from "../theme";
import { Monitor, Moon, Sun } from "./icons";

export default function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const options: [ThemeChoice, string, ReactElement][] = [
    ["light", "Light", <Sun key="l" />], ["system", "Match system", <Monitor key="s" />], ["dark", "Dark", <Moon key="d" />]];
  return (
    <div className="segmented theme-switch" role="group" aria-label="Colour theme">
      {options.map(([value, label, icon]) => (
        <button key={value} type="button" aria-pressed={theme === value} title={label} aria-label={label}
          onClick={() => setTheme(value)}>{icon}</button>))}
    </div>
  );
}
