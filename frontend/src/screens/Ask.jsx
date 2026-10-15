import { useState } from "react";
import { Cypher, Header, Kind, data } from "../ui.jsx";

const SUGGEST = ["retries", "canary rollback", "pause cap", "taste quiz", "Redis memory"];
const STOP = new Set(["the", "and", "why", "are", "is", "what", "how", "who", "does", "our", "for", "with"]);

// ponytail: in-browser word match over the exported chunks, stands in for db.idx.fulltext.queryNodes until the API exists
function search(q) {
  const words = q.toLowerCase().match(/[a-z0-9_.]+/g)?.filter((w) => w.length > 2 && !STOP.has(w)) ?? [];
  if (!words.length) return { words, hits: [] };
  const hits = data.chunks
    .map((c) => {
      const text = c.text.toLowerCase();
      return { c, score: words.reduce((s, w) => s + text.split(w).length - 1, 0), all: words.every((w) => text.includes(w)) };
    })
    .filter((h) => h.score > 0)
    .sort((a, b) => b.all - a.all || b.score - a.score)
    .slice(0, 6);
  return { words, hits };
}

function Snippet({ text, words }) {
  const lower = text.toLowerCase();
  const at = Math.max(0, Math.min(...words.map((w) => lower.indexOf(w)).filter((i) => i >= 0)) - 90);
  const part = (at ? "…" : "") + text.slice(at, at + 260).replace(/\s+/g, " ") + "…";
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return <p className="snippet">{part.split(re).map((s, i) => (i % 2 ? <mark key={i}>{s}</mark> : s))}</p>;
}

export default function Ask() {
  const [q, setQ] = useState("retries");
  const { words, hits } = search(q);

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
      {hits.map(({ c }) => (
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
ORDER BY score DESC LIMIT 5`}</Cypher>
    </>
  );
}
