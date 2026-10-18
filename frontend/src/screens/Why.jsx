import { useEffect, useState } from "react";
import { Header, Kind, Pill, fmt, useData } from "../ui.jsx";

function where(ref) {
  const [kind, id] = [ref.slice(0, ref.indexOf(":")), ref.slice(ref.indexOf(":") + 1)];
  if (kind === "pr") return `#${id}`;
  if (kind === "thread") return `#${id.split("/")[1]}`;
  if (kind === "session") return "Claude Code";
  return id;
}

// The patterns behind the why-trace (graph.py DECISIONS and TRACE_*); each row lights up the one that reached it
const PATTERNS = [
  "MATCH (f:File)<-[:ABOUT]-(d:Decision {id: $id})",
  "MATCH (s:Source)-[:RECORDS]->(d)",
  "MATCH (d)-[:SUPERSEDES]->(o:Decision)<-[:CAUSED_BY]-(i:Incident)",
  "MATCH (d)-[:INFORMED_BY]->(r:Research)-[:CITES]->(x:ExternalSource)",
  "MATCH (r:Research)-[:FOUND]->(n:Insight)-[:JUSTIFIES]->(d)",
];
const STEP_MS = 450;
const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const Node = ({ kind, muted, edge, hop, state, children }) => (
  <li className={`node ${muted ? "muted-node" : ""} ${state}`}>
    <span className="dot-mark" aria-hidden="true" />
    <code className="edge">{edge}<span className="hop">hop {hop}</span></code>
    <Kind kind={kind} />
    <div className="node-body">{children}</div>
  </li>
);

const Group = ({ title, state }) => <li className={`group ${state}`}>{title}</li>;

// a decision and every path to its sources, revealed one hop at a time; the story and the dashboards both render it
export function Trace({ d, t }) {
  const { first } = useData();
  const h = d.about.length ? 1 : 0; // hops are counted from the file when the decision is about one
  const rows = [
    ...d.about.map((f) => ({ key: f, kind: "File", line: 0, edge: "start", hop: 0, body: <code>{f}</code> })),
    { key: d.id, kind: "Decision", line: 0, edge: h ? `${d.about[0].split("/").pop()} <-[:ABOUT]-` : "start", hop: h, body: (
      <>
        <b>{d.id}</b> {d.what}
        <p className="muted">{d.why}</p>
        <blockquote>“{d.evidence}”</blockquote>
      </>
    ) },

    { group: "Recorded in" },
    ...t.sources.map((s) => ({ key: s.ref, kind: s.kind, line: 1, edge: `${d.id} <-[:RECORDS]-`, hop: h + 1, body: (
      <>
        {s.title}
        <div className="meta">{where(s.ref)} · {fmt(s.at)} · {s.people.map(first).join(", ")}</div>
      </>
    ) })),

    t.supersedes.length > 0 && { group: "Replaced" },
    ...t.supersedes.flatMap((o) => [
      { key: o.id, kind: "Decision", muted: true, line: 2, edge: `${d.id} -[:SUPERSEDES]->`, hop: h + 1,
        body: <><b>{o.id}</b> {o.what}</> },
      ...o.incidents.map((i) => ({ key: i.id, kind: "Incident", line: 2, edge: `${o.id} <-[:CAUSED_BY]-`, hop: h + 2, body: (
        <>
          {i.title}
          <div className="meta">{i.id} · {i.severity} · {fmt(i.at)} · caused by {o.id}</div>
        </>
      ) })),
    ]),

    t.research.length > 0 && { group: "Informed by" },
    ...t.research.flatMap((r) => [
      { key: r.id, kind: "Research", line: 3, edge: `${d.id} -[:INFORMED_BY]->`, hop: h + 1,
        body: <>{r.title}<div className="meta">{r.doc}</div></> },
      ...r.cites.map((x) => ({ key: x.url, kind: "External", line: 3, edge: `${r.id} -[:CITES]->`, hop: h + 2, body: (
        <>
          <a href={x.url} target="_blank" rel="noreferrer">{x.title} ↗</a>
          <div className="meta">{x.publisher} · {x.date}</div>
        </>
      ) })),
    ]),

    t.insights.length > 0 && { group: "Justified by" },
    ...t.insights.map((i) => ({ key: i.id, kind: "Research", line: 4, edge: `${d.id} <-[:JUSTIFIES]-`, hop: h + 1,
      body: <>{i.text}<div className="meta">{i.research}</div></> })),
  ].filter(Boolean);

  // a group heading carries the number of the row after it, so it appears together with that row
  let k = 0;
  const numbered = rows.map((r) => (r.group ? { ...r, i: k + 1 } : { ...r, i: ++k }));
  const n = k;

  const [at, setAt] = useState(1); // rows shown so far
  useEffect(() => setAt(reduced() ? Infinity : 1), [d.id]);
  useEffect(() => {
    if (at >= n) return;
    const id = setTimeout(() => setAt(at + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [at, n]);
  const live = at < n ? numbered.find((r) => !r.group && r.i === at)?.line : -1;
  const state = (r) => (r.i > at ? "off" : !r.group && r.i === at && at < n ? "now" : "");

  return (
    <>
      <div className="hop-query card">
        <div className="hop-head">
          <span className="muted small">Each row is one hop FalkorDB matched, with the read-only pattern that reached it</span>
          <button className="chip" onClick={() => setAt(1)}>Replay</button>
        </div>
        <pre>{PATTERNS.map((p, j) => <span key={p} className={j === live ? "now" : undefined}>{p}</span>)}</pre>
      </div>

      <ol className="trace card">
        {numbered.map((r) => r.group
          ? <Group key={r.group} title={r.group} state={state(r)} />
          : <Node key={r.key} kind={r.kind} muted={r.muted} edge={r.edge} hop={r.hop} state={state(r)}>{r.body}</Node>)}
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
    </>
  );
}
