import { useState } from "react";
import { Cypher, Header, Item, Pill, data, first } from "../ui.jsx";

const CASES = [
  { id: "arjun", name: "Arjun" },
  { id: "priya", name: "Priya" },
  { id: "arjun+priya", name: "Both" },
];

// the toggle, agenda and combination callout; the landing page shows the first `limit` items, combination risk first
export function DryRun({ open, limit, more }) {
  const [c, setC] = useState("arjun+priya");
  const run = data.dry_runs[c];
  const n = (id) => data.dry_runs[id].agenda.length;
  const who = c.split("+").map(first).join(" and ");
  const risky = (item) => run.combination_risk.includes(item);
  const items = limit ? [...run.agenda].sort((a, b) => risky(b) - risky(a)).slice(0, limit) : run.agenda;
  const weak = limit ? [] : Object.keys(run.weak_backup);

  return (
    <>
      <div className="segmented" role="group" aria-label="Who leaves">
        {CASES.map((x) => (
          <button key={x.id} aria-pressed={c === x.id} onClick={() => setC(x.id)}>{x.name}</button>
        ))}
      </div>

      <section className="card">
        <div className="big">
          <span className="big-num risk-text">{run.agenda.length}</span>
          <span>things leave with {who}, with nobody else who knows them</span>
        </div>
        {items.map((item) => (
          <Item key={item} item={item} open={open}>
            {risky(item) && <Pill tone="warn">only if both leave</Pill>}
          </Item>
        ))}
        {items.length < run.agenda.length && more?.(run.agenda.length - items.length)}
      </section>

      {weak.length > 0 && (
        <section className="card">
          <h2>Covered by one person who touched it once <span className="count">{weak.length}</span></h2>
          {weak.map((item) => (
            <Item key={item} item={item} open={open}>
              <Pill tone="warn">weak backup: {first(run.weak_backup[item])}</Pill>
            </Item>
          ))}
        </section>
      )}

      {c === "arjun+priya" && (
        <p className="callout warn">
          Arjun alone takes {n("arjun")}, Priya alone takes {n("priya")}, but together they take {n("arjun+priya")}, not{" "}
          {n("arjun") + n("priya")}. {run.combination_risk.length} items were safe only while one of them stayed. Each
          resignation looked fine on its own.
        </p>
      )}
    </>
  );
}

export default function Departure({ open }) {
  return (
    <>
      <Header title="Simulate a departure">
        Arjun and Priya resign on Sep 15. KT Brain copies the workspace graph (<code>GRAPH.COPY</code>), removes the
        leavers from the copy, and lists what nobody else knows. That list is the KT agenda. The real graph is not touched.
      </Header>

      <DryRun open={open} />

      <Cypher>{`
GRAPH.COPY ws_tiffinbox dryrun_<id>    // the workspace graph is never touched
// on the copy:
MATCH (p:Person) WHERE p.id IN $leavers SET p.active = false
MATCH (l:Person)-[:KNOWS]->(k) WHERE l.id IN $leavers
  AND (k:File OR (k:Decision AND k.status = 'active'))
WITH DISTINCT k
MATCH (p:Person)-[:KNOWS]->(k)
WITH k, sum(CASE WHEN p.id IN $leavers THEN 1 ELSE 0 END) AS leavers_knowing,
     sum(CASE WHEN p.active THEN 1 ELSE 0 END) AS backups
WHERE backups = 0
RETURN coalesce(k.id, k.path) AS item, leavers_knowing > 1 AS combination_risk`}</Cypher>
    </>
  );
}
