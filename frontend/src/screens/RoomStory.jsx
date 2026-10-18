import { useEffect, useState } from "react";
import { motion, MotionConfig } from "motion/react";

// The landing hero: TiffinBox's office as a floor plan, told in five acts.
// Names, dates and decisions D1 / D8 / D13 come from data/tiffinbox (answer_key.json, people.json).
const ACTS = [
  {
    date: "Before", title: "Six teams ship TiffinBox", ms: 5500,
    text: "Six teams build one product. Every commit, review and chat thread is knowledge, and most of it lives only in people's heads.",
  },
  {
    date: "Sep 15", title: "Arjun and Priya resign", ms: 5000,
    text: "Arjun built payment retries. Priya runs deploys and secrets. When they walk out, everything only they knew goes with them.",
  },
  {
    date: "Sep 22", title: "Meera joins payments", ms: 7500,
    text: "Meera takes over payments. The code says retries = 7, but nothing says why, and the two people who could answer are gone.",
  },
  {
    date: "Oct 6", title: "A cleanup PR breaks checkout", ms: 6000,
    text: "Seven retries look like a mistake, so Meera's cleanup PR sets them to 3. The gateway's next deploy drops its webhooks for five minutes, and payments start failing.",
  },
  {
    date: "Oct 6", title: "KT Brain answers why", ms: 10000,
    text: "KT Brain kept Arjun's and Priya's reasoning as a graph. Meera asks why, gets the answer with its sources, and puts the fix back.",
  },
];

const PODS = [
  ["Payments", 230, 170], ["Platform", 600, 170], ["Web", 970, 170],
  ["Recommendations", 230, 490], ["Product", 600, 490], ["Mobile", 970, 490],
];
const SEATS = [[-50, -62], [50, -62], [-50, 62], [50, 62]];
// everyone who stays, one per desk: [x, y, name]. Mobile has no one in data/tiffinbox, so its seat stays unnamed
const TEAM = [
  [920, 108, "Kavya"],
  [180, 428, "Rohan"],
  [550, 428, "Neha"],
  [920, 428],
];
const MODULES = [["App", 330], ["Orders", 510], ["Payments", 690], ["Gateway", 870]];
const ARJUN = [180, 108], PRIYA = [650, 108], MEERA = [280, 232];

// the aisle out of the room and through the door on the right wall
const DOOR = [[1080, 270], [1080, 485], [1195, 485]];
const IN = [...DOOR].reverse();

// keyframes for walking a polyline relative to `anchor`; times follow distance so the pace is even
function walk(points, [ax, ay]) {
  const d = [0];
  for (let i = 1; i < points.length; i++) {
    d.push(d[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  }
  return { x: points.map((p) => p[0] - ax), y: points.map((p) => p[1] - ay), times: d.map((v) => v / d.at(-1)) };
}

const leave = (points, delay) => {
  const k = walk(points, points[0]);
  return {
    here: { x: 0, y: 0, opacity: 1, transition: { x: { duration: 0 }, y: { duration: 0 }, opacity: { duration: 0.5 } } },
    gone: {
      x: k.x, y: k.y, opacity: k.x.map((_, i, a) => (i === a.length - 1 ? 0 : 1)),
      transition: { duration: 3, delay, times: k.times, ease: "linear" },
    },
  };
};

const arrive = (points, delay) => {
  const k = walk(points, points.at(-1));
  return {
    out: { x: k.x[0], y: k.y[0], opacity: 0, transition: { duration: 0 } },
    in: {
      x: k.x, y: k.y, opacity: k.x.map((_, i) => (i === 0 ? 0 : 1)),
      transition: { duration: 2.6, delay, times: k.times, ease: "linear" },
    },
  };
};

const ARJUN_OUT = leave([ARJUN, [120, 108], [120, 270], ...DOOR], 0.4);
const PRIYA_OUT = leave([PRIYA, [720, 108], [720, 270], ...DOOR], 1);
const MEERA_IN = arrive([...IN, [280, 270], MEERA], 0.3);
const BRAIN_IN = arrive([...IN, [420, 270], [420, 110]], 0.2);

const draw = (delay, duration = 0.8) => ({
  off: { pathLength: 0, opacity: 0, transition: { duration: 0.3 } },
  on: { pathLength: 1, opacity: 1, transition: { delay, duration, ease: "easeInOut" } },
});
const fade = (delay) => ({
  off: { opacity: 0, transition: { duration: 0.3 } },
  on: { opacity: 1, transition: { delay, duration: 0.5 } },
});

// a seated worker: head, shoulders and a shirt collar, bobbing at the keyboard (offset per seat so nobody types in sync)
function Person({ x, y, name, className = "", right }) {
  return (
    <g className={`worker ${name ? "named" : ""} ${className}`} transform={`translate(${x} ${y})`}>
      <g className="bob" style={{ animationDelay: `-${(x * 7 + y * 3) % 1600}ms` }}>
        <path className="body" d="M-14 15v-4a10 10 0 0 1 10-10h8a10 10 0 0 1 10 10v4Z" />
        <path className="collar" d="M-4 1l4 5 4-5" />
        <circle className="head" cy="-9" r="8" />
      </g>
      {name && (right ? <text className="name name-right" x="22" y="5">{name}</text> : <text className="name" y="-24">{name}</text>)}
    </g>
  );
}

function Room({ act, broken, healed }) {
  const on = (cond) => (cond ? "on" : "off");
  return (
    <svg viewBox="0 0 1200 660" className="room" role="img" aria-label={`Floor plan of the TiffinBox office. ${ACTS[act].title}.`}>
      <defs>
        <pattern id="plan-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" className="grid-line" />
        </pattern>
      </defs>
      <rect x="40" y="40" width="1120" height="580" fill="url(#plan-grid)" />

      {/* walls, three windows, the door and its swing */}
      <path className="wall" d="M1160 440V40H40V620H1160V530" />
      {[200, 540, 880].map((x) => <rect key={x} className="window" x={x} y="36" width="120" height="8" />)}
      <path className="plan" d="M1160 530H1070M1070 530A90 90 0 0 1 1160 440" />

      {/* knowledge threads, run under the desks like cables: who feeds what into the product */}
      <motion.path className="thread" d="M180 123C180 260 690 250 690 302" variants={draw(0.2, 1)} animate={on(act === 0)} initial={false} />
      <motion.path className="thread" d="M650 123C650 250 870 250 870 302" variants={draw(0.2, 1)} animate={on(act === 0)} initial={false} />
      <path className="thread" d="M180 413C180 380 330 390 330 358" />
      <path className="thread" d="M550 413C550 385 510 390 510 358" />
      {PODS.map(([name, x, y]) => (
        <g key={name} transform={`translate(${x} ${y})`}>
          {SEATS.map(([sx, sy]) => (
            <rect key={sx + "" + sy} className="chair" x={sx - 15} y={sy + (sy < 0 ? -13 : -9)} width="30" height="22" rx="6" />
          ))}
          <rect className="desk" x="-90" y="-35" width="180" height="70" rx="3" />
          {SEATS.map(([sx, sy]) => <path key={sx + "" + sy} className="monitor" d={`M${sx - 14} ${sy < 0 ? -28 : 28}h28`} />)}
          <text className="pod" y="5">{name}</text>
        </g>
      ))}

      {/* the product, running on the centre table */}
      <rect className="table" x="240" y="288" width="720" height="84" rx="4" />
      {[[395, 445], [575, 625], [755, 805]].map(([a, b], i) => (
        <path key={a} className={`flow ${broken && i === 2 ? "stopped" : ""}`} d={`M${a} 330H${b}`} />
      ))}
      {MODULES.map(([name, x]) => {
        const pay = name === "Payments";
        return (
          <motion.g key={name} variants={{ calm: { x: 0 }, shake: { x: [0, -7, 7, -5, 5, 0], transition: { duration: 0.5 } } }}
            animate={pay && broken ? "shake" : "calm"} initial={false}>
            <g className={`module ${name === "Gateway" ? "external" : ""} ${pay && broken ? "broken" : ""} ${pay && healed ? "healed" : ""}`}>
              <rect x={x - 65} y="302" width="130" height="56" rx="6" />
              <text x={x} y={pay ? 326 : 335}>{name}</text>
              {pay && <text className="config" x={x} y="345">retries = {broken ? 3 : 7}</text>}
            </g>
          </motion.g>
        );
      })}
      <motion.path className="crack" d="M676 302l10 16-8 12 14 14-8 14" variants={draw(0, 0.4)} animate={on(broken)} initial={false} />
      <motion.text className="alarm" x="690" y="392" variants={fade(0)} animate={on(broken)} initial={false}>
        checkout failing
      </motion.text>
      <motion.circle className="ring" cx="690" cy="330" initial={false} animate={broken ? "ring" : "still"}
        variants={{ still: { r: 30, opacity: 0 }, ring: { r: [30, 260], opacity: [0.5, 0], transition: { duration: 1.4, repeat: 1 } } }} />


      {TEAM.map(([x, y, name]) => <Person key={x + "," + y} x={x} y={y} name={name} />)}

      <motion.g variants={ARJUN_OUT} animate={act >= 1 ? "gone" : "here"} initial={false}>
        <Person x={ARJUN[0]} y={ARJUN[1]} name="Arjun" />
      </motion.g>
      <motion.g variants={PRIYA_OUT} animate={act >= 1 ? "gone" : "here"} initial={false}>
        <Person x={PRIYA[0]} y={PRIYA[1]} name="Priya" />
      </motion.g>

      {/* Meera reads everything she can find; none of it says why */}
      {[["retry.py", 410, 140, 3.4], ["PAY-88", 440, 185, 4.2], ["#payments", 410, 230, 5]].map(([label, x, y, delay]) => (
        <motion.g key={label} className="doc" variants={fade(delay)} animate={on(act === 2)} initial={false}>
          <rect x={x - 48} y={y - 13} width="96" height="26" rx="4" />
          <text x={x - 6} y={y + 4.5}>{label}</text>
          <text className="unknown" x={x + 36} y={y + 5}>?</text>
        </motion.g>
      ))}

      {/* her cleanup PR, then the same path again carrying the fix */}
      <motion.path className="commit" d="M280 247C300 300 640 280 690 302" variants={draw(0.3, 1)} animate={on(act === 3)} initial={false} />
      <motion.path className="thread fix" d="M280 247C300 300 640 280 690 302" variants={draw(4.2, 0.8)} animate={on(act === 4)} initial={false} />

      {/* KT Brain walks in, wakes what Arjun and Priya left in the graph, and hands it to Meera */}
      <motion.path className="thread wake" d="M398 104Q300 40 195 104" variants={draw(2.2, 0.7)} animate={on(act === 4)} initial={false} />
      <motion.path className="thread wake" d="M442 104Q545 40 635 104" variants={draw(2.2, 0.7)} animate={on(act === 4)} initial={false} />
      <motion.path className="thread" d="M420 132Q420 225 296 232" variants={draw(3.4, 0.6)} animate={on(act === 4)} initial={false} />
      {[["Arjun", ARJUN], ["Priya", PRIYA]].map(([name, [x, y]]) => (
        <motion.g key={name} variants={fade(2.4)} animate={on(act === 4)} initial={false}>
          <Person x={x} y={y} name={name} className="ghost" />
        </motion.g>
      ))}
      {[["D1", 298, 74], ["D8", 542, 74]].map(([id, x, y]) => (
        <motion.g key={id} className="decision" variants={fade(2.9)} animate={on(act === 4)} initial={false}>
          <rect x={x - 17} y={y - 12} width="34" height="24" rx="5" />
          <text x={x} y={y + 4.5}>{id}</text>
        </motion.g>
      ))}

      <motion.g variants={MEERA_IN} animate={act >= 2 ? "in" : "out"} initial={false}>
        <Person x={MEERA[0]} y={MEERA[1]} name="Meera" className="newcomer" right />
      </motion.g>

      <motion.g variants={BRAIN_IN} animate={act === 4 ? "in" : "out"} initial={false}>
        <g className="brain" transform="translate(420 110)">
          <circle r="22" />
          <path d="M-9-6L8-8L1 9Z" />
          <circle className="b-node" cx="-9" cy="-6" r="3.5" />
          <circle className="b-node" cx="8" cy="-8" r="3.5" />
          <circle className="b-node" cx="1" cy="9" r="3.5" />
          <text className="name" y="-32">KT Brain</text>
        </g>
      </motion.g>
    </svg>
  );
}

function WhyCard() {
  return (
    <div className="why-card">
      <p className="why-q">Why does payments retry 7 times?</p>
      <p>The payment gateway drops its webhooks for about five minutes during its own deploys. Seven retries cover that gap.</p>
      <p className="muted small">
        Decision D1, from a #payments chat thread, ticket PAY-88, Arjun's AI session and his PR. Priya's D8 comes with it:
        rotating the gateway key also means updating the webhook secret.
      </p>
      <a href="#/why">Open the why-trace</a>
    </div>
  );
}

export default function RoomStory() {
  const [act, setAct] = useState(0);
  const [playing, setPlaying] = useState(() => !matchMedia("(prefers-reduced-motion: reduce)").matches);
  // payments breaks a beat after the PR lands, and heals once the fix has been drawn
  const [late, setLate] = useState(false);

  useEffect(() => {
    setLate(false);
    const t = setTimeout(() => setLate(true), act === 3 ? 1300 : 5000);
    return () => clearTimeout(t);
  }, [act]);

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => setAct((a) => (a + 1) % ACTS.length), ACTS[act].ms);
    return () => clearTimeout(t);
  }, [act, playing]);

  const broken = (act === 3 && late) || (act === 4 && !late);
  const healed = act === 4 && late;

  return (
    <MotionConfig reducedMotion="user">
      <figure className="story">
        <div className="story-stage">
          <Room act={act} broken={broken} healed={healed} />
        </div>
        <figcaption>
          <div className="story-bar">
            <button className="icon-btn" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause the story" : "Play the story"}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
                {playing ? <path d="M7 5h3v14H7zM14 5h3v14h-3z" /> : <path d="M8 5v14l11-7z" />}
              </svg>
            </button>
            <ol className="acts">
              {ACTS.map((a, i) => (
                <li key={i}>
                  <button aria-current={i === act ? "step" : undefined} onClick={() => { setAct(i); setPlaying(false); }}>
                    <span className="act-date">{a.date}</span>
                    <span className="act-title">{a.title}</span>
                    <span className="act-bar">{i === act && playing && <span style={{ animationDuration: `${a.ms}ms` }} />}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
          <div className={`story-text ${act === 4 ? "with-why" : ""}`} aria-live="polite">
            <p><span className="act-lead">{ACTS[act].title}. </span>{ACTS[act].text}</p>
            {act === 4 && <WhyCard />}
          </div>
        </figcaption>
      </figure>
    </MotionConfig>
  );
}
