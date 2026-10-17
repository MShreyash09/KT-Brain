// Pieces both dashboards use: the sidebar layout, data loading, why-trace page, search and the sources table.
import { useCallback, useEffect, useState } from "react";
import { DataProvider, Kind, Pill, api, fmt, go, useData } from "../ui.jsx";
import { AgentAnswer, Cited, Snippet, terms } from "../screens/Ask.jsx";
import { Trace } from "../screens/Why.jsx";

// GET once, plus a reload() for after a change; `poll` re-fetches every 3 s while it returns true
export function useLoad(path, poll) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const reload = useCallback(() => api(path).then(setData).catch((e) => setError(e.message)), [path]);
  useEffect(() => { reload(); }, [reload]);
  const busy = data && poll?.(data);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [busy, reload]);
  return [data, reload, error];
}

export function Dash({ base, nav, current, data, error, children }) {
  return (
    <div className="shell">
      <nav className="steps" aria-label="Dashboard">
        {nav.map(([id, name, count]) => (
          <a key={id} href={`#/${base}/${id}`} aria-current={id === current ? "page" : undefined}>
            {name}
            {count ? <span className="count">{count}</span> : null}
          </a>
        ))}
      </nav>
      <main className="content">
        {error ? <p className="form-error">{error}</p> : !data ? <p className="muted">Loading…</p> : (
          <DataProvider data={data}>{children}</DataProvider>
        )}
      </main>
    </div>
  );
}

export function WhyPage({ base, id }) {
  const [res, , error] = useLoad(`why/${encodeURIComponent(id)}`);
  return (
    <>
      <p><a href="#" onClick={(e) => { e.preventDefault(); history.back(); }}>← Back</a></p>
      <header className="step-head">
        <h1>Why is it like this?</h1>
        <p>{id}: every path from this decision to the sources that recorded it.</p>
      </header>
      {error && <p className="form-error">{error}</p>}
      {res && <Trace d={res.decision} t={res.trace} />}
      {res && !res.trace.sources.length && <p className="muted">No source records this decision yet.</p>}
    </>
  );
}

// A cited id opens its why-trace (a decision in this view) or its full text (a source such as pr:124 or doc:…)
const SOURCE_REF = /^(pr|ticket|thread|session|doc):/;
export function citeLink(base, decisions) {
  return (id) => (id in decisions ? () => go(base, "why", id)
    : SOURCE_REF.test(id) ? () => go(base, "doc", encodeURIComponent(id)) : null);
}

export function Find({ base, hint }) {
  const { decisions } = useData();
  const [q, setQ] = useState("");
  const [asked, setAsked] = useState("");
  const [hits, setHits] = useState(null);
  useEffect(() => {
    if (!terms(q).length) return setHits(null);
    const ask = new AbortController();
    const t = setTimeout(() => fetch(`/api/find?q=${encodeURIComponent(q)}`, { signal: ask.signal })
      .then((r) => r.json()).then(setHits).catch(() => {}), 200);
    return () => { clearTimeout(t); ask.abort(); };
  }, [q]);
  return (
    <>
      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); setAsked(q.trim()); }}>
        <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Ask how something works, why it was decided, or who knows it…" aria-label="Question" />
        <button className="btn primary" disabled={!q.trim()}>Ask the agent</button>
      </form>
      <p className="muted small">{hint} Matching chunks show as you type; press Ask for an answer that cites them.</p>
      <AgentAnswer path={asked && `agent?q=${encodeURIComponent(asked)}`} link={citeLink(base, decisions)} />
      {hits && !hits.length && <p className="muted">Nothing you can see mentions that.</p>}
      {hits?.map((c) => (
        <section key={`${c.ref}#${c.seq}`} className="card hit">
          <div className="hit-head">
            <Kind kind={c.kind} />
            <b>{c.title || c.text.split("\n")[0].slice(0, 80)}</b>
            <span className="muted small">chunk {c.seq + 1}</span>
          </div>
          <Snippet text={c.text} words={terms(q)} />
          {c.files.length > 0 && <p className="chips">{c.files.map((f) => <code key={f} className="file-chip">{f}</code>)}</p>}
        </section>
      ))}
    </>
  );
}

const extractTone = (x) => (!x || x === "off" ? "muted" : x.startsWith("failed") ? "risk" : x === "pending" ? "warn" : "ok");
const extractText = (x) => (!x ? "fixture" : x === "off" ? "no AI provider" : x === "pending" ? "extracting…" : x);

const docLink = (base, ref) => `#/${base}/doc/${encodeURIComponent(ref)}`;

// Titles open the full text. `onRemove` (admin only) adds a Remove button to uploaded sources; `onShare` a
// share/make-private button to docs. `extract: false` hides the extraction status (the company docs list).
export function Sources({ sources, base, who, onRemove, onShare, extract = true }) {
  if (!sources.length) return <p className="muted">No sources yet.</p>;
  return sources.map((s) => (
    <div key={s.ref} className="row">
      <Kind kind={s.kind} />
      <span className="item-label"><a href={docLink(base, s.ref)}>{s.title || s.ref}</a><br />
        <span className="meta">{who ? `${who(s)} · ` : ""}{fmt(s.at)}{s.decisions ? ` · ${s.decisions} decisions` : ""}</span>
      </span>
      <span className="item-extra">
        {extract && <Pill tone={extractTone(s.extract)}>{extractText(s.extract)}</Pill>}
        {onShare && s.kind === "Doc" && (
          <button className="btn" onClick={() => onShare(s)} title={s.shared ? "Everyone in the company can read it now" : "Only you, your successors and admins can read it now"}>
            {s.shared ? "Make private" : "Share with company"}
          </button>
        )}
        {onRemove && s.extract && <button className="btn" onClick={() => onRemove(s)}>Remove</button>}
      </span>
    </div>
  ));
}

export const share = (s) => api("source/share", { ref: s.ref, shared: !s.shared });

export function DocPage({ id }) {
  const [res, , error] = useLoad(`source?ref=${encodeURIComponent(id)}`);
  return (
    <>
      <p><a href="#" onClick={(e) => { e.preventDefault(); history.back(); }}>← Back</a></p>
      {error && <p className="form-error">{error}</p>}
      {res && (
        <>
          <header className="step-head"><h1>{res.title || res.ref}</h1></header>
          <section className="card"><pre className="doc-text">{res.text}</pre></section>
        </>
      )}
    </>
  );
}

const STATE = { open: ["risk", "only one person knows it"], resolved: ["ok", "resolved: someone else knows it now"],
  lost: ["muted", "lost: they left first"] };

// The agent's radar alerts, each with its KT brief. `who` names the only knower (left out on a member's own page).
export function Alerts({ alerts, base, who }) {
  const data = useData();
  const link = citeLink(base, data.decisions);
  return alerts.map((a) => (
    <details key={a.id} className="alert" open={a.status === "open" && alerts.length < 4}>
      <summary>
        <Kind kind={a.kind} />
        <span className="item-label">{a.kind === "Decision" ? <><b>{a.item}</b> {data.label(a.item)}</> : <code>{a.item}</code>}</span>
        <span className="item-extra">
          {who && <span className="meta">{who(a.person)}</span>}
          <Pill tone={STATE[a.status][0]}>{STATE[a.status][1]}</Pill>
          <span className="meta">{fmt(new Date(a.created * 1000).toISOString().slice(0, 10))}</span>
        </span>
      </summary>
      <div className="brief">
        {a.brief ? <Cited text={a.brief} link={link} /> : (
          <p className="muted small">No AI provider, so no brief. Evidence: {a.refs.join(", ") || "none"}.</p>
        )}
      </div>
    </details>
  ));
}

export const pending = (sources) => sources?.some((s) => s.extract === "pending");
export const openWhy = (base) => (id) => go(base, "why", id);
