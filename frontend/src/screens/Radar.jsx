import { Cypher, Header, Item, Pill, Score, useData } from "../ui.jsx";

export default function Radar({ open }) {
  const data = useData();
  const { first, status } = data;
  const max = Math.max(...data.radar.map((r) => r.score));
  const groups = data.people
    .map((p) => ({ p, rows: data.radar.filter((r) => r.person === p.id) }))
    .filter((g) => g.rows.length);

  return (
    <>
      <Header title={`${data.radar.length} things only one person knows`}>
        Bus factor 1: active decisions and files that exactly one active person knows. This is visible while they
        are still here, not after they leave.
      </Header>

      {groups.map(({ p, rows }) => {
        const s = status(p);
        return (
          <section key={p.id} className={`card ${s.tone === "risk" ? "at-risk" : ""}`}>
            <h2>
              {first(p.id)} <span className="count">{rows.length}</span> <Pill tone={s.tone}>{s.text}</Pill>
            </h2>
            {rows.map((r) => (
              <Item key={r.item} item={r.item} open={open}>
                <Score value={r.score} max={max} />
              </Item>
            ))}
          </section>
        );
      })}

      <Cypher>{`
MATCH (p:Person {active: true})-[e:KNOWS]->(k)
WHERE k:File OR (k:Decision AND k.status = 'active')
WITH k, collect(p.id) AS knowers, max(e.score) AS score
WHERE size(knowers) = 1
RETURN coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, knowers[0] AS only_knower, score`}</Cypher>
    </>
  );
}
