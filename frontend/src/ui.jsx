// Shared data + small components. Each view (the public TiffinBox story, the admin dashboard, a member's brain) puts
// its own graph data in <DataCtx>; `useData()` returns it with the helpers below bound to it.
import { createContext, useContext, useMemo } from "react";

export const DataCtx = createContext(null);
export const fmt = (day) =>
  day ? new Date(day + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }) : "";

export function withHelpers(data) {
  const person = Object.fromEntries(data.people.map((p) => [p.id, p]));
  const isDecision = (item) => item in data.decisions;
  return {
    ...data,
    person,
    isDecision,
    first: (id) => person[id]?.name.split(" ")[0] ?? id,
    label: (item) => data.decisions[item]?.what ?? item,
    // the decision a why-trace starts from: the item itself, or the active decision about a file
    whyFor(item) {
      if (isDecision(item)) return !data.traces || data.traces[item] ? item : null;
      const d = Object.values(data.decisions).find((d) => d.status === "active" && d.about.includes(item));
      return d ? d.id : null;
    },
    status(p) {
      if (p.joined > data.workspace.snapshot) return { text: `Joins ${fmt(p.joined)}`, tone: "accent" };
      if (p.active === false) return { text: p.last_day ? `Left ${fmt(p.last_day)}` : "Left", tone: "muted" };
      if (p.last_day) return { text: `Leaving ${fmt(p.last_day)}`, tone: "risk" };
      return { text: "Active", tone: "muted" };
    },
  };
}

export const useData = () => useContext(DataCtx);

export function DataProvider({ data, children }) {
  const value = useMemo(() => data && withHelpers(data), [data]); // null while loading: useData() returns null
  return <DataCtx.Provider value={value}>{children}</DataCtx.Provider>;
}

export const go = (...parts) => {
  location.hash = `/${parts.join("/")}`;
  scrollTo(0, 0);
};

// JSON fetch for the dashboards; throws the API's own error message
export async function api(path, body, method) {
  const res = await fetch(`/api/${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await res.json().catch(() => null);
  if (!res.ok) throw new Error(out?.detail ?? `Request failed (${res.status})`);
  return out;
}

export const Pill = ({ tone = "muted", children }) => <span className={`pill ${tone}`}>{children}</span>;

// stroke icons (24 × 24, Lucide-style); `name` picks the path
const ICONS = {
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  message: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  nodes: "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.6 13.5l6.8 4M15.4 6.5l-6.8 4",
  swap: "M16 3l4 4-4 4M20 7H4M8 21l-4-4 4-4M4 17h16",
  database: "M12 8c5 0 9-1.3 9-3s-4-3-9-3-9 1.3-9 3 4 3 9 3zM3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3",
  sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  userCheck: "M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M8.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM17 11l2 2 4-4",
  sparkle: "M12 3l1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z",
  target: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  branch: "M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  check: "M20 6L9 17l-5-5",
  arrow: "M5 12h14M12 5l7 7-7 7",
  zap: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  terminal: "M4 17l6-6-6-6M12 19h8",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
};
export const Icon = ({ name, size = 18 }) => (
  <svg className="icon" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={ICONS[name]} />
  </svg>
);

// shimmering placeholder lines while data is on its way (a sleeping Render instance can take ~30 s to wake)
export const Skeleton = ({ lines = 4 }) => (
  <div className="skeleton" role="status" aria-label="Loading">
    {Array.from({ length: lines }, (_, i) => <span key={i} />)}
  </div>
);

const KIND = { Decision: "Decision", File: "File", PR: "PR", Ticket: "Ticket", Thread: "Chat",
  AgentSession: "AI session", Doc: "Doc", Research: "Research", Incident: "Incident", External: "External" };
export const Kind = ({ kind }) => <span className={`kind k-${kind}`}>{KIND[kind] ?? kind}</span>;

// one agenda / knowledge row; clicking opens its why-trace when there is one
export function Item({ item, open, children }) {
  const { whyFor, isDecision, label, decisions } = useData();
  const why = whyFor(item);
  const body = (
    <>
      <Kind kind={isDecision(item) ? "Decision" : "File"} />
      {isDecision(item) ? (
        <span className="item-label"><b>{item}</b> {label(item)}</span>
      ) : (
        <code className="item-label">{item}</code>
      )}
      <span className="item-extra">
        {decisions[item]?.status === "superseded" && <Pill>superseded</Pill>}
        {decisions[item]?.status === "proposed" && <Pill tone="warn">proposed</Pill>}
        {children}
      </span>
    </>
  );
  return why && open ? (
    <button className="row clickable" onClick={() => open(why)} title="Open why-trace">{body}</button>
  ) : (
    <div className="row">{body}</div>
  );
}

export const Score = ({ value, max }) => (
  <span className="score" title={`KNOWS score ${value}`}>
    <span className="bar"><span style={{ width: `${Math.min(100, (value / max) * 100)}%` }} /></span>
    <span className="num">{value.toFixed(2)}</span>
  </span>
);

export const Cypher = ({ children }) => (
  <details className="cypher">
    <summary>Cypher</summary>
    <pre>{children.trim()}</pre>
  </details>
);

export const Header = ({ title, children }) => (
  <header className="step-head">
    <h1>{title}</h1>
    <p>{children}</p>
  </header>
);
