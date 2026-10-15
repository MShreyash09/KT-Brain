import { useEffect, useState } from "react";
import { DataProvider, api, fmt, go } from "./ui.jsx";
import Landing from "./screens/Landing.jsx";
import Team from "./screens/Team.jsx";
import Radar from "./screens/Radar.jsx";
import Departure from "./screens/Departure.jsx";
import Why from "./screens/Why.jsx";
import Handover from "./screens/Handover.jsx";
import Ask from "./screens/Ask.jsx";
import { Login, Register } from "./dash/Auth.jsx";
import Admin from "./dash/Admin.jsx";
import Member from "./dash/Member.jsx";

const STEPS = [
  { id: "team", name: "Team", Screen: Team },
  { id: "radar", name: "Radar", Screen: Radar },
  { id: "departure", name: "Departure", Screen: Departure },
  { id: "why", name: "Why", Screen: Why },
  { id: "handover", name: "Handover", Screen: Handover },
  { id: "ask", name: "Ask", Screen: Ask },
];

// "#/admin/why/D1" -> ["admin", "why", "D1"]
const fromHash = () => (location.hash.replace(/^#\/?/, "") || "home").split("/").map(decodeURIComponent);

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

// the public TiffinBox story: landing page + six steps, read from /api/workspace
function Story({ view, demo }) {
  const [focus, setFocus] = useState("D1"); // decision shown on the Why step
  const open = (decision) => { setFocus(decision); go("why"); };
  const i = STEPS.findIndex((s) => s.id === view);
  const step = STEPS[i];
  const next = STEPS[i + 1];
  if (!demo) return <p className="page-msg muted">Loading the TiffinBox graph…</p>;
  return (
    <DataProvider data={demo}>
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
    </DataProvider>
  );
}

export default function App() {
  const [route, setRoute] = useState(fromHash);
  const [user, setUser] = useState(undefined); // undefined = still checking the session cookie
  const [demo, setDemo] = useState(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    const onHash = () => setRoute(fromHash());
    addEventListener("hashchange", onHash);
    api("auth/me").then(setUser).catch(() => setDown(true));
    return () => removeEventListener("hashchange", onHash);
  }, []);

  const [view, ...rest] = route;
  const story = view === "home" || STEPS.some((s) => s.id === view);
  useEffect(() => {
    if (story && !demo) api("workspace").then(setDemo).catch(() => setDown(true));
  }, [story, demo]);

  const signOut = async () => {
    await api("auth/logout", {});
    setUser(null);
    go("login");
  };
  const home = user ? (user.role === "admin" ? "admin" : "me") : "login";

  let page;
  if (down) page = <p className="page-msg">The KT Brain API is not running. Start it with: <code>cd backend && uv run uvicorn app:app</code></p>;
  else if (story) page = <Story view={view} demo={demo} />;
  else if (user === undefined) page = null;
  else if (view === "login") page = <Login onIn={(u) => { setUser(u); go(u.role === "admin" ? "admin" : "me"); }} />;
  else if (view === "register") page = <Register onIn={(u) => { setUser(u); go("admin"); }} />;
  else if (!user) page = <Login onIn={(u) => { setUser(u); go(...route); }} />;
  else if (view === "admin" && user.role === "admin") page = <Admin user={user} path={rest} />;
  else if (view === "me" && user.person) page = <Member user={user} path={rest} />;
  else page = <p className="page-msg">Nothing here. <a href={`#/${home}`}>Go to your dashboard</a></p>;

  return (
    <>
      <div className="topbar">
        <a className="brand" href="#/">
          <span className="logo" aria-hidden="true">◆</span> KT Brain
        </a>
        <span className="ws">
          {story && view !== "home" && demo && (
            <>
              {demo.workspace.name} <span className="dot">·</span> <span className="muted">synthetic data</span>
              <span className="dot hide-sm">·</span>
              <span className="muted hide-sm">snapshot {fmt(view === "handover" ? "2026-09-30" : demo.workspace.snapshot)}</span>
            </>
          )}
          {!story && user && <span className="muted">{user.company_name}</span>}
        </span>
        <nav className="account">
          {user ? (
            <>
              {story && <a href={`#/${home}`}>Dashboard</a>}
              {user.role === "admin" && user.person && view === "admin" && <a href="#/me">My brain</a>}
              {user.role === "admin" && view === "me" && <a href="#/admin">Admin</a>}
              <span className="muted hide-sm">{user.name}</span>
              <button className="btn" onClick={signOut}>Sign out</button>
            </>
          ) : user === null && view !== "login" ? (
            <a className="btn" href="#/login">Sign in</a>
          ) : null}
        </nav>
        <ThemeToggle />
      </div>
      {page}
    </>
  );
}
