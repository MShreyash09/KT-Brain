import { Cypher, Header, Item, Pill, Score, useData } from "../ui.jsx";

// How much of the stack depends on the item's service: PageRank over DEPENDS_ON, 1.0 = the most depended-on service
export const Blast = ({ value }) => value > 0 && (
  <span title="Blast radius: PageRank of the item's service over DEPENDS_ON, relative to the service everything else depends on">
    <Pill tone={value >= 0.75 ? "risk" : "muted"}>blast {value.toFixed(2)}</Pill>
  </span>
);

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
        are still here, not after they leave. Each item is ranked by its blast radius: FalkorDB's PageRank over which
        services depend on which, so infra, which everything runs on, comes first.
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
                <Blast value={r.blast} />
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
RETURN coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, knowers[0] AS only_knower, score,
       [(k)-[:ABOUT|PART_OF*1..2]->(s:Service) | s.id] AS services

// blast radius of each service
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.id, score`}</Cypher>
    </>
  );
}
