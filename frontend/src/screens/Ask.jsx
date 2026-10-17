import { useEffect, useState } from "react";
import { Cypher, Header, Kind, api, useData } from "../ui.jsx";

const SUGGEST = ["Why do payment retries happen 7 times?", "Who knows how the gateway key is rotated?",
  "How does canary rollback work?", "Why is Redis memory capped?"];
// the same words the API sends to the full-text index (backend/agent.py search_words), used here to highlight them
export const terms = (q) => q.toLowerCase().match(/[a-z0-9_]+/g)?.filter((w) => w.length > 2) ?? [];

export function Snippet({ text, words }) {
  const lower = text.toLowerCase();
  const found = words.map((w) => lower.indexOf(w)).filter((i) => i >= 0); // none when the index matched a stem
  const at = found.length ? Math.max(0, Math.min(...found) - 90) : 0;
  const part = (at ? "…" : "") + text.slice(at, at + 260).replace(/\s+/g, " ") + "…";
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <p className="snippet">{part.split(re).map((s, i) => (i % 2 ? <mark key={i}>{s}</mark> : s))}</p>;
}

// Agent text with [id] citations. `link(id)` returns a click handler for ids that can be opened, or null.
export function Cited({ text, link }) {
  return text.split("\n").map((line, i) => (
    <p key={i} className="answer-line">
      {line.split(/(\[[^[\]]+\])/).map((s, j) => {
        if (!/^\[.+\]$/.test(s)) return s;
        const id = s.slice(1, -1);
        const onClick = link?.(id);
        return onClick ? <button key={j} className="cite" onClick={onClick}>{id}</button>
          : <code key={j} className="cite">{id}</code>;
      })}
    </p>
  ));
}

// The agent's answer to one question (`path` is the API path with the question in it, or null before asking)
export function AgentAnswer({ path, link }) {
  const [res, setRes] = useState(null);
  useEffect(() => {
    setRes(null);
    if (!path) return;
    let live = true;
    api(path).then((r) => live && setRes(r)).catch((e) => live && setRes({ note: e.message, cited: [] }));
    return () => { live = false; };
  }, [path]);
  if (!path) return null;
  return (
    <section className="card answer" aria-live="polite">
      <h2>Agent</h2>
      {!res ? <p className="muted">Searching the graph and following it to the decisions and people behind the hits…</p> : (
        <>
          {res.answer ? <Cited text={res.answer} link={link} /> : <p className="muted">{res.note}</p>}
          {res.cited.length > 0 && (
            <>
              <p className="muted small">{res.answer ? "Evidence it cited (every line must cite the graph, or it is dropped)" : "Evidence"}</p>
              {res.cited.map((c) => (
                <div key={c.id} className="row">
                  <Kind kind={c.kind} />
                  <span className="item-label">{c.title}</span>
                  <code className="item-extra small">{c.id}</code>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </section>
  );
}

export default function Ask({ open }) {
  const { whyFor } = useData();
  const [q, setQ] = useState(SUGGEST[0]);
  const [asked, setAsked] = useState(SUGGEST[0]);
  const [hits, setHits] = useState([]);
  const words = terms(asked);
  useEffect(() => {
    const ask = new AbortController();
    fetch(`/api/search?q=${encodeURIComponent(asked)}`, { signal: ask.signal })
      .then((r) => r.json()).then(setHits).catch(() => {});
    return () => ask.abort();
  }, [asked]);
  const pick = (s) => { setQ(s); setAsked(s); };

  return (
    <>
      <Header title="Ask the agent">
        The agent searches the <code>Chunk</code> nodes, follows the graph from each hit to the decisions it records and
        the people who still know them, and answers from that evidence alone. Every line has to cite a node it was
        shown; anything else is dropped.
      </Header>

      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); setAsked(q.trim()); }}>
        <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Ask how something works, why it was decided, or who knows it…" aria-label="Question" />
        <button className="btn primary" disabled={!q.trim()}>Ask</button>
      </form>
      <p className="chips">
        {SUGGEST.map((s) => <button key={s} className="chip" onClick={() => pick(s)}>{s}</button>)}
      </p>

      <AgentAnswer path={asked && `ask?q=${encodeURIComponent(asked)}`}
        link={(id) => (whyFor(id) === id ? () => open(id) : null)} />

      {hits.length > 0 && <h2 className="section-title">Matching chunks</h2>}
      {hits.map((c) => (
        <section key={`${c.ref}#${c.seq}`} className="card hit">
          <div className="hit-head">
            <Kind kind={c.kind} />
            <b>{c.title || c.text.split("\n")[0].slice(0, 80)}</b>
            <span className="muted small">{c.ref} · chunk {c.seq + 1}</span>
          </div>
          <Snippet text={c.text} words={words} />
          {c.files.length > 0 && <p className="chips">{c.files.map((f) => <code key={f} className="file-chip">{f}</code>)}</p>}
        </section>
      ))}

      <Cypher>{`
// 1. full-text hits
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (node)-[:MENTIONS]->(f:File)
RETURN s.ref, node.text, collect(f.path) AS files ORDER BY score DESC LIMIT 6

// 2. walk from the hits to the decisions behind them, and who still knows them
MATCH (d:Decision) WHERE d.status <> 'proposed'
WITH d, [(s:Source)-[:RECORDS]->(d) | s.ref] AS recorded_in, [(d)-[:ABOUT]->(f:File) | f.path] AS about
WHERE any(r IN recorded_in WHERE r IN $refs) OR any(f IN about WHERE f IN $files)
RETURN d.id, d.what, d.why,
       [(p:Person {active: true})-[:KNOWS]->(d) | p.name] AS knowers,
       [(n:Decision)-[:SUPERSEDES]->(d) | n.id] AS superseded_by`}</Cypher>
    </>
  );
}
