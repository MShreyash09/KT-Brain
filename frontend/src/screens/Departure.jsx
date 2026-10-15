import { useState } from "react";
import { Cypher, Header, Item, Pill, data, first } from "../ui.jsx";

const CASES = [
  { id: "arjun", name: "Arjun" },
  { id: "priya", name: "Priya" },
  { id: "arjun+priya", name: "Both" },
];

export default function Departure({ open }) {
  const [c, setC] = useState("arjun+priya");
  const run = data.dry_runs[c];
  const n = (id) => data.dry_runs[id].agenda.length;
  const who = c.split("+").map(first).join(" and ");

  return (
    <>
      <Header title="Simulate a departure">
        Arjun and Priya resign on Sep 15. KT Brain copies the workspace graph (<code>GRAPH.COPY</code>), removes the
        leavers from the copy, and lists what nobody else knows. That list is the KT agenda. The real graph is not touched.
      </Header>

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
        {run.agenda.map((item) => (
          <Item key={item} item={item} open={open}>
            {run.combination_risk.includes(item) && <Pill tone="warn">only if both leave</Pill>}
            {run.weak_backup[item] && <Pill tone="warn">weak backup: {first(run.weak_backup[item])}</Pill>}
          </Item>
        ))}
      </section>

      {c === "arjun+priya" && (
        <p className="callout warn">
          Arjun alone takes {n("arjun")}, Priya alone takes {n("priya")}, but together they take {n("arjun+priya")}, not{" "}
          {n("arjun") + n("priya")}. {run.combination_risk.length} items were safe only while one of them stayed. Each
          resignation looked fine on its own.
        </p>
      )}

      <Cypher>{`
GRAPH.COPY ws_tiffinbox dryrun_42
// on the copy:
MATCH (p:Person) WHERE p.id IN $leavers SET p.active = false
MATCH (l:Person)-[:KNOWS]->(k) WHERE l.id IN $leavers
  AND (k:File OR (k:Decision AND k.status = 'active'))
  AND NOT EXISTS { MATCH (o:Person {active: true})-[:KNOWS]->(k) }
RETURN DISTINCT coalesce(k.id, k.path) AS agenda_item`}</Cypher>
    </>
  );
}
