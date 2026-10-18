import { Icon, Skeleton, go, useData } from "../ui.jsx";
import { DryRun } from "./Departure.jsx";
import RoomStory from "./RoomStory.jsx";

const REPO = "https://github.com/MShreyash09/KT-Brain";

const steps = (data, h = data.handover) => [
  ["team", "Team", "Commits, reviews, tickets, chat, docs and AI sessions become weighted KNOWS edges. Nobody fills in a skills matrix."],
  ["radar", "Radar", `${data.radar.length} things only one person knows, found while everyone is still here.`],
  ["departure", "Departure", "Dry-run a resignation on a copy of the graph. What nobody else knows becomes the KT agenda."],
  ["why", "Why", "Every decision traces back to the thread, ticket, PR and AI session that recorded it."],
  ["handover", "Handover", `The new hire's KT session and PRs count the agenda down: ${h.before} → ${h.remaining.length}.`],
  ["ask", "Ask", "An agent answers from the graph and cites the source behind every line."],
];

// what the product reads today (README "Capturing AI coding sessions"); nothing planned is listed
const SOURCES = [["branch", "GitHub commits, PRs & reviews"], ["terminal", "Claude Code sessions"], ["terminal", "Codex sessions"],
  ["file", "Markdown & PDF docs"], ["message", "MCP for coding agents"], ["database", "FalkorDB graph"]];

const FEATURES = [
  ["target", "Bus-factor radar", "Every file and decision only one active person knows, ranked by blast radius from algo.pageRank over your service graph.", "wide"],
  ["logout", "Departure dry run", "Simulate a resignation on a GRAPH.COPY of your workspace. The leftover list is the KT agenda, including what's lost only if two people leave."],
  ["branch", "Why-trace", "Click a decision and walk back to the chat thread, ticket, PR and AI session that recorded it."],
  ["zap", "An agent that acts on its own", "Every minute it checks the radar. A new single-knower item gets an alert and a KT brief written from that person's own work.", "wide"],
  ["swap", "Handover to zero", "Offboard with a successor who inherits the brain. KT sessions and their PRs add LEARNED edges until the count hits zero."],
  ["message", "Ask with citations", "Questions are answered by tools over the graph, never free-written Cypher. A line without a valid source is dropped.", "wide"],
];

const HOW = [
  ["Connect", "Point it at your GitHub repo. Teammates drop in docs, or sync Claude Code and Codex sessions with the CLI, which redacts secrets on their laptop."],
  ["Watch", "KT Brain derives who KNOWS what from real work, fading with age. The agent flags anything only one person knows, the day it happens."],
  ["Hand over", "When someone resigns, dry-run it first, then offboard to a successor and track the agenda down to zero."],
];

const TRUST = [
  ["lock", "Local-first capture", "The CLI strips sessions to prompts, answers and file paths and removes secrets before anything leaves the laptop."],
  ["users", "Permission-aware answers", "Members see their own graph and shared docs. The agent only cites what the person asking could already open."],
  ["database", "One graph per company", "Each workspace is its own FalkorDB graph. Dry runs happen on a throwaway copy, so the live graph is never touched."],
  ["shield", "Careful wording", "It says “no recorded evidence anyone else knows this”, never “nobody knows this”. It tracks coverage, not productivity."],
];

const FAQ = [
  ["Does it replace KT sessions?", "No. It tells you which KT sessions matter: the items with no recorded backup. Then it counts them down as the successor learns them."],
  ["Is this a way to rank employees?", "No. It scores knowledge per file and decision to find items without a backup. No screen ranks people or measures output."],
  ["Do I need an AI key?", "No. The radar, dry runs, why-traces and handovers are graph queries. A key from any OpenAI-compatible provider adds written answers, decision extraction and KT briefs."],
  ["Why a graph database?", "“Nobody else knows this” is a question about missing paths. Search can't prove an absence; a graph query over KNOWS edges can, and GRAPH.COPY makes dry runs free."],
];

// the hero and the office story need no data, so they show at once; the demo sections wait for /api/workspace
export default function Landing({ start }) {
  const data = useData();
  return (
    <main className="landing">
      <section className="hero">
        <span className="eyebrow"><Icon name="zap" size={14} /> New: an agent that flags single-knower risk on its own</span>
        <h1>Know what walks out the door before it does.</h1>
        <p className="lead">
          KT Brain records who knows what from a developer's first day: commits, reviews, chat, docs and AI coding
          sessions, in one FalkorDB graph. When someone resigns, the handover plan is already written.
        </p>
        <div className="hero-actions">
          <a className="btn primary lg" href="#/register">Start free <Icon name="arrow" size={16} /></a>
          <button className="btn lg" onClick={start}>Explore the live demo</button>
        </div>
        <p className="hero-note"><Icon name="check" size={14} /> Free during beta <Icon name="check" size={14} /> No AI key needed
          <Icon name="check" size={14} /> Demo workspace preloaded</p>
        <div className="app-frame">
          <div className="frame-bar" aria-hidden="true"><i /><i /><i /><span>kt-brain · TiffinBox office</span></div>
          <RoomStory />
        </div>
      </section>

      <section className="logos" aria-label="Sources">
        <p>Reads the tools your team already uses</p>
        <ul>{SOURCES.map(([icon, name]) => <li key={name}><Icon name={icon} size={16} /> {name}</li>)}</ul>
      </section>

      <section className="block" id="product">
        <Head kicker="Product" title="Everything a handover needs, before anyone resigns">
          A chatbot answers the questions you think to ask. KT Brain finds the ones you didn't know to ask.
        </Head>
        <div className="bento">
          {FEATURES.map(([icon, title, text, size]) => (
            <article key={title} className={`feature ${size ?? ""}`}>
              <span className="feature-icon"><Icon name={icon} /></span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="block" id="how">
        <Head kicker="How it works" title="Three steps. No skills matrix." />
        <ol className="how">
          {HOW.map(([title, text], i) => (
            <li key={title}><span className="how-n">{i + 1}</span><h3>{title}</h3><p>{text}</p></li>
          ))}
        </ol>
      </section>

      {data ? <Demo data={data} /> : <section className="block"><Skeleton lines={6} /></section>}

      <section className="block" id="security">
        <Head kicker="Security & privacy" title="Built for the people being recorded, too" />
        <div className="trust">
          {TRUST.map(([icon, title, text]) => (
            <div key={title} className="trust-item">
              <Icon name={icon} />
              <div><h3>{title}</h3><p>{text}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section className="block" id="pricing">
        <Head kicker="Pricing" title="Free while we're in beta" />
        <div className="plans">
          <article className="plan featured">
            <h3>Hosted beta</h3>
            <p className="price">$0 <span>/ company</span></p>
            <ul>
              {["Admin and member accounts", "GitHub repo with daily sync", "Docs and AI-session uploads", "Agent alerts and KT briefs",
                "Bring your own AI key (optional)"].map((x) => <li key={x}><Icon name="check" size={16} /> {x}</li>)}
            </ul>
            <a className="btn primary" href="#/register">Register your company</a>
          </article>
          <article className="plan">
            <h3>Self-hosted</h3>
            <p className="price">$0 <span>/ your infra</span></p>
            <ul>
              {["Everything in the hosted beta", "Runs on your own FalkorDB", "Docker, uv and Node, about five minutes",
                "MCP server for your coding agents"].map((x) => <li key={x}><Icon name="check" size={16} /> {x}</li>)}
            </ul>
            <a className="btn" href={REPO} target="_blank" rel="noreferrer">View setup on GitHub</a>
          </article>
        </div>
      </section>

      <section className="block" id="faq">
        <Head kicker="FAQ" title="Questions teams ask first" />
        <div className="faq">
          {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
        </div>
      </section>

      <footer className="footer">
        <div className="footer-hero">
          <div className="footer-copy">
            <span className="kicker">Week one of the new hire</span>
            <h2>Stop guessing why the code looks the way it does</h2>
            <p>Meera finds <code>retries = 7</code> and almost “fixes” it. She asks KT Brain instead, and gets Arjun's
              reason with the chat, ticket and PR behind it.</p>
            <div className="hero-actions">
              <a className="btn primary lg" href="#/register">Start free <Icon name="arrow" size={16} /></a>
              <button className="btn lg" onClick={start}>Explore the live demo</button>
            </div>
          </div>
          <DevScene />
        </div>
        <div className="footer-brand">
          <b>KT Brain</b>
          <p>Knowledge transfer is a coverage problem, not a Q&amp;A problem.</p>
        </div>
        <nav aria-label="Product">
          <h4>Product</h4>
          <a href="#/radar">Radar</a><a href="#/departure">Departure dry run</a><a href="#/why">Why-trace</a><a href="#/ask">Ask</a>
        </nav>
        <nav aria-label="Account">
          <h4>Account</h4>
          <a href="#/login">Sign in</a><a href="#/register">Register a company</a>
        </nav>
        <nav aria-label="Developers">
          <h4>Developers</h4>
          <a href={REPO} target="_blank" rel="noreferrer">GitHub</a>
          <a href={`${REPO}#setup`} target="_blank" rel="noreferrer">Setup guide</a>
        </nav>
        <p className="footer-note">Built on FalkorDB for WeMakeDevs × FalkorDB Graph Hacks 2026. TiffinBox data is synthetic.</p>
      </footer>
    </main>
  );
}

// Over the shoulder of a new hire: they hit retries = 7, ask KT Brain why, and get D1 with its sources.
// One 10 s CSS loop (styles.css, "dev scene"); with reduced motion every element simply shows its final state.
const CODE = ["# api/payments/retry.py", "def charge(order):", "    retries = 7", "    backoff = 2 ** attempt", "    return gateway.pay(", "        order, retries)"];
const ANSWER = ["Gateway drops webhooks", "for ~5 min on deploys.", "7 retries cover that."];

function DevScene() {
  return (
    <svg className="dev-scene" viewBox="0 0 640 400" role="img"
      aria-label="A developer asks KT Brain why retries is 7 and gets decision D1 with its sources">
      <path className="ds-desk" d="M20 300H620" />
      <rect className="ds-monitor" x="90" y="16" width="460" height="244" rx="12" />
      <rect className="ds-screen" x="102" y="28" width="436" height="220" rx="4" />
      <path className="ds-stand" d="M300 260h40l8 40h-56z" />

      {/* editor */}
      <rect className="ds-hl" x="110" y="80" width="250" height="20" rx="3" />
      <rect className="ds-ok" x="110" y="80" width="250" height="20" rx="3" />
      {CODE.map((line, i) => (
        <text key={i} className={`ds-code ${i === 0 ? "ds-comment" : ""}`} x="118" y={54 + i * 22} xmlSpace="preserve">{line}</text>
      ))}
      <rect className="ds-cursor" x="232" y="83" width="2" height="14" />
      <g className="ds-check">
        <rect x="300" y="83" width="52" height="14" rx="7" />
        <text x="326" y="93.5">✓ D1</text>
      </g>

      {/* KT Brain panel */}
      <path className="ds-divider" d="M372 28V248" />
      <circle className="ds-logo" cx="392" cy="48" r="8" />
      <text className="ds-title" x="406" y="52">KT Brain</text>
      <g className="ds-q">
        <rect x="384" y="66" width="142" height="26" rx="13" />
        <text x="455" y="83">Why retries = 7?</text>
      </g>
      <g className="ds-think">{[0, 1, 2].map((i) => <circle key={i} cx={392 + i * 10} cy="112" r="3" style={{ animationDelay: `${i * 0.15}s` }} />)}</g>
      {ANSWER.map((line, i) => (
        <text key={line} className="ds-a" x="386" y={116 + i * 18} style={{ animationDelay: `${i * 0.35}s` }}>{line}</text>
      ))}
      {[["D1", 386], ["PAY-88", 420], ["#payments", 474]].map(([cite, x], i) => (
        <g key={cite} className="ds-chip" style={{ animationDelay: `${i * 0.2}s` }}>
          <rect x={x} y="184" width={cite.length * 6.4 + 12} height="20" rx="5" />
          <text x={x + 6} y="198">{cite}</text>
        </g>
      ))}

      {/* the developer, seen from behind */}
      <g className="ds-dev">
        <path className="ds-body" d="M210 400v-22c0-30 26-48 58-50h104c32 2 58 20 58 50v22z" />
        <circle className="ds-head" cx="320" cy="300" r="32" />
        <path className="ds-hair" d="M288 300a32 32 0 0 1 64 0c-10 4-20 6-32 6s-22-2-32-6z" />
      </g>
    </svg>
  );
}

function Head({ kicker, title, children }) {
  return (
    <header className="block-head">
      <span className="kicker">{kicker}</span>
      <h2>{title}</h2>
      {children && <p className="lead">{children}</p>}
    </header>
  );
}

function Demo({ data }) {
  const c = data.workspace.counts;
  const STEPS = steps(data);
  return (
    <>
      <section className="block" id="demo">
        <div className="split">
          <div>
            <span className="kicker">Try it</span>
            <h2>Run the resignation before it happens</h2>
            <p className="lead">
              Pick who leaves. KT Brain copies the graph, takes them out, and lists everything nobody else knows. That
              list is the KT agenda.
            </p>
            <dl className="metrics">
              <div><dt>people</dt><dd>{data.people.length}</dd></div>
              <div><dt>decisions</dt><dd>{c.Decision}</dd></div>
              <div><dt>graph edges</dt><dd>{c.edges}</dd></div>
              <div><dt>single-knower items</dt><dd className="risk-text">{data.radar.length}</dd></div>
            </dl>
            <p className="muted small">TiffinBox: a synthetic meal-subscription startup, 6 months of history.</p>
          </div>
          <div className="hero-demo">
            <p className="demo-label">Who leaves?</p>
            <DryRun limit={4} more={(n) => <a className="more" href="#/departure">{n} more in the dry run</a>} />
          </div>
        </div>
      </section>

      <section className="block tour">
        <Head kicker="Guided tour" title="Six steps through one resignation" />
        <ol>
          {STEPS.map(([id, name, text], i) => (
            <li key={id}>
              <a href={`#/${id}`} onClick={(e) => { e.preventDefault(); go(id); }}>
                <span className="n">{i + 1}</span>
                <h3>{name}</h3>
                <p>{text}</p>
              </a>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
