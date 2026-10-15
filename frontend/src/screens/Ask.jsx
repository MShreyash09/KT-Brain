import { useEffect, useState } from "react";
import { Cypher, Header, Kind } from "../ui.jsx";

const SUGGEST = ["retries", "canary rollback", "pause cap", "taste quiz", "Redis memory"];
// the same words the API sends to the full-text index (backend/app.py search), used here to highlight them
export const terms = (q) => q.toLowerCase().match(/[a-z0-9_]+/g)?.filter((w) => w.length > 2) ?? [];

export function Snippet({ text, words }) {
  const lower = text.toLowerCase();
  const found = words.map((w) => lower.indexOf(w)).filter((i) => i >= 0); // none when the index matched a stem
  const at = found.length ? Math.max(0, Math.min(...found) - 90) : 0;
  const part = (at ? "…" : "") + text.slice(at, at + 260).replace(/\s+/g, " ") + "…";
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <p className="snippet">{part.split(re).map((s, i) => (i % 2 ? <mark key={i}>{s}</mark> : s))}</p>;
}

export default function Ask() {
  const [q, setQ] = useState("retries");
  const [hits, setHits] = useState([]);
  const words = terms(q);
  useEffect(() => {
    const ask = new AbortController();
    fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: ask.signal })
      .then((r) => r.json()).then(setHits).catch(() => {});
    return () => ask.abort();
  }, [q]);

  return (
    <>
      <Header title="Ask the docs">
        Docs, AI sessions and chat are stored as <code>Chunk</code> nodes inside FalkorDB, with a full-text index.
        There is no second database. Each hit links back to its source and the files it mentions.
      </Header>

      <input className="search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Search docs, AI sessions and chat…" aria-label="Search" />
      <p className="chips">
        {SUGGEST.map((s) => <button key={s} className="chip" onClick={() => setQ(s)}>{s}</button>)}
      </p>

      {q && !hits.length && <p className="muted">No chunk mentions that.</p>}
      {hits.map((c) => (
        <section key={`${c.ref}#${c.seq}`} className="card hit">
          <div className="hit-head">
            <Kind kind={c.kind} />
            <b>{c.title || c.text.split("\n")[0].slice(0, 80)}</b>
            <span className="muted small">chunk {c.seq + 1}</span>
          </div>
          <Snippet text={c.text} words={words} />
          {c.files.length > 0 && <p className="chips">{c.files.map((f) => <code key={f} className="file-chip">{f}</code>)}</p>}
        </section>
      ))}

      <Cypher>{`
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (node)-[:MENTIONS]->(f:File)
RETURN s.ref AS source, node.seq AS chunk, score, collect(f.path) AS files
ORDER BY score DESC LIMIT 6`}</Cypher>
    </>
  );
}
