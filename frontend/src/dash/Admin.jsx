import { useState } from "react";
import { DataProvider, Item, Pill, Score, api, go, useData } from "../ui.jsx";
import KnowsGraph from "../screens/KnowsGraph.jsx";
import { Dash, Sources, WhyPage, openWhy, pending, useLoad } from "./common.jsx";

const BASE = "admin";
const open = openWhy(BASE);
const initials = (name) => name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const repoBusy = (s) => s && !s.startsWith("done") && !s.startsWith("failed");

function Stat({ value, children, tone }) {
  return (
    <div className="card stat">
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
        <Stat value={data.people.filter((p) => p.active !== false).length}>people working</Stat>
        <Stat value={data.radar.length} tone={data.radar.length ? "risk-text" : ""}>things only one person knows</Stat>
        <Stat value={open_} tone={open_ ? "risk-text" : ""}>handover items not learned yet</Stat>
        <Stat value={data.sources.length}>docs and AI sessions</Stat>
      </div>
      <h2 className="section-title">Only one person knows these</h2>
      {!groups.length && <p className="muted">Nothing yet. Connect a repo or ask people to add their docs and AI sessions.</p>}
      {groups.map(({ p, rows }) => {
        const s = status(p);
        return (
          <section key={p.id} className="card">
            <h2>{first(p.id)} <span className="count">{rows.length}</span> <Pill tone={s.tone}>{s.text}</Pill></h2>
            {rows.map((r) => <Item key={r.item} item={r.item} open={open}><Score value={r.score} max={max} /></Item>)}
          </section>
        );
      })}
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
        {error && <p className="form-error">{error}</p>}
        <p className="muted small">Commit authors are matched to employees by GitHub login. Anyone unmatched shows up as a
          contributor you can add later. Without a GitHub token (Settings) the first sync reads the last 25 commits and 10 PRs.</p>
      </section>
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
        <Sources sources={data.sources} who={data.first} onRemove={remove} />
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
        <p>The AI provider reads uploaded docs and AI sessions and pulls out the decisions in them. Any OpenAI-compatible API
          works, including free tiers.</p>
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
    </>
  );
}

export default function Admin({ path }) {
  const [section = "overview", id] = path;
  const [data, reload, error] = useLoad("admin", (d) => repoBusy(d.repo.status) || pending(d.sources));
  const nav = [
    ["overview", "Overview"],
    ["employees", "Employees", data?.people.length],
    ["graph", "Knowledge graph"],
    ["handovers", "Handovers", data?.successors.length],
    ["sources", "Sources", data?.sources.length],
    ["settings", "Settings"],
  ];
  const page = {
    overview: <Overview />, employees: <Employees reload={reload} />, graph: <Graph />, handovers: <Handovers />,
    sources: <SourcesPage reload={reload} />, settings: <SettingsPage reload={reload} />,
    person: <Person id={id} />, why: <WhyPage base={BASE} id={id} />,
  }[section] ?? <p className="muted">Nothing here.</p>;
  return <Dash base={BASE} nav={nav} current={section} data={data} error={error}>{page}</Dash>;
}
