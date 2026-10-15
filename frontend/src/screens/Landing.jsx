import { data } from "../ui.jsx";

export default function Landing({ start }) {
  const c = data.workspace.counts;
  return (
    <main className="landing">
      <h1>Know what walks out the door before it does.</h1>
      <p className="lead">
        KT Brain records who knows what from a developer's first day: commits, reviews, tickets, chat, docs and AI
        coding sessions, all in one FalkorDB graph. When someone resigns, the handover plan is already written.
      </p>
      <button className="btn primary lg" onClick={start}>Open the TiffinBox demo →</button>
      <p className="muted small">
        A synthetic meal-subscription startup: 6 months, {data.people.length} people, {c.Decision} decisions,{" "}
        {c.edges} edges. Two engineers resign on Sep 15.
      </p>
      <div className="soon">
        <span className="pill muted">Coming soon</span>
        Bring your own: a public GitHub repo, docs, or Claude Code session logs.
      </div>
    </main>
  );
}
