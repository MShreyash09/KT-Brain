import { useData } from "../ui.jsx";
import { DryRun } from "./Departure.jsx";
import RoomStory from "./RoomStory.jsx";

const steps = (data, h = data.handover) => [
  ["team", "Team", "Commits, reviews, tickets, chat, docs and AI sessions become weighted KNOWS edges. Nobody fills in a skills matrix."],
  ["radar", "Radar", `${data.radar.length} things only one person knows, found while everyone is still here.`],
  ["departure", "Departure", "Dry-run a resignation on a copy of the graph. What nobody else knows becomes the KT agenda."],
  ["why", "Why", "Every decision traces back to the thread, ticket, PR and AI session that recorded it."],
  ["handover", "Handover", `The new hire's KT session and PRs count the agenda down: ${h.before} → ${h.remaining.length}.`],
  ["ask", "Ask", "Full-text search over docs, AI sessions and chat, in the same FalkorDB graph."],
];

export default function Landing({ start }) {
  const data = useData();
  const STEPS = steps(data);
  const c = data.workspace.counts;
  return (
    <main className="landing">
      <section className="hero">
        <h1>Know what walks out the door before it does.</h1>
        <div className="hero-row">
          <p className="lead">
            KT Brain records who knows what from a developer's first day: commits, reviews, tickets, chat, docs and AI
            coding sessions, all in one FalkorDB graph. When someone resigns, the handover plan is already written.
          </p>
          <div className="hero-actions">
            <button className="btn primary lg" onClick={start}>Open the TiffinBox demo</button>
            <a className="btn lg" href="#/departure">Dry-run a resignation</a>
          </div>
        </div>
        <RoomStory />
      </section>

      <section className="split">
        <div>
          <h2>Run the resignation before it happens</h2>
          <p className="lead">
            Pick who leaves. KT Brain copies the graph, takes them out, and lists everything nobody else knows. That list
            is the KT agenda.
          </p>
          <p className="muted small">
            TiffinBox is a synthetic meal-subscription startup: 6 months, {data.people.length} people, {c.Decision}{" "}
            decisions, {c.edges} edges.
          </p>
        </div>
        <div className="hero-demo">
          <p className="demo-label">Who leaves?</p>
          <DryRun limit={4} more={(n) => <a className="more" href="#/departure">{n} more in the dry run</a>} />
        </div>
      </section>

      <section className="tour">
        <h2>Six steps through one resignation</h2>
        <ol>
          {STEPS.map(([id, name, text], i) => (
            <li key={id}>
              <a href={`#/${id}`}>
                <span className="n">{i + 1}</span>
                <h3>{name}</h3>
                <p>{text}</p>
              </a>
            </li>
          ))}
        </ol>
      </section>

      <div className="soon">
        <span className="pill muted">Coming soon</span>
        Bring your own: a public GitHub repo, docs, or Claude Code session logs.
      </div>
    </main>
  );
}
