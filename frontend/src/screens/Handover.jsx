import { Cypher, Header, Item, Pill, data, first, fmt } from "../ui.jsx";

export default function Handover({ open }) {
  const h = data.handover;
  const covered = Object.entries(h.covered);
  const left = h.remaining.length;

  return (
    <>
      <Header title="Handover progress">
        Meera joins on Sep 22. Her KT session with Arjun and her first PRs add <code>LEARNED</code> and{" "}
        <code>KNOWS</code> edges. The KT is done when the counter hits zero, not when the call ends.
      </Header>

      <section className="card">
        <div className="big">
          <span className="big-num">{h.before} → <span className="risk-text">{left}</span></span>
          <span>items still known only by Arjun and Priya after Sep 30</span>
        </div>
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={h.before} aria-valuenow={covered.length}
          aria-label="Items handed over">
          <span style={{ width: `${(covered.length / h.before) * 100}%` }} />
        </div>
      </section>

      <div className="two-col">
        <section className="card">
          <h2>Covered by {first(h.learner)} <span className="count ok">{covered.length}</span></h2>
          {covered.map(([item, c]) => (
            <Item key={item} item={item} open={open}>
              <span className="meta">{c.via} · {fmt(c.at)}</span>
            </Item>
          ))}
        </section>
        <section className="card at-risk">
          <h2>Nobody knows these now <span className="count">{left}</span></h2>
          {h.remaining.map((item) => <Item key={item} item={item} open={open} />)}
        </section>
      </div>

      <p className="callout">
        <Pill tone="accent">Suggestion</Pill> All {left} are DevOps. Nearest person: <b>{first(h.mentor.person)}</b> (
        {h.mentor.reason}). The graph just wrote a hiring request.
      </p>

      <Cypher>{`
// after the last day: what a former member knows and no active person KNOWS or LEARNED
MATCH (l:Person {active: false})-[:KNOWS]->(k) WHERE k:File OR (k:Decision AND k.status = 'active')
OPTIONAL MATCH (o:Person {active: true})-[:KNOWS|LEARNED]->(k)
WITH k, count(o) AS backups WHERE backups = 0
RETURN coalesce(k.id, k.path) AS still_orphaned`}</Cypher>
    </>
  );
}
