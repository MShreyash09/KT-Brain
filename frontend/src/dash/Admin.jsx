import { useState } from "react";
import { DataProvider, Icon, Item, Pill, Score, api, go, useData } from "../ui.jsx";
import KnowsGraph from "../screens/KnowsGraph.jsx";
import { Alerts, Dash, DocPage, Find, Sources, WhyPage, openWhy, pending, share, useLoad } from "./common.jsx";
import { Blast } from "../screens/Radar.jsx";

const BASE = "admin";
const open = openWhy(BASE);
const initials = (name) => name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const repoBusy = (s) => s && !s.startsWith("done") && !s.startsWith("failed");
// The server keeps the daily sync time in UTC; the admin picks it in their own time zone.
// ponytail: converted with today's offset, so a DST change shifts it by an hour; store an IANA zone if that matters
const toUtc = (hhmm) => { const d = new Date(); d.setHours(...hhmm.split(":").map(Number), 0, 0); return d.toISOString().slice(11, 16); };
const toLocal = (hhmm) => { const d = new Date(); d.setUTCHours(...hhmm.split(":").map(Number), 0, 0); return d.toTimeString().slice(0, 5); };

function Stat({ value, children, tone, icon }) {
  return (
    <div className="card stat">
      <span className={`stat-icon ${tone ? "risk" : ""}`}><Icon name={icon} /></span>
      <span className={`big-num ${tone ?? ""}`}>{value}</span>
      <span className="muted">{children}</span>
    </div>
  );
}

function Overview() {
  const data = useData();
  const { first, status } = data;
  const open_ = data.successors.reduce((n, s) => n + s.agenda - s.learned, 0);
  const max = Math.max(...data.radar.map((r) => r.score), 1);
  const groups = data.people.map((p) => ({ p, rows: data.radar.filter((r) => r.person === p.id) })).filter((g) => g.rows.length);
  return (
    <>
      <header className="step-head">
        <h1>{data.workspace.name}</h1>
        <p>Who knows what across the company, and what would leave with each person.</p>
      </header>
      <div className="stats">
        <Stat icon="users" value={data.people.filter((p) => p.active !== false).length}>people working</Stat>
        <Stat icon="target" value={data.radar.length} tone={data.radar.length ? "risk-text" : ""}>things only one person knows</Stat>
        <Stat icon="swap" value={open_} tone={open_ ? "risk-text" : ""}>handover items not learned yet</Stat>
        <Stat icon="file" value={data.sources.length}>docs and AI sessions</Stat>
      </div>
      <h2 className="section-title">Only one person knows these</h2>
      {!groups.length && <p className="muted">Nothing yet. Connect a repo or ask people to add their docs and AI sessions.</p>}
      {groups.map(({ p, rows }) => {
        const s = status(p);
        return (
          <section key={p.id} className="card">
            <h2>{first(p.id)} <span className="count">{rows.length}</span> <Pill tone={s.tone}>{s.text}</Pill></h2>
            {rows.map((r) => <Item key={r.item} item={r.item} open={open}><Blast value={r.blast} /><Score value={r.score} max={max} /></Item>)}
          </section>
        );
      })}
      <AgentActivity />
    </>
  );
}

function AgentActivity() {
  const data = useData();
  const live = data.alerts.filter((a) => a.status === "open");
  const closed = data.alerts.filter((a) => a.status !== "open").slice(0, 20);
  return (
    <>
      <h2 className="section-title">Agent activity <span className="count">{live.length} open</span></h2>
      <p className="muted small">Nobody asks for these. Every minute the agent checks the radar. When something becomes known
        by only one person (after a sync, an upload or someone leaving), it opens an alert and writes a KT brief from that
        person's own work: what it is, and what to ask them before they go. It closes the alert when a second person
        knows the item, or marks it lost if they left first.</p>
      {!data.alerts.length && <p className="muted">No alerts yet. The agent's first check runs within a minute of the server starting.</p>}
      {live.length > 0 && <section className="card at-risk"><Alerts alerts={live} base={BASE} who={data.first} /></section>}
      {closed.length > 0 && <section className="card"><h2>Closed</h2><Alerts alerts={closed} base={BASE} who={data.first} /></section>}
    </>
  );
}

function AddEmployee({ reload }) {
  const [form, setForm] = useState({ name: "", email: "", role: "Engineer", github: "", password: "welcome123" });
  const [done, setDone] = useState(null);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setDone(await api("admin/employees", form));
      setForm({ ...form, name: "", email: "", github: "" });
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <details className="card add-employee">
      <summary><b>Add an employee</b></summary>
      <form className="form-grid" onSubmit={submit}>
        <label className="field"><span>Name</span><input required value={form.name} onChange={set("name")} /></label>
        <label className="field"><span>Email</span><input required type="email" value={form.email} onChange={set("email")} /></label>
        <label className="field"><span>Role</span><input value={form.role} onChange={set("role")} /></label>
        <label className="field"><span>GitHub login (links their commits)</span><input value={form.github} onChange={set("github")} /></label>
        <label className="field"><span>First password</span><input required minLength={6} value={form.password} onChange={set("password")} /></label>
        <div className="form-actions"><button className="btn primary">Add employee</button></div>
      </form>
      {error && <p className="form-error">{error}</p>}
      {done && <p className="callout">Account ready. Send them: <code>{done.email}</code> / <code>{done.password}</code></p>}
    </details>
  );
}

function Employee({ p, reload }) {
  const data = useData();
  const { status, first } = data;
  const [panel, setPanel] = useState(null); // "dryrun" | "offboard"
  const [run, setRun] = useState(null);
  const [successor, setSuccessor] = useState("");
  const [error, setError] = useState("");
  const s = status(p);
  const knows = data.knows.filter((k) => k.person === p.id).length;
  const only = data.radar.filter((r) => r.person === p.id).length;
  const account = data.users.find((u) => u.person === p.id);
  const others = data.people.filter((o) => o.id !== p.id && o.active !== false);
  const succeededBy = data.successors.find((x) => x.leaver === p.id);

  const simulate = async () => {
    setPanel(panel === "dryrun" ? null : "dryrun");
    if (!run) setRun(await api(`admin/dryrun?leavers=${encodeURIComponent(p.id)}`));
  };
  const offboard = async () => {
    setError("");
    try {
      await api("admin/offboard", { person: p.id, successor });
      setPanel(null);
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="card employee">
      <div className="emp-head">
        <span className="avatar" aria-hidden="true">{initials(p.name)}</span>
        <span className="item-label">
          <b>{p.name}</b> <Pill tone={s.tone}>{s.text}</Pill><br />
          <span className="meta">{p.role}{account ? ` · ${account.email}` : " · no account yet"}{p.github ? ` · @${p.github}` : ""}</span>
        </span>
        <span className="emp-num">knows {knows}{only ? <> · <b className="risk-text">only one: {only}</b></> : null}</span>
      </div>
      <div className="emp-actions">
        <button className="btn" onClick={() => go(BASE, "person", p.id)}>Graph</button>
        {p.active !== false && <button className="btn" aria-expanded={panel === "dryrun"} onClick={simulate}>Simulate leaving</button>}
        {p.active !== false && <button className="btn" aria-expanded={panel === "offboard"}
          onClick={() => setPanel(panel === "offboard" ? null : "offboard")}>Offboard…</button>}
        {succeededBy && <span className="muted small">Brain handed to {first(succeededBy.successor)}</span>}
      </div>
      {panel === "dryrun" && (
        <div className="emp-panel">
          {!run ? <p className="muted">Copying the graph and removing {first(p.id)}…</p> : (
            <>
              <p><b className={run.agenda.length ? "risk-text" : ""}>{run.agenda.length}</b> things would leave with {first(p.id)}, with nobody else who knows them.</p>
              {run.agenda.map((i) => <Item key={i} item={i} open={open} />)}
              {Object.entries(run.weak_backup).map(([i, who]) => (
                <Item key={i} item={i} open={open}><Pill tone="warn">weak backup: {first(who)}</Pill></Item>
              ))}
            </>
          )}
        </div>
      )}
      {panel === "offboard" && (
        <div className="emp-panel">
          <p>{first(p.id)} is marked as left today and can no longer sign in. The successor can read {first(p.id)}'s graph,
            decisions and why-traces, and works through the items only {first(p.id)} knew.</p>
          <div className="inline-form">
            <label className="field"><span>Successor</span>
              <select value={successor} onChange={(e) => setSuccessor(e.target.value)}>
                <option value="">Pick a person…</option>
                {others.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.role})</option>)}
              </select>
            </label>
            <button className="btn primary danger" disabled={!successor} onClick={offboard}>Offboard {first(p.id)}</button>
          </div>
          {error && <p className="form-error">{error}</p>}
        </div>
      )}
    </section>
  );
}

function Employees({ reload }) {
  const data = useData();
  return (
    <>
      <header className="step-head">
        <h1>Employees</h1>
        <p>Simulate a departure before it happens, then offboard with a successor who inherits the brain.</p>
      </header>
      <AddEmployee reload={reload} />
      {data.people.map((p) => <Employee key={p.id} p={p} reload={reload} />)}
    </>
  );
}

function Person({ id }) {
  const data = useData();
  const p = data.person[id];
  if (!p) return <p className="muted">No such person.</p>;
  const knows = data.knows.filter((k) => k.person === id);
  const max = Math.max(...knows.map((k) => k.score), 1);
  return (
    <>
      <p><a href="#/admin/employees">← Employees</a></p>
      <header className="step-head">
        <h1>{p.name}</h1>
        <p>{p.role}. Every file and decision {data.first(id)} knows, scored from their commits, reviews, docs, chat and AI sessions.</p>
      </header>
      <DataProvider data={{ ...data, people: [p], knows }}>
        <KnowsGraph sel={id} onPerson={() => {}} open={open} />
      </DataProvider>
      <section className="card">
        <h2>{data.first(id)} knows <span className="count">{knows.length}</span></h2>
        {knows.length ? knows.map((k) => <Item key={k.item} item={k.item} open={open}><Score value={k.score} max={max} /></Item>)
          : <p className="muted">Nothing yet.</p>}
      </section>
    </>
  );
}

function Graph() {
  const data = useData();
  const [sel, setSel] = useState(data.people[0]?.id);
  return (
    <>
      <header className="step-head">
        <h1>Knowledge graph</h1>
        <p>Every person and the files and decisions they know. Hover to isolate one, click a person to highlight them, click an item for its why-trace.</p>
      </header>
      {data.knows.length ? <KnowsGraph sel={sel} onPerson={setSel} open={open} /> : <p className="muted">No knowledge yet.</p>}
    </>
  );
}

function Handovers() {
  const data = useData();
  const { first } = data;
  return (
    <>
      <header className="step-head">
        <h1>Handovers</h1>
        <p>For each person who left: the items only they knew, and how many their successor has learned.</p>
      </header>
      {!data.successors.length && <p className="muted">Nobody has been offboarded yet.</p>}
      {data.successors.map((s) => (
        <section key={s.leaver} className="card">
          <div className="big">
            <span className="big-num">{s.learned} <span className="muted">/ {s.agenda}</span></span>
            <span>items only {first(s.leaver)} knew, learned by {first(s.successor)}</span>
          </div>
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={s.agenda} aria-valuenow={s.learned}
            aria-label={`${first(s.leaver)} handover`}>
            <span style={{ width: `${s.agenda ? (s.learned / s.agenda) * 100 : 100}%` }} />
          </div>
          <p className="muted small">The agenda counts down as {first(s.successor)} has KT sessions, ships their own work on these
            items, or marks them learned.</p>
        </section>
      ))}
    </>
  );
}

function SourcesPage({ reload }) {
  const data = useData();
  const [url, setUrl] = useState(data.repo.url);
  const [syncAt, setSyncAt] = useState(data.repo.sync_at ? toLocal(data.repo.sync_at) : "19:00");
  const [error, setError] = useState("");
  const proposed = Object.values(data.decisions).filter((d) => d.status === "proposed");
  const run = async (fn) => {
    setError("");
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const connect = (e) => {
    e.preventDefault();
    run(() => api("admin/github", { url }));
  };
  const autoSync = (at) => run(() => api("admin/autosync", { at: at && toUtc(at) }, "PUT"));
  const review = (id, action) => run(() => api(`admin/decisions/${encodeURIComponent(id)}`, { action }));
  const remove = (s) => confirm(`Remove “${s.title || s.ref}” and the decisions only it recorded?`)
    && run(() => api(`admin/sources/${s.ref.split("/").map(encodeURIComponent).join("/")}`, undefined, "DELETE"));
  return (
    <>
      <header className="step-head">
        <h1>Sources</h1>
        <p>The company repo is connected here. Each employee adds their own docs and AI coding sessions from their dashboard.</p>
      </header>
      <section className="card">
        <h2>GitHub repository</h2>
        <form className="inline-form" onSubmit={connect}>
          <label className="field grow"><span>Public repo URL</span>
            <input required placeholder="https://github.com/owner/repo" value={url} onChange={(e) => setUrl(e.target.value)} />
          </label>
          <button className="btn primary" disabled={repoBusy(data.repo.status)}>{data.repo.url ? "Sync again" : "Connect"}</button>
        </form>
        {data.repo.status && (
          <p className={data.repo.status.startsWith("failed") ? "form-error" : "muted small"}>{data.repo.status}</p>
        )}
        {data.repo.url && (
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); autoSync(syncAt); }}>
            <label className="field"><span>Sync every day at (your time)</span>
              <input type="time" required value={syncAt} onChange={(e) => setSyncAt(e.target.value)} />
            </label>
            <button className="btn">{data.repo.sync_at ? "Change time" : "Turn on daily sync"}</button>
            {data.repo.sync_at && <button type="button" className="btn" onClick={() => autoSync("")}>Turn off</button>}
          </form>
        )}
        {data.repo.url && (
          <p className="muted small">{data.repo.sync_at ? `Daily sync is on at ${toLocal(data.repo.sync_at)}.` : "Daily sync is off."} The
            default is after work hours, so it doesn't use the GitHub limit during the day. It only sets when KT Brain reads
            the repo: every commit keeps its own time and counts the same whatever hour it was made.</p>
        )}
        {error && <p className="form-error">{error}</p>}
        <p className="muted small">Commit authors are matched to employees by GitHub login. Anyone unmatched shows up as a
          contributor you can add later. Without a GitHub token (Settings) the first sync reads the last 25 commits and 10 PRs.</p>
      </section>
      <BucketCard reload={reload} />
      {proposed.length > 0 && (
        <section className="card">
          <h2>Proposed decisions <span className="count">{proposed.length}</span></h2>
          <p className="muted small">Pulled from an employee's upload. They stay out of the radar and handovers until you
            confirm them, or until a second person's source records the same decision.</p>
          {proposed.map((d) => (
            <div key={d.id} className="agenda-row">
              <Item item={d.id} open={open} />
              <button className="btn" onClick={() => review(d.id, "confirm")}>Confirm</button>
              <button className="btn danger" onClick={() => review(d.id, "reject")}>Reject</button>
            </div>
          ))}
        </section>
      )}
      <section className="card">
        <h2>Docs and AI sessions <span className="count">{data.sources.length}</span></h2>
        <Sources sources={data.sources} base={BASE} who={(s) => data.first(s.person)} onRemove={remove}
          onShare={(s) => run(() => share(s))} />
      </section>
    </>
  );
}

function SettingsPage({ reload }) {
  const data = useData();
  const saved = data.settings.provider ? data.settings : { provider: "openrouter", ...data.presets.openrouter };
  const [form, setForm] = useState({ provider: saved.provider, base: saved.base, model: saved.model, key: "", github_token: "" });
  const [msg, setMsg] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const pick = (e) => {
    const p = data.presets[e.target.value];
    setForm({ ...form, provider: e.target.value, ...(p ? { base: p.base, model: p.model } : {}) });
  };
  const save = async (e) => {
    e.preventDefault();
    setMsg(null);
    try {
      await api("admin/settings", form, "PUT");
      setForm({ ...form, key: "", github_token: "" });
      setMsg({ ok: "Saved." });
      reload();
    } catch (err) {
      setMsg({ error: err.message });
    }
  };
  const test = async () => {
    setMsg({ ok: "Asking the model…" });
    try {
      setMsg({ ok: `It answered: “${(await api("admin/settings/test", {})).reply}”` });
    } catch (err) {
      setMsg({ error: err.message });
    }
  };
  return (
    <>
      <header className="step-head">
        <h1>Settings</h1>
        <p>One key for the whole company. The AI provider pulls decisions out of uploaded docs and AI sessions, answers
          everyone's questions on the Ask page, and writes the agent's KT briefs. Employees never need their own key.
          Any OpenAI-compatible API works, including free tiers.</p>
      </header>
      <form className="card form-grid" onSubmit={save}>
        <label className="field"><span>Provider</span>
          <select value={form.provider} onChange={pick}>
            <option value="openrouter">OpenRouter</option>
            <option value="groq">Groq</option>
            <option value="google">Google AI Studio</option>
            <option value="ollama">Ollama (local)</option>
            <option value="custom">Other OpenAI-compatible API</option>
          </select>
        </label>
        <label className="field"><span>Model (check your provider's current list)</span>
          <input required value={form.model} onChange={set("model")} />
        </label>
        <label className="field wide"><span>Base URL</span><input required value={form.base} onChange={set("base")} /></label>
        <label className="field wide"><span>API key {data.settings.key && <span className="muted">(saved: {data.settings.key}, leave empty to keep)</span>}</span>
          <input type="password" autoComplete="off" value={form.key} onChange={set("key")} />
        </label>
        <label className="field wide"><span>GitHub token, optional {data.settings.github_token && <span className="muted">(saved: {data.settings.github_token})</span>}</span>
          <input type="password" autoComplete="off" value={form.github_token} onChange={set("github_token")}
            placeholder="Raises the GitHub limit from 60 to 5,000 requests an hour" />
        </label>
        <div className="form-actions">
          <button className="btn primary">Save</button>
          <button type="button" className="btn" onClick={test} disabled={!data.settings.key}>Test the AI provider</button>
        </div>
        {msg?.ok && <p className="muted wide">{msg.ok}</p>}
        {msg?.error && <p className="form-error wide">{msg.error}</p>}
      </form>
      <p className="muted small">Keys are stored in the company record in FalkorDB and never sent back to the browser.</p>
      <BucketForm reload={reload} />
    </>
  );
}

// The company's own S3-compatible bucket for original documents (backend/ingest/s3.py)
function BucketForm({ reload }) {
  const s3 = useData().s3 ?? {};  // {} until the backend that sends it is deployed
  const [form, setForm] = useState({ endpoint: s3.endpoint, region: s3.region, bucket: s3.bucket, prefix: s3.prefix, key_id: "", secret: "" });
  const [msg, setMsg] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const run = async (fn, ok) => {
    setMsg({ ok: "Checking the bucket…" });
    try {
      await fn();
      setForm({ ...form, key_id: "", secret: "" });
      setMsg({ ok });
      reload();
    } catch (err) {
      setMsg({ error: err.message });
    }
  };
  return (
    <>
      <h2 className="section-title">Document storage <span className="pill muted">optional</span></h2>
      <form className="card form-grid" onSubmit={(e) => { e.preventDefault(); run(() => api("admin/s3", form, "PUT"), "Connected. Import your documents from the Sources page."); }}>
        <p className="muted small wide" style={{ margin: 0 }}>Keep original documents in your own S3-compatible bucket (AWS S3,
          Cloudflare R2, MinIO). KT Brain reads them into the graph for search and decisions, and readers can open the
          original file with its formatting through a link that expires after 5 minutes. Originals stay in your bucket.</p>
        <label className="field"><span>Bucket</span><input required value={form.bucket} onChange={set("bucket")} placeholder="acme-docs" /></label>
        <label className="field"><span>Folder prefix (optional)</span><input value={form.prefix} onChange={set("prefix")} placeholder="engineering/docs" /></label>
        <label className="field"><span>Region</span><input value={form.region} onChange={set("region")} placeholder="us-east-1 (auto for R2)" /></label>
        <label className="field"><span>Endpoint (empty for AWS S3)</span>
          <input value={form.endpoint} onChange={set("endpoint")} placeholder="https://<account>.r2.cloudflarestorage.com" /></label>
        <label className="field"><span>Access key ID {s3.key_id && <span className="muted">(saved: {s3.key_id})</span>}</span>
          <input autoComplete="off" value={form.key_id} onChange={set("key_id")} /></label>
        <label className="field"><span>Secret access key {s3.secret && <span className="muted">(saved: {s3.secret})</span>}</span>
          <input type="password" autoComplete="off" value={form.secret} onChange={set("secret")} /></label>
        <div className="form-actions">
          <button className="btn primary">{s3.connected ? "Save and test" : "Connect bucket"}</button>
          {s3.connected && <button type="button" className="btn" onClick={() => run(() => api("admin/s3", undefined, "DELETE"), "Disconnected.")}>Disconnect</button>}
        </div>
        {msg?.ok && <p className="muted wide">{msg.ok}</p>}
        {msg?.error && <p className="form-error wide">{msg.error}</p>}
        <p className="muted small wide" style={{ margin: 0 }}>Use a key limited to this bucket: read access to import and open
          originals, plus write access if web uploads should be kept there too.</p>
      </form>
    </>
  );
}

function BucketCard({ reload }) {
  const s3 = useData().s3 ?? {};  // {} until the backend that sends it is deployed
  const [error, setError] = useState("");
  if (!s3.connected) return null;
  const busy = /^(queued|reading)/.test(s3.status);
  const start = async () => {
    setError("");
    try {
      await api("admin/s3/import", {});
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <section className="card">
      <h2>S3 documents</h2>
      <div className="inline-form">
        <span className="grow"><code>s3://{s3.bucket}/{s3.prefix}</code></span>
        <button className="btn primary" disabled={busy} onClick={start}>{busy ? "Importing…" : "Import documents"}</button>
      </div>
      {s3.status && s3.status !== "connected" && <p className={s3.status.startsWith("failed") ? "form-error" : "muted small"}>{s3.status}</p>}
      {error && <p className="form-error">{error}</p>}
      <p className="muted small">Reads .md, .txt and .pdf files under the prefix (up to 200 per import, 8 MB each). Files that
        haven't changed since the last import are skipped.</p>
    </section>
  );
}

export default function Admin({ user, path }) {
  const [section = "overview", id] = path;
  const [data, reload, error] = useLoad("admin", (d) => repoBusy(d.repo.status) || /^(queued|reading)/.test(d.s3?.status) || pending(d.sources));
  const nav = [
    ["overview", "Overview", data?.alerts.filter((a) => a.status === "open").length],
    ["ask", "Ask"],
    ["employees", "Employees", data?.people.length],
    ["graph", "Knowledge graph"],
    ["handovers", "Handovers", data?.successors.length],
    ["sources", "Sources", data?.sources.length],
    ["settings", "Settings"],
  ];
  const page = {
    overview: <Overview />,
    ask: (
      <>
        <header className="step-head"><h1>Ask</h1><p>The agent answers from the whole company graph and cites every claim.</p></header>
        <Find base={BASE} hint="The agent sees the whole company: it can search every source, trace decisions, check who knows what, dry-run a departure and read the radar." />
      </>
    ),
    employees: <Employees reload={reload} />, graph: <Graph />, handovers: <Handovers />,
    sources: <SourcesPage reload={reload} />, settings: <SettingsPage reload={reload} />,
    person: <Person id={id} />, why: <WhyPage base={BASE} id={id} />, doc: <DocPage id={id} />,
  }[section] ?? <p className="muted">Nothing here.</p>;
  return <Dash base={BASE} nav={nav} current={section} data={data} error={error} user={user}>{page}</Dash>;
}
