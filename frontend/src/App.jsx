import { useEffect, useState } from "react";
import { data, fmt } from "./ui.jsx";
import Landing from "./screens/Landing.jsx";
import Team from "./screens/Team.jsx";
import Radar from "./screens/Radar.jsx";
import Departure from "./screens/Departure.jsx";
import Why from "./screens/Why.jsx";
import Handover from "./screens/Handover.jsx";
import Ask from "./screens/Ask.jsx";

const STEPS = [
  { id: "team", name: "Team", Screen: Team },
  { id: "radar", name: "Radar", Screen: Radar },
  { id: "departure", name: "Departure", Screen: Departure },
  { id: "why", name: "Why", Screen: Why },
  { id: "handover", name: "Handover", Screen: Handover },
  { id: "ask", name: "Ask", Screen: Ask },
];

const fromHash = () => location.hash.replace("#/", "") || "home";

function ThemeToggle() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("theme", theme); } catch { /* private mode: theme just isn't remembered */ }
  }, [theme]);
  const dark = theme === "dark";
  return (
    <button className="icon-btn" onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} title={dark ? "Light theme" : "Dark theme"}>
      {dark ? (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}

export default function App() {
  const [view, setView] = useState(fromHash);
  const [focus, setFocus] = useState("D1"); // decision shown on the Why step
  useEffect(() => {
    const onHash = () => setView(fromHash());
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const go = (id) => {
    location.hash = `/${id}`;
    scrollTo(0, 0);
  };
  const open = (decision) => { setFocus(decision); go("why"); };

  const i = STEPS.findIndex((s) => s.id === view);
  const step = STEPS[i];
  const next = STEPS[i + 1];

  return (
    <>
      <div className="topbar">
        <a className="brand" href="#/">
          <span className="logo" aria-hidden="true">◆</span> KT Brain
        </a>
        {step && (
          <span className="ws">
            {data.workspace.name} <span className="dot">·</span> <span className="muted">synthetic data</span>
            <span className="dot hide-sm">·</span>
            <span className="muted hide-sm">snapshot {fmt(step.id === "handover" ? "2026-09-30" : data.workspace.snapshot)}</span>
          </span>
        )}
        <ThemeToggle />
      </div>

      {!step ? (
        <Landing start={() => go("team")} />
      ) : (
        <div className="shell">
          <nav className="steps" aria-label="Demo steps">
            {STEPS.map((s, n) => (
              <a key={s.id} href={`#/${s.id}`} aria-current={s.id === view ? "page" : undefined}>
                <span className="n">{n + 1}</span> {s.name}
              </a>
            ))}
          </nav>
          <main className="content">
            <step.Screen open={open} focus={focus} setFocus={setFocus} />
            {next && (
              <div className="next">
                <button className="btn primary" onClick={() => go(next.id)}>Next: {next.name} →</button>
              </div>
            )}
          </main>
        </div>
      )}
    </>
  );
}
