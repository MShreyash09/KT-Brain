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
  const value = useMemo(() => withHelpers(data), [data]);
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
