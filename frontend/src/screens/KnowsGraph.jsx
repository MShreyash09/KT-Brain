import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { Skeleton, useData } from "../ui.jsx";

// loaded only on pages that show a graph, so the landing page stays light
const ForceGraph2D = lazy(() => import("react-force-graph-2d"));

// taller on big screens, never so tall the legend falls off a laptop screen
const HEIGHT = Math.round(Math.min(Math.max(window.innerHeight - 330, 480), 820));

// People, the files and decisions they KNOW, and which file each decision is ABOUT.
function build(data) {
  const { first, isDecision } = data;
  const radar = new Set((data.radar ?? []).map((r) => r.item));
  const people = data.people.filter((p) => data.knows.some((k) => k.person === p.id));
  const items = [...new Set(data.knows.map((k) => k.item))];
  const nodes = [
    ...people.map((p) => ({ id: `p:${p.id}`, person: p.id, text: first(p.id), leaving: !!p.last_day || p.active === false })),
    ...items.map((i) => ({ id: i, item: i, text: isDecision(i) ? i : i.split("/").pop(), decision: isDecision(i),
      superseded: data.decisions[i]?.status === "superseded", only: radar.has(i) })),
  ];
  const max = Math.max(...data.knows.map((k) => k.score));
  const links = [
    ...data.knows.map((k) => ({ source: `p:${k.person}`, target: k.item, w: 0.6 + (k.score / max) * 2.4 })),
    ...Object.values(data.decisions).flatMap((d) => d.about.filter((f) => items.includes(f) && items.includes(d.id))
      .map((f) => ({ source: d.id, target: f, about: true, w: 0.8 }))),
  ];
  return { nodes, links };
}

// The theme's colours for the canvas, read again when the light/dark toggle flips data-theme.
function readColors() {
  const s = getComputedStyle(document.documentElement);
  const v = (name) => s.getPropertyValue(name).trim();
  return { text: v("--text"), muted: v("--text-2"), surface: v("--surface"), surface2: v("--surface-2"), border: v("--border"),
    accent: v("--accent"), accentSoft: v("--accent-soft"), risk: v("--risk"), riskSoft: v("--risk-soft") };
}

function useColors() {
  const [colors, setColors] = useState(readColors);
  useEffect(() => {
    const o = new MutationObserver(() => setColors(readColors()));
    o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => o.disconnect();
  }, []);
  return colors;
}

const end = (x) => (typeof x === "object" ? x.id : x); // a link end: an id before the simulation starts, a node after

// A live force-directed graph, like the FalkorDB Browser: scroll to zoom, drag to pan, drag a node to pin it,
// hover to light up its neighbours. Labels appear as you zoom in, so a big workspace stays readable.
export default function KnowsGraph({ sel, onPerson, open }) {
  const data = useData();
  const { label, whyFor } = data;
  const g = useMemo(() => build(data), [data]);
  const colors = useColors();
  const box = useRef(null);
  const fg = useRef(null);
  const fitted = useRef(false);
  const [width, setWidth] = useState(800);
  const [hover, setHover] = useState(null);

  const neighbours = useMemo(() => {
    const m = new Map(g.nodes.map((n) => [n.id, new Set([n.id])]));
    for (const l of g.links) {
      m.get(end(l.source))?.add(end(l.target));
      m.get(end(l.target))?.add(end(l.source));
    }
    return m;
  }, [g]);

  useEffect(() => {
    if (!box.current) return;
    const o = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    o.observe(box.current);
    return () => o.disconnect();
  }, []);

  useEffect(() => {
    fitted.current = false;
    fg.current?.d3Force("charge")?.strength(-140);
    fg.current?.d3Force("link")?.distance((l) => (l.about ? 35 : 80));
  }, [g]);

  if (!g.nodes.length) return <p className="muted">No knowledge yet.</p>;

  const focus = hover ?? (sel ? `p:${sel}` : null);
  const near = (focus && neighbours.get(focus)) || new Set();
  const lit = (l) => focus && (end(l.source) === focus || end(l.target) === focus);
  const act = (n) => (n.person ? onPerson(n.person) : whyFor(n.item) && open(whyFor(n.item)));
  const zoom = (f) => fg.current?.zoom(fg.current.zoom() * f, 250);

  const draw = (n, ctx, scale) => {
    const r = n.person ? 8 : n.decision ? 4.5 : 4;
    ctx.globalAlpha = hover && !near.has(n.id) ? 0.12 : n.superseded ? 0.45 : 1;
    ctx.beginPath();
    if (n.decision) ctx.rect(n.x - r, n.y - r, r * 2, r * 2);
    else ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = n.leaving ? colors.riskSoft : n.person || n.decision ? colors.accentSoft : colors.surface2;
    ctx.fill();
    ctx.lineWidth = n.only ? 1.6 : 1;
    ctx.strokeStyle = n.only || n.leaving ? colors.risk : n.person || n.decision ? colors.accent : colors.muted;
    ctx.stroke();
    if (n.person) {
      ctx.fillStyle = n.leaving ? colors.risk : colors.accent;
      ctx.font = "600 8px Archivo, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(n.text[0], n.x, n.y + 0.5);
    }
    // labels: always for people, for the hovered node's neighbours, for everything else once zoomed in (a selected
    // person can know hundreds of files, so selection alone lights their links but doesn't label them all)
    if (n.person || scale > 1.8 || (hover && near.has(n.id))) {
      const size = Math.max(10 / scale, 2.5);
      ctx.font = `${n.person ? 600 : 400} ${size}px Archivo, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = n.person ? colors.text : colors.muted;
      ctx.fillText(n.text, n.x, n.y + r + 2);
    }
    ctx.globalAlpha = 1;
  };

  return (
    <section className="card graph-card">
      <div className="graph-tools">
        <span className="muted small">{g.nodes.filter((n) => n.person).length} people · {g.nodes.filter((n) => !n.person).length} files
          and decisions · scroll to zoom, drag to pan, drag a node to pin it</span>
        <span className="graph-buttons">
          <button className="btn" onClick={() => zoom(1.4)} aria-label="Zoom in">+</button>
          <button className="btn" onClick={() => zoom(1 / 1.4)} aria-label="Zoom out">−</button>
          <button className="btn" onClick={() => fg.current?.zoomToFit(400, 40)}>Fit</button>
        </span>
      </div>
      <div ref={box} className="graph-canvas" style={{ cursor: hover ? "pointer" : "grab" }}>
        <Suspense fallback={<div style={{ padding: 16, height: HEIGHT }}><Skeleton lines={6} /></div>}>
        <ForceGraph2D
          ref={fg}
          graphData={g}
          width={width}
          height={HEIGHT}
          backgroundColor="rgba(0,0,0,0)"
          nodeCanvasObject={draw}
          nodePointerAreaPaint={(n, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.person ? 11 : 7, 0, 2 * Math.PI);
            ctx.fill();
          }}
          nodeLabel={(n) => (n.person ? `${n.text}: click to see what they know`
            : n.decision ? `${n.item} ${label(n.item)}` : n.item)}
          linkColor={(l) => (lit(l) ? colors.accent : colors.border)}
          linkWidth={(l) => (lit(l) ? l.w + 0.6 : l.w)}
          linkLineDash={(l) => (l.about ? [3, 3] : null)}
          onNodeHover={(n) => setHover(n?.id ?? null)}
          onNodeClick={act}
          onNodeDragEnd={(n) => { n.fx = n.x; n.fy = n.y; }}
          onBackgroundClick={() => setHover(null)}
          cooldownTicks={150}
          onEngineStop={() => {
            if (!fitted.current) fg.current?.zoomToFit(400, 40);
            fitted.current = true;
          }}
        />
        </Suspense>
      </div>
      <p className="legend muted small">
        <span><i className="sw sw-person" /> person</span>
        <span><i className="sw sw-leaving" /> leaving</span>
        <span><i className="sw" /> file</span>
        <span><i className="sw sw-decision" /> decision</span>
        <span><i className="sw sw-only" /> only one person knows it</span>
        <span>line width = KNOWS score · dashed = decision is about that file · click an item for its why-trace</span>
      </p>
    </section>
  );
}
