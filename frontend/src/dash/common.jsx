// Pieces both dashboards use: the sidebar layout, data loading, why-trace page, search and the sources table.
import { useCallback, useEffect, useState } from "react";
import { DataProvider, Kind, Pill, api, fmt, go } from "../ui.jsx";
import { Snippet, terms } from "../screens/Ask.jsx";
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

export function Find({ hint }) {
  const [q, setQ] = useState("");
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
      <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Search docs, AI sessions and chat…" aria-label="Search" />
      <p className="muted small">{hint}</p>
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

// `onRemove` (admin only) adds a Remove button to uploaded sources
export function Sources({ sources, who, onRemove }) {
  if (!sources.length) return <p className="muted">No sources yet.</p>;
  return sources.map((s) => (
    <div key={s.ref} className="row">
      <Kind kind={s.kind} />
      <span className="item-label">{s.title || s.ref}<br />
        <span className="meta">{who ? `${who(s.person)} · ` : ""}{fmt(s.at)}{s.decisions ? ` · ${s.decisions} decisions` : ""}</span>
      </span>
      <span className="item-extra">
        <Pill tone={extractTone(s.extract)}>{extractText(s.extract)}</Pill>
        {onRemove && s.extract && <button className="btn" onClick={() => onRemove(s)}>Remove</button>}
      </span>
    </div>
  ));
}

export const pending = (sources) => sources?.some((s) => s.extract === "pending");
export const openWhy = (base) => (id) => go(base, "why", id);
