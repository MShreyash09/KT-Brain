import { Cypher, Header, Kind, Pill, fmt, useData } from "../ui.jsx";

function where(ref) {
  const [kind, id] = [ref.slice(0, ref.indexOf(":")), ref.slice(ref.indexOf(":") + 1)];
  if (kind === "pr") return `#${id}`;
  if (kind === "thread") return `#${id.split("/")[1]}`;
  if (kind === "session") return "Claude Code";
  return id;
}

const Node = ({ kind, muted, children }) => (
  <li className={`node ${muted ? "muted-node" : ""}`}>
    <span className="dot-mark" aria-hidden="true" />
    <Kind kind={kind} />
    <div className="node-body">{children}</div>
  </li>
);

const Group = ({ title }) => <li className="group">{title}</li>;

// a decision and every path to its sources; the story and the dashboards both render it
export function Trace({ d, t }) {
  const { first } = useData();
  return (
    <>
      <ol className="trace card">
        {d.about.map((f) => <Node key={f} kind="File"><code>{f}</code></Node>)}
        <Node kind="Decision">
          <b>{d.id}</b> {d.what}
          <p className="muted">{d.why}</p>
          <blockquote>“{d.evidence}”</blockquote>
        </Node>

        <Group title="Recorded in" />
        {t.sources.map((s) => (
          <Node key={s.ref} kind={s.kind}>
            {s.title}
            <div className="meta">{where(s.ref)} · {fmt(s.at)} · {s.people.map(first).join(", ")}</div>
          </Node>
        ))}

        {t.supersedes.length > 0 && <Group title="Replaced" />}
        {t.supersedes.map((o) => [
          <Node key={o.id} kind="Decision" muted><b>{o.id}</b> {o.what}</Node>,
          ...o.incidents.map((i) => (
            <Node key={i.id} kind="Incident">
              {i.title}
              <div className="meta">{i.id} · {i.severity} · {fmt(i.at)} · caused by {o.id}</div>
            </Node>
          )),
        ])}

        {t.research.length > 0 && <Group title="Informed by" />}
        {t.research.map((r) => [
          <Node key={r.id} kind="Research">{r.title}<div className="meta">{r.doc}</div></Node>,
          ...r.cites.map((x) => (
            <Node key={x.url} kind="External">
              <a href={x.url} target="_blank" rel="noreferrer">{x.title} ↗</a>
              <div className="meta">{x.publisher} · {x.date}</div>
            </Node>
          )),
        ])}

        {t.insights.length > 0 && <Group title="Justified by" />}
        {t.insights.map((i) => (
          <Node key={i.id} kind="Research">{i.text}<div className="meta">{i.research}</div></Node>
        ))}
      </ol>

      {(t.patterns.length > 0 || t.features.length > 0) && (
        <p className="chips">
          {t.patterns.map((p) => <Pill key={p} tone="accent">Pattern: {p}</Pill>)}
          {t.features.map((f) => <Pill key={f} tone="accent">Feature: {f}</Pill>)}
        </p>
      )}
    </>
  );
}

export default function Why({ focus, setFocus }) {
  const data = useData();
  const d = data.decisions[focus];
  const t = data.traces[focus];
  const options = Object.values(data.decisions).filter((x) => x.status === "active");

  return (
    <>
      <Header title="Why is it like this?">
        Every answer is a path through the graph, with sources. Pick a decision, or click any row on the other steps.
      </Header>

      <label className="picker">
        <span className="muted small">Decision</span>
        <select value={focus} onChange={(e) => setFocus(e.target.value)}>
          {options.map((x) => <option key={x.id} value={x.id}>{x.id} · {x.what}</option>)}
        </select>
      </label>

      <Trace d={d} t={t} />

      <Cypher>{`
MATCH (d:Decision {id: $id})
OPTIONAL MATCH (d)-[:ABOUT]->(f:File)
OPTIONAL MATCH (s:Source)-[:RECORDS]->(d)
OPTIONAL MATCH (d)-[:SUPERSEDES]->(old)<-[:CAUSED_BY]-(i:Incident)
OPTIONAL MATCH (d)-[:INFORMED_BY]->(r:Research)-[:CITES]->(x:ExternalSource)
OPTIONAL MATCH (n:Insight)-[:JUSTIFIES]->(d)
RETURN d, collect(DISTINCT f), collect(DISTINCT s), collect(DISTINCT i), collect(DISTINCT x), collect(DISTINCT n)`}</Cypher>
    </>
  );
}
