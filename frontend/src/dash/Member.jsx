import { useState } from "react";
import { DataProvider, Item, Pill, Score, api, fmt, useData } from "../ui.jsx";
import KnowsGraph from "../screens/KnowsGraph.jsx";
import { Alerts, Dash, DocPage, Find, Sources, WhyPage, openWhy, pending, share, useLoad } from "./common.jsx";

const BASE = "me";
const open = openWhy(BASE);

function Brain() {
  const data = useData();
  const knows = data.knows.filter((k) => k.person === data.me);
  const max = Math.max(...knows.map((k) => k.score), 1);
  const me = data.person[data.me];
  return (
    <>
      <header className="step-head">
        <h1>My brain</h1>
        <p>The files and decisions you know, scored from your commits, reviews, docs and AI sessions. Only you and your
          admin can see this.</p>
      </header>
      {data.alerts.length > 0 && (
        <section className="card at-risk">
          <h2>Only you know these <span className="count">{data.alerts.length}</span></h2>
          <p className="muted small">The agent noticed nobody else knows these. Its brief, written from your own work, lists
            what a successor would need to ask you. Write it down in a doc, or pair with someone on it.</p>
          <Alerts alerts={data.alerts} base={BASE} />
        </section>
      )}
      {knows.length ? (
        <DataProvider data={{ ...data, people: [me], knows }}>
          <KnowsGraph sel={data.me} onPerson={() => {}} open={open} />
        </DataProvider>
      ) : (
        <section className="card empty">
          <h2>Your graph is empty</h2>
          <p className="muted">Add a design doc, research notes or a Claude Code session log, or connect the CLI. If your
            admin connected the company repo, your commits show up here too.</p>
          <a className="btn primary" href="#/me/sources">Add sources</a>
        </section>
      )}
      {knows.length > 0 && (
        <section className="card">
          <h2>You know <span className="count">{knows.length}</span></h2>
          {knows.map((k) => <Item key={k.item} item={k.item} open={open}><Score value={k.score} max={max} /></Item>)}
        </section>
      )}
    </>
  );
}

function Inherited({ id, reload }) {
  const data = useData();
  const { first } = data;
  const [busy, setBusy] = useState(null);
  const block = data.inherited.find((x) => x.person === id);
  const p = data.person[id];
  if (!block || !p) return <p className="muted">You did not succeed this person.</p>;
  const agenda = block.items.filter((i) => !i.others.length);
  const shared = block.items.filter((i) => i.others.length);
  const learned = agenda.filter((i) => i.learned).length;
  const theirs = data.knows.filter((k) => k.person === id);
  const decisions = theirs.filter((k) => k.kind === "Decision");

  const mark = async (item) => {
    setBusy(item);
    await api("brain/learned", { item }).finally(() => setBusy(null));
    reload();
  };

  return (
    <>
      <header className="step-head">
        <h1>{p.name}'s brain</h1>
        <p>{p.role}. {first(id)} left{p.last_day ? ` on ${fmt(p.last_day)}` : ""}. You are their successor, so you can read
          everything they knew, every decision they took part in, and why it was made.</p>
      </header>

      <section className="card">
        <div className="big">
          <span className="big-num">{learned} <span className="muted">/ {agenda.length}</span></span>
          <span>things only {first(id)} knew that you have picked up</span>
        </div>
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={agenda.length} aria-valuenow={learned}
          aria-label="Handover progress">
          <span style={{ width: `${agenda.length ? (learned / agenda.length) * 100 : 100}%` }} />
        </div>
      </section>

      <section className="card at-risk">
        <h2>Only {first(id)} knew these <span className="count">{agenda.length - learned} left</span></h2>
        {agenda.map((i) => (
          <div key={i.item} className="agenda-row">
            <Item item={i.item} open={open} />
            {i.learned ? <Pill tone="ok">learned</Pill> : (
              <button className="btn" disabled={busy === i.item} onClick={() => mark(i.item)}>Mark learned</button>
            )}
          </div>
        ))}
        {!agenda.length && <p className="muted">Nothing: someone else still knows everything {first(id)} knew.</p>}
      </section>

      {decisions.length > 0 && (
        <section className="card">
          <h2>Decisions {first(id)} took part in <span className="count">{decisions.length}</span></h2>
          <p className="muted small">Open one to see the chat, ticket, PR and AI session it came from.</p>
          {decisions.map((k) => <Item key={k.item} item={k.item} open={open} />)}
        </section>
      )}

      {shared.length > 0 && (
        <details className="card">
          <summary><b>Also known by someone else</b> <span className="count">{shared.length}</span></summary>
          {shared.map((i) => (
            <Item key={i.item} item={i.item} open={open}>
              <Pill>ask {i.others.map(first).join(", ")}</Pill>
            </Item>
          ))}
        </details>
      )}

      <h2 className="section-title">{first(id)}'s graph</h2>
      <DataProvider data={{ ...data, people: [p], knows: theirs }}>
        <KnowsGraph sel={id} onPerson={() => {}} open={open} />
      </DataProvider>
    </>
  );
}

function CompanyDocs() {
  const data = useData();
  return (
    <>
      <header className="step-head">
        <h1>Company docs</h1>
        <p>Design docs, ADRs, runbooks and research their authors shared with everyone. AI sessions and chat stay with
          the person who wrote them and their successors.</p>
      </header>
      <section className="card">
        <Sources sources={data.company_docs} base={BASE} who={(s) => s.author} extract={false} />
      </section>
    </>
  );
}

const toBase64 = (file) => new Promise((ok, fail) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",")[1]);
  r.onerror = fail;
  r.readAsDataURL(file);
});

function AddSources({ reload }) {
  const data = useData();
  const [log, setLog] = useState([]);
  const [token, setToken] = useState("");
  const [drag, setDrag] = useState(false);

  const send = async (files) => {
    for (const f of files) {
      setLog((l) => [{ name: f.name, state: "uploading…" }, ...l]);
      const done = (state) => setLog((l) => l.map((x) => (x.name === f.name ? { ...x, state } : x)));
      try {
        const res = await api("brain/upload", { name: f.name, data: await toBase64(f) });
        done(`added (${res.refs.length} source${res.refs.length > 1 ? "s" : ""})`);
      } catch (err) {
        done(err.message);
      }
    }
    reload();
  };

  const command = `python cli/ktbrain.py sync --server ${location.origin} --token ${token} --repo .`;
  const mcp = `claude mcp add ktbrain -- python cli/ktbrain.py mcp --server ${location.origin} --token ${token}`;
  return (
    <>
      <header className="step-head">
        <h1>Add sources</h1>
        <p>Everything you add builds your graph. Text is split into chunks inside FalkorDB, and decisions are pulled out
          when your admin has set up an AI provider. Docs are shared with the whole company unless you make them
          private; AI sessions stay with you, your successors and your admin.</p>
      </header>

      <label className={`card dropzone ${drag ? "over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); send([...e.dataTransfer.files]); }}>
        <input type="file" multiple accept=".md,.markdown,.txt,.pdf,.jsonl" className="visually-hidden"
          onChange={(e) => { send([...e.target.files]); e.target.value = ""; }} />
        <b>Drop files here or click to choose</b>
        <span className="muted small">Design docs, research notes and ADRs (.md, .txt, .pdf), or Claude Code session logs
          (.jsonl, from ~/.claude/projects). Up to 8 MB each. Passwords and API keys are redacted before storing.</span>
      </label>
      {log.length > 0 && (
        <section className="card">
          {log.map((x, i) => <div key={i} className="row"><code className="item-label">{x.name}</code><span className="meta">{x.state}</span></div>)}
        </section>
      )}

      <section className="card">
        <h2>Connect your laptop</h2>
        <p className="muted small">The <code>ktbrain</code> CLI reads your Claude Code sessions for one repo, strips them to
          prompts, answers and edited file paths, redacts secrets on your machine, and sends only that. It also gives
          Claude Code the agent's tools over MCP, so before it changes a file it can ask why the file is the way it is
          and who knows it, from what you can see here.</p>
        {token ? (
          <>
            <p className="small">Sync your sessions: run this from the repo you work in. The token is shown once.</p>
            <pre className="command">{command}</pre>
            <button className="btn" onClick={() => navigator.clipboard?.writeText(command)}>Copy command</button>
            <p className="small">Let Claude Code ask KT Brain (the same token):</p>
            <pre className="command">{mcp}</pre>
            <button className="btn" onClick={() => navigator.clipboard?.writeText(mcp)}>Copy command</button>
          </>
        ) : (
          <button className="btn primary" onClick={async () => setToken((await api("brain/cli-token", {})).token)}>Create a CLI token</button>
        )}
      </section>

      <section className="card">
        <h2>Your sources <span className="count">{data.sources.length}</span></h2>
        <Sources sources={data.sources} base={BASE} onShare={(s) => share(s).then(reload)} />
      </section>
    </>
  );
}

export default function Member({ path }) {
  const [section = "brain", id] = path;
  const [data, reload, error] = useLoad("brain", (d) => pending(d.sources));
  const nav = [
    ["brain", "My brain", data?.knows.filter((k) => k.person === data.me).length],
    ...(data?.inherited ?? []).map((x) => [`from/${x.person}`, `From ${data.people.find((p) => p.id === x.person)?.name.split(" ")[0]}`,
      x.items.filter((i) => !i.others.length && !i.learned).length]),
    ["docs", "Company docs", data?.company_docs.length],
    ["sources", "Add sources", data?.sources.length],
    ["ask", "Ask"],
  ];
  const current = section === "from" ? `from/${id}` : section;
  const page = {
    brain: <Brain />, from: <Inherited id={id} reload={reload} />, sources: <AddSources reload={reload} />,
    docs: <CompanyDocs />, doc: <DocPage id={id} />,
    ask: (
      <>
        <header className="step-head"><h1>Ask</h1><p>The agent answers from what you can see in the graph and cites every claim.</p></header>
        <Find base={BASE} hint="Searches docs shared with the company, plus your own AI sessions and chat and those of anyone you succeeded." />
      </>
    ),
    why: <WhyPage base={BASE} id={id} />,
  }[section] ?? <p className="muted">Nothing here.</p>;
  return <Dash base={BASE} nav={nav} current={current} data={data} error={error}>{page}</Dash>;
}
