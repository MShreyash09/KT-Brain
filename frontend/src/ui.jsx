// Shared data + small components. The data is a snapshot of the real graph (see design.md); the API replaces it later.
import data from "./data/tiffinbox.json";

export { data };
export const person = Object.fromEntries(data.people.map((p) => [p.id, p]));
export const first = (id) => person[id]?.name.split(" ")[0] ?? id;
export const isDecision = (item) => item in data.decisions;
export const label = (item) => data.decisions[item]?.what ?? item;
export const fmt = (day) =>
  day ? new Date(day + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }) : "";

// the decision a why-trace starts from: the item itself, or the active decision about a file
export function whyFor(item) {
  if (isDecision(item)) return data.traces[item] ? item : null;
  const d = Object.values(data.decisions).find((d) => d.status === "active" && d.about.includes(item));
  return d ? d.id : null;
}

export function status(p) {
  if (p.joined > data.workspace.snapshot) return { text: `Joins ${fmt(p.joined)}`, tone: "accent" };
  if (p.last_day) return { text: `Leaving ${fmt(p.last_day)}`, tone: "risk" };
  return { text: "Active", tone: "muted" };
}

export const Pill = ({ tone = "muted", children }) => <span className={`pill ${tone}`}>{children}</span>;

const KIND = { Decision: "Decision", File: "File", PR: "PR", Ticket: "Ticket", Thread: "Chat",
  AgentSession: "AI session", Doc: "Doc", Research: "Research", Incident: "Incident", External: "External" };
export const Kind = ({ kind }) => <span className={`kind k-${kind}`}>{KIND[kind] ?? kind}</span>;

// one agenda / knowledge row; clicking opens its why-trace when there is one
export function Item({ item, open, children }) {
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
        {data.decisions[item]?.status === "superseded" && <Pill>superseded</Pill>}
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
