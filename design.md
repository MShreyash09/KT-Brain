# KT Brain: UI design

_2026-10-15. The screens read live graph data: `GET /api/workspace` (loaded once in `frontend/src/ui.jsx`) and
`GET /api/search` (Ask). Both come from `backend/app.py`._

**References:** Mobbin and Google Stitch were not connected to this session (`claude mcp list` shows neither). These
wireframes are hand-drawn from common SaaS dashboard patterns (Linear, Vercel, Raycast settings). **TODO:** once both
MCP servers are connected, pull Mobbin references for "onboarding empty state", "data table with risk badges" and
"timeline / activity feed". Generate a Stitch pass of the six screens, then update this file and the CSS tokens.

## Principles
1. **One question per screen.** Each step answers one thing a judge would ask, in the order of the demo script
   (`COMPANY-X-SCENARIO.md` §4). There are no dashboards full of charts.
2. **Show only what is needed.** Nothing is decorative. Counts appear only where the number is the point (the radar
   count, the agenda size, the 12 → 6 counter).
3. **Every answer shows its proof.** Lists link to their why-trace, and each screen has a collapsed "Cypher" block with
   the exact query that produced it (this is the Rule 3 evidence for judges).
4. **Synthetic data is labelled** in the top bar at all times.
5. **Works on a phone.** The sidebar collapses into a scrolling tab bar, and nothing scrolls sideways.

## Information architecture
```
Landing ──► Workspace (TiffinBox demo)
              1 Team        who knows what
              2 Radar       bus factor = 1
              3 Departure   simulate Arjun / Priya / both leaving (GRAPH.COPY)
              4 Why         decision → sources → research → incident
              5 Handover    Meera's KT: 12 → 6
              6 Ask         full-text search over Chunk nodes
```
Each step ends with a "Next: …" button, so a judge can click straight through the story.

## Wireframes

### Landing
```
┌──────────────────────────────────────────────────────────────┐
│ ◆ KT Brain                                          [☀/☾]    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│      Know what walks out the door before it does.            │
│      KT Brain records who knows what from day one, so a      │
│      resignation comes with a ready-made handover plan.      │
│                                                              │
│      [ Open the TiffinBox demo → ]                           │
│      6 months · 6 people · 802 edges · synthetic data        │
│                                                              │
│      Bring your own: GitHub repo · docs · Claude Code logs   │
│      (coming soon, greyed out)                               │
└──────────────────────────────────────────────────────────────┘
```

### Workspace shell (desktop ≥ 900 px)
```
┌──────────────────────────────────────────────────────────────┐
│ ◆ KT Brain   TiffinBox · synthetic · snapshot Sep 21  [☀/☾]  │
├────────────┬─────────────────────────────────────────────────┤
│ 1 Team     │  <step title>                                   │
│ 2 Radar    │  <one-line explanation>                         │
│ 3 Departure│                                                 │
│ 4 Why      │  <step content, max 880 px wide>                │
│ 5 Handover │                                                 │
│ 6 Ask      │  ▸ Cypher                                       │
│            │                          [ Next: Radar → ]      │
└────────────┴─────────────────────────────────────────────────┘
```
On a phone the sidebar becomes a row of tabs under the top bar that scrolls sideways.

### 1 Team
```
 Who knows what                       snapshot Sep 21
 ┌─────────┐ ┌─────────┐ ┌─────────┐
 │ AM      │ │ PI      │ │ KN      │   person cards: initials, name, role,
 │ Arjun   │ │ Priya   │ │ Kavya   │   status pill (Leaving Sep 30 / Active /
 │ Backend │ │ DevOps  │ │ Frontend│   Joins Sep 22), "knows 22 · only one 3"
 │ Leaving │ │ Leaving │ │ Active  │
 └─────────┘ └─────────┘ └─────────┘
 ── Arjun knows ───────────────────────────────────
 Decision  D1  Payment retries = 7 …     ███████░ 6.45   ← click opens Why
 File      api/payments/retry.py         █████░░░ 5.12
```

### 2 Radar
```
 12 items only one person knows
 Arjun (leaving) ─ 3     Decision D1 …  · File retry.py · File webhooks.py
 Priya (leaving) ─ 6     …
 Rohan           ─ 3     …
```
Rows for people who are leaving get the risk colour.

### 3 Departure
```
 Who leaves?  ( Arjun | Priya | [Both] )
 Ran on GRAPH.COPY tiffinbox → dryrun; the workspace graph is untouched.
 ┌──────────────┐
 │ 12           │ items leave with them = the KT agenda
 └──────────────┘
 D8  Rotating the API key also requires WEBHOOK_SECRET   [only if both leave]
 D14 CI cache key …                                      [weak backup: Kavya]
```

### 4 Why
```
 [ D1 Payment retries = 7 … ▾ ]
 ● File      api/payments/retry.py
 │
 ● Decision  Payment retries = 7 with exponential backoff
 │           why · "evidence quote"
 │ recorded in
 ● Thread    #payments  Aug 4   arjun
 ● Ticket    PAY-88     Aug 4   arjun
 ● Session   Retry policy for gateway deploy gaps   Aug 5  arjun
 ● PR #124   …          Aug 5   arjun
 │ replaced
 ○ D13 Payment retries = 3            (caused INC-x, if any)
 │ informed by
 ● Research R1 → External: Cloudflare 2019 ↗
 Pattern: Retry with exponential backoff
```

### 5 Handover
```
 12 → 6   ██████░░░░░░  6 covered by Meera
 Covered                         Still only with Arjun/Priya
 ✓ D1     KT session · Sep 24    ✗ D6  Canary deploys …
 ✓ retry.py  her PR · Sep 25     ✗ main.tf …
 Suggested mentor: Kavya (weak backup on D14 and ci.yml), or hire DevOps.
```

### 6 Ask
```
 [ why are retries 7?                               ]
 chips: retries · canary · pause cap · taste quiz
 Doc   Research: cold-start recommendations   chunk 1
       "…we drop the **taste quiz**…"   files: ml/recommend/features.py
 Full-text search over Chunk nodes inside FalkorDB. No second database.
```

## Visual tokens
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f7f7f5` | `#0e0e10` | page |
| `--surface` | `#ffffff` | `#17171a` | cards, sidebar |
| `--surface-2` | `#f0f0ed` | `#202024` | hover, chips, code |
| `--border` | `#e3e3df` | `#2c2c31` | 1 px lines |
| `--text` | `#1b1b19` | `#ececef` | body |
| `--text-2` | `#62625c` | `#a1a1aa` | secondary |
| `--accent` | `#4f46e5` | `#8b8cf8` | primary button, Decision, focus ring |
| `--risk` | `#c92a2a` | `#ff6b6b` | leaving, bus factor 1, not covered |
| `--warn` | `#b45309` | `#f0b429` | combination risk, weak backup |
| `--ok` | `#2b8a3e` | `#51cf66` | covered / learned |

- Type: system UI stack at 15 px base. Monospace (`ui-monospace`) for file paths and Cypher. Step titles 22 px/600.
- Spacing: a 4 px scale (4, 8, 12, 16, 24, 32). Radius 10 px for cards, 999 px for pills.
- Theme: the toggle sits in the top bar. It defaults to the OS setting, the choice is saved in `localStorage`, and a
  tiny inline script in `index.html` sets `data-theme` before first paint so the page never flashes.
- Motion: none beyond 150 ms colour transitions.
- Accessibility: buttons are `<button>`, the step nav is a `<nav>` with `aria-current`, the toggle has an
  `aria-label`, and focus rings are visible. Text contrast is ≥ 4.5:1 in both themes.

## Stack
React + Vite, plain CSS with custom properties. No UI kit, chart or graph library: the why-trace is a vertical path
drawn with CSS, and score bars are divs. Dependencies are `react`, `react-dom`, `vite` and `@vitejs/plugin-react`.

## Not in this pass
- The Play/replay animation (Apr → Sep). Day 3, after the API.
- Live BYO ingest (GitHub URL, uploads). The landing card only shows it as coming soon.
- A force-directed graph view. The FalkorDB Browser already does that, and a path list reads better for a why-trace.
