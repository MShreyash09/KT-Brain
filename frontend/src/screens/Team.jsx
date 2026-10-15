import { useState } from "react";
import { Cypher, Header, Item, Pill, Score, useData } from "../ui.jsx";
import KnowsGraph from "./KnowsGraph.jsx";

export default function Team({ open }) {
  const data = useData();
  const { first, status } = data;
  const [sel, setSel] = useState("arjun");
  const knows = data.knows.filter((k) => k.person === sel);
  const max = Math.max(...data.knows.map((k) => k.score));
  const p = data.people.find((p) => p.id === sel);

  return (
    <>
      <Header title="Who knows what">
        Every commit, review, ticket, chat post, doc and AI session adds evidence. KT Brain turns it into a weighted{" "}
        <code>KNOWS</code> edge from a person to a file or decision. Pick a person.
      </Header>

      <div className="people">
        {data.people.map((p) => {
          const s = status(p);
          const n = data.knows.filter((k) => k.person === p.id).length;
          const only = data.radar.filter((r) => r.person === p.id).length;
          return (
            <button key={p.id} className={`person ${p.id === sel ? "selected" : ""}`} onClick={() => setSel(p.id)}
              aria-pressed={p.id === sel}>
              <span className="avatar" aria-hidden="true">{p.name.split(" ").map((w) => w[0]).join("")}</span>
              <span className="pname">{p.name}</span>
              <span className="muted small">{p.role.split(" (")[0]}</span>
              <Pill tone={s.tone}>{s.text}</Pill>
              <span className="small">knows {n}{only ? <> · <b className="risk-text">only one: {only}</b></> : null}</span>
            </button>
          );
        })}
      </div>

      <KnowsGraph sel={sel} onPerson={setSel} open={open} />

      <section className="card">
        <h2>{first(sel)} knows</h2>
        {knows.length ? (
          knows.map((k) => (
            <Item key={k.item} item={k.item} open={open}>
              <Score value={k.score} max={max} />
            </Item>
          ))
        ) : (
          <p className="muted">
            Nothing yet: {first(sel)} joins on {p.joined}, after this snapshot. See step 5.
          </p>
        )}
      </section>

      <Cypher>{`
// derived from raw edges, e.g. for files:
MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:CHANGED]->(k:File)
WITH p, k, CASE WHEN c.message =~ $trivial THEN 0.05 ELSE 1.0 END AS w, c.ts AS ts
WITH p, k, sum(w * 0.5 ^ (($now - ts) / ($half_life * 86400.0))) AS score
MERGE (p)-[e:KNOWS]->(k) SET e.score = e.score + score
// ...plus reviews, and sources that RECORD a decision; edges with score <= 0.3 are dropped`}</Cypher>
    </>
  );
}
