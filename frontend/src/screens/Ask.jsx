import { useEffect, useState } from "react";
import { Cypher, Header, Kind, api, useData } from "../ui.jsx";

const SUGGEST = ["Why do payment retries happen 7 times?", "What do we lose if Arjun leaves?",
  "Who should I ask about retry.py?", "Where are we most at risk of losing knowledge?", "How does canary rollback work?"];
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

const argText = (args) => Object.values(args).map((v) => JSON.stringify(v)).join(", ");

// The tools the agent ran, in order, and what each found (or why it found nothing)
function Steps({ steps }) {
  return (
    <ol className="steps-run">
      {steps.map((s, i) => (
        <li key={i}>
          <code>{s.tool}({argText(s.args)})</code>{" "}
          <span className="muted small">
            {s.error ? s.error : s.found.length ? `→ ${s.found.length} found` : "→ nothing"}
          </span>
        </li>
      ))}
    </ol>
  );
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
      {!res ? <p className="muted">The agent is picking tools and walking the graph…</p> : (
        <>
          {res.answer && <Cited text={res.answer} link={link} />}
          {res.note && <p className="muted">{res.note}</p>}
          {res.steps?.length > 0 && (
            <details className="how" open={!res.answer}>
              <summary className="muted small">How it got there: {res.steps.length} tool call{res.steps.length > 1 ? "s" : ""}</summary>
              <Steps steps={res.steps} />
            </details>
          )}
          {res.cited.length > 0 && (
            <>
              <p className="muted small">{res.answer ? "Evidence it cited, and the graph path to each (every line must cite the graph, or it is dropped)" : "Evidence"}</p>
              {res.cited.map((c) => (
                <div key={c.id} className="row cited-row">
                  <Kind kind={c.kind} />
                  <span className="item-label">{c.title || c.id}
                    {c.paths?.slice(0, 2).map((p) => <code key={p} className="path">{p}</code>)}
                  </span>
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
        The agent never writes Cypher. It picks from five tools built on fixed queries (full-text search, the why-trace,
        who knows an item, a departure dry run, the PageRank radar), and every name it passes is looked up in the graph
        first, so a misspelt file gets suggestions instead of a guess. It answers from what the tools return, and every
        line has to cite a node it was shown; anything else is dropped.
      </Header>

      <form className="ask-form" onSubmit={(e) => { e.preventDefault(); setAsked(q.trim()); }}>
        <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Ask how something works, why it was decided, or who knows it…" aria-label="Question" />
        <button className="btn primary" disabled={!q.trim()}>Ask</button>
      </form>
      <p className="chips">
        {SUGGEST.map((s) => <button key={s} className="chip" onClick={() => pick(s)}>{s}</button>)}
      </p>
      <p className="muted small">The agent runs on a free AI tier that answers a few questions a minute. When it's busy
        you still get the evidence and graph paths, just no written answer.</p>

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
// the tools the model can call; it only fills in their arguments
search(query)      CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
                   MATCH (node)-[:PART_OF]->(s:Source) ... then the decisions s RECORDS, and who KNOWS them
why(item)          MATCH (s:Source)-[:RECORDS]->(:Decision {id: $id}), (d)-[:SUPERSEDES]->(old)<-[:CAUSED_BY]-(i:Incident) ...
                   or for a file: MATCH (d:Decision)-[:ABOUT]->(:File {path: $path}), (p)-[:AUTHORED]->(c:Commit)-[:CHANGED]->(f)
who_knows(item)    MATCH (p:Person)-[e:KNOWS|LEARNED]->(k) RETURN p.name, e.score, e.last_touched
if_leaves(people)  GRAPH.COPY, then SET p.active = false and find what no active Person KNOWS any more
radar()            CALL algo.pageRank('Service', 'DEPENDS_ON') over items exactly one active Person KNOWS

// before any tool runs, each name is resolved: MATCH (k) WHERE k:File OR k:Decision RETURN coalesce(k.id, k.path)`}</Cypher>
    </>
  );
}
