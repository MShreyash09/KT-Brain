import { useMemo, useState } from "react";
import { data, first, isDecision, label, whyFor } from "../ui.jsx";

const W = 880, H = 540, PAD = 28;

// People, the files and decisions they KNOW, and which file each decision is ABOUT.
function build() {
  const radar = new Set(data.radar.map((r) => r.item));
  const people = data.people.filter((p) => data.knows.some((k) => k.person === p.id));
  const items = [...new Set(data.knows.map((k) => k.item))];
  const nodes = [
    ...people.map((p) => ({ id: `p:${p.id}`, person: p.id, text: first(p.id), leaving: !!p.last_day })),
    ...items.map((i) => ({ id: i, item: i, text: isDecision(i) ? i : i.split("/").pop(), decision: isDecision(i),
      superseded: data.decisions[i]?.status === "superseded", only: radar.has(i) })),
  ];
  const max = Math.max(...data.knows.map((k) => k.score));
  const edges = [
    ...data.knows.map((k) => ({ a: `p:${k.person}`, b: k.item, w: 1 + (k.score / max) * 3 })),
    ...Object.values(data.decisions).flatMap((d) => d.about.filter((f) => items.includes(f) && items.includes(d.id))
      .map((f) => ({ a: d.id, b: f, about: true }))),
  ];
  return { nodes, edges };
}

// ponytail: plain O(n²) force layout run once (~50 nodes); swap for d3-force if workspaces grow to hundreds of nodes
function layout({ nodes, edges }) {
  const at = Object.fromEntries(nodes.map((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length;
    return [n.id, Object.assign(n, { x: W / 2 + 300 * Math.cos(a), y: H / 2 + 200 * Math.sin(a), vx: 0, vy: 0 })];
  }));
  for (let t = 0; t < 400; t++) {
    const k = 1 - t / 400;
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy + 1;
        const f = (40000 / d2) * k;
        a.vx -= dx * f / Math.sqrt(d2); a.vy -= dy * f / Math.sqrt(d2);
        b.vx += dx * f / Math.sqrt(d2); b.vy += dy * f / Math.sqrt(d2);
      }
    for (const e of edges) {
      const a = at[e.a], b = at[e.b], dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
      const f = ((d - (e.about ? 55 : 110)) * 0.04 * k) / d;
      a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    for (const n of nodes) {
      n.vx += (W / 2 - n.x) * 0.003; n.vy += (H / 2 - n.y) * 0.0045;
      n.x = Math.min(W - PAD, Math.max(PAD, n.x + (n.vx *= 0.55)));
      n.y = Math.min(H - PAD, Math.max(PAD, n.y + (n.vy *= 0.55)));
    }
  }
  return at;
}

export default function KnowsGraph({ sel, onPerson, open }) {
  const g = useMemo(build, []);
  const at = useMemo(() => layout(g), [g]);
  const [hover, setHover] = useState(null);
  const focus = hover ?? `p:${sel}`;
  const near = new Set([focus, ...g.edges.flatMap((e) => (e.a === focus ? [e.b] : e.b === focus ? [e.a] : []))]);

  const act = (n) => (n.person ? onPerson(n.person) : whyFor(n.item) && open(whyFor(n.item)));

  return (
    <section className="card graph-card">
      <svg viewBox={`0 0 ${W} ${H}`} className="kgraph" role="img"
        aria-label="Knowledge graph: people linked to the files and decisions they know">
        {g.edges.map((e, i) => {
          const a = at[e.a], b = at[e.b], lit = e.a === focus || e.b === focus;
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={e.w ?? 1}
            className={`edge ${e.about ? "about" : ""} ${lit ? "lit" : ""}`} />;
        })}
        {g.nodes.map((n) => {
          const p = at[n.id];
          const cls = ["node", n.person ? "is-person" : n.decision ? "is-decision" : "is-file", n.leaving && "leaving",
            n.only && "only", n.superseded && "superseded", hover && !near.has(n.id) && "dim"].filter(Boolean).join(" ");
          return (
            <g key={n.id} className={cls} transform={`translate(${p.x},${p.y})`} tabIndex={0} role="button"
              onClick={() => act(n)} onKeyDown={(e) => e.key === "Enter" && act(n)}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}>
              <title>{n.person ? `${n.text}: click to see what they know` : `${n.decision ? `${n.item} ${label(n.item)}` : n.item}`}</title>
              {n.decision ? <rect x={-7} y={-7} width={14} height={14} rx={3} /> : <circle r={n.person ? 15 : 6} />}
              {n.person ? <text dy={4} className="initial">{n.text[0]}</text> : null}
              <text dy={n.person ? 30 : 18} className="lbl">{n.text}</text>
            </g>
          );
        })}
      </svg>
      <p className="legend muted small">
        <span><i className="sw sw-person" /> person</span>
        <span><i className="sw sw-leaving" /> leaving</span>
        <span><i className="sw" /> file</span>
        <span><i className="sw sw-decision" /> decision</span>
        <span><i className="sw sw-only" /> only one person knows it</span>
        <span>line width = KNOWS score · dashed = decision is about that file</span>
      </p>
    </section>
  );
}
