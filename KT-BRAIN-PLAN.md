# KT Brain: End-to-End Build Plan

_Written 2026-10-12 for Graph Hacks × FalkorDB (Oct 15–18, 2026). Tracks: **03 Company Brain + 02 Agent Memory** (+ **01** via MCP)._

> **Rule 8:** before Oct 15, only ideas, notes, graph-model sketches and diagrams are allowed. Everything here is a plan. The snippets are learning examples and query sketches; write the real code yourself from Oct 15. Commit this file on day 1 as proof of your pre-event design.

---

## 0. The story (the problem you'll tell in the demo)

> "At my startup, when a developer leaves, we do **KT**: knowledge transfer. Sometimes it's a 1-hour call, sometimes weeks, depending on how free both devs are. When someone is laid off, it's often a rushed call on their last day.
> Six months later the new dev changes a retry count from 7 to 3, and payments start failing. The reason it was 7 lived in a Slack thread, a Claude Code session and a ticket that nobody remembered.
> **KT fails because nobody knows what's missing.** KT Brain starts recording from the **first day** a dev joins: every commit, PR, review, ticket, doc and AI-assistant session goes into a graph. When they leave, nothing has to be extracted at the last minute. The graph already knows what *only they* know, builds the KT agenda, tracks the handover until it hits zero, and hands their memory to the new dev's coding agent."

The thesis in one line: **a KT is a coverage problem, not a Q&A problem.** A chatbot answers what you ask. The graph tells you what you didn't know to ask.

**Why from day 1 and not a backup at exit:**
- Layoffs are sudden. An exit interview gets maybe 1 hour; the graph has 2 years.
- A dev who knows they're leaving has little reason to document. Passive capture asks nothing of them.
- The "why" is freshest when the decision happens (the AI session, the PR review), not months later.
- The same brain helps *while they're still here*: teammates see who knows what, and bus-factor risk shows up early, not at the exit.

---

## 1. What you're building (one screen)

```
 DAY 1 ──────────────── continuous capture ──────────────── EXIT
  GitHub (commits, PRs, reviews, issues)  ┐
  AI coding sessions (Claude Code logs)   │ ingest → FalkorDB
  Tickets (Jira-like), Slack-like threads │ (one graph per company,
  Docs / ADRs / READMEs                   ┘  updated daily)
                         │
          ┌──────────────┼──────────────────────────┐
          ▼              ▼                          ▼
   1. WHO KNOWS WHAT   2. DRY-RUN DEPARTURE       3. WHY-TRACE
   bus-factor radar    GRAPH.COPY → remove dev    "why is retries=7?"
   (while they're      → list what only they      → path: file → PR →
    still here)          know = KT agenda            AI session → ticket
                         │
                         ▼
   4. HANDOVER TRACKER: KT sessions + the new dev's PRs add LEARNED edges
      → "14 things only they know → 0"
                         │
                         ▼
   5. INHERITANCE: the new dev's Claude Code calls the brain via MCP
      before editing a file → gets the predecessor's decisions + citations
```

Build priority (stop where time runs out; each step is demoable):
1. **Ingest + who-knows-what** ← the MVP
2. **Dry-run departure → KT agenda** ← the core thesis; don't skip it
3. **Why-trace with path citations**
4. **Handover tracker** (LEARNED edges, count → 0)
5. **MCP inheritance** for the new dev's coding agent (adds Track 01)

---

## 2. Graph data model (sample to work with)

### Nodes

| Label | Key properties | Example |
|---|---|---|
| `Person` | `id`, `name`, `active` (bool), `joined_at`, `left_at`, `role` | dev_arjun (leaving), dev_meera (new) |
| `Service` | `id`, `name`, `criticality` (computed) | payments, notifications |
| `File` | `path`, `service_id` | `payments/retry.py` |
| `PR` | `id`, `title`, `merged_at` | PR #212 "bump webhook retries" |
| `Commit` | `sha`, `message`, `at` | `a1b2c3` |
| `AgentSession` | `id`, `tool` (claude-code/cursor), `at`, `summary` | Claude Code session 2026-03-04 |
| `Decision` | `id`, `what`, `why`, `at`, `status` (active/superseded) | "retries=7 because Stripe webhooks flap during their deploys" |
| `Ticket` | `id`, `title`, `status` | PAY-88 "duplicate refunds" |
| `Thread` | `id`, `channel`, `at` | #payments thread about Stripe outage |
| `Doc` | `id`, `title`, `updated_at` | "Payments runbook" |
| `Concept` | `id`, `name` | "idempotency keys", "webhook signing" |

### Relationships

| Edge | Meaning |
|---|---|
| `(:Person)-[:AUTHORED]->(:PR\|:Commit\|:Doc)` | wrote it |
| `(:Person)-[:REVIEWED]->(:PR)` | reviewed it |
| `(:Person)-[:RAN]->(:AgentSession)` | used an AI assistant |
| `(:Person)-[:POSTED_IN]->(:Thread)` · `(:Person)-[:ASSIGNED]->(:Ticket)` | discussions and work |
| `(:PR)-[:CONTAINS]->(:Commit)-[:CHANGED]->(:File)-[:PART_OF]->(:Service)` | code structure |
| `(:AgentSession)-[:PRODUCED]->(:Commit)` | AI session behind a commit |
| `(:AgentSession\|:Thread\|:Ticket\|:PR)-[:RECORDS]->(:Decision)` | where a decision was made |
| `(:Decision)-[:ABOUT]->(:File\|:Service\|:Concept)` | what it's about |
| `(:Decision)-[:SUPERSEDES]->(:Decision)` | keeps knowledge current |
| `(:Ticket)-[:FIXED_BY]->(:PR)` · `(:Doc)-[:DESCRIBES]->(:Service)` | links |
| `(:Service)-[:DEPENDS_ON]->(:Service)` | for criticality (betweenness) |
| `(:Person)-[:KNOWS {score, last_touched, evidence}]->(:Service\|:Decision\|:Concept)` | **derived** nightly from the edges above |
| `(:Person)-[:LEARNED {at, via:'kt_session'\|'pr'\|'review'}]->(...)` | **handover progress** |

**Design choices:**
- `KNOWS` is *derived*, not entered by hand: authored, reviewed, ran a session about it, or decided it. Recompute it daily, which is how the brain fills itself from day 1.
- `KNOWS.score` decays with time (a file touched two years ago counts less). Write the formula down; judges will ask.
- Decisions are first-class nodes, so the "why" survives even when the code changes.

### Sample seed (≈ 40 nodes, enough to demo)

```
People:   arjun (active→leaving, joined 2024-06), kavya (active), meera (new, joined 2026-10)
Services: payments, notifications, auth   (payments DEPENDS_ON auth; notifications DEPENDS_ON payments)
Files:    payments/retry.py, payments/webhooks.py, auth/tokens.py, notifications/send.py

Arjun only:  payments/retry.py, payments/webhooks.py, Decision D1 "retries=7",
             Decision D2 "webhooks are idempotent via event_id"
Shared:      auth/tokens.py (arjun + kavya)
Kavya only:  notifications/send.py

D1 trail: Thread T9 (#payments, Stripe flapping) → Ticket PAY-88 → AgentSession S3
          (Claude Code: "bump retries, Stripe deploys cause 5-min webhook gaps")
          → Commit a1b2c3 → PR #212 → payments/retry.py
```

Expected demo result: the dry run of Arjun leaving shows **payments, D1, D2, webhook signing** with **no other knower**; auth is safe (Kavya); notifications isn't affected.

### The key queries (sketches; you'll write the real ones)

**Derive KNOWS** (nightly job, simplified):
```cypher
MATCH (p:Person)-[:AUTHORED|REVIEWED]->(:PR)-[:CONTAINS]->(:Commit)-[:CHANGED]->(:File)-[:PART_OF]->(s:Service)
WITH p, s, count(*) AS touches
MERGE (p)-[k:KNOWS]->(s) SET k.score = touches
```

**KT agenda:** what only the leaver knows (run on the dry-run copy).
```cypher
MATCH (l:Person {id:$leaver})-[:KNOWS]->(k)
OPTIONAL MATCH (o:Person {active:true})-[:KNOWS|LEARNED]->(k) WHERE o <> l
WITH k, count(o) AS backups WHERE backups = 0
RETURN labels(k)[0] AS kind, k.id, k.criticality ORDER BY k.criticality DESC
```

**Dry-run departure:**
```
GRAPH.COPY company company_dryrun_arjun
MATCH (p:Person {id:'arjun'}) SET p.active = false      // on the copy only
→ run the KT agenda query → orphan list (the agenda)
```

**Why-trace:** "why is `payments/retry.py` the way it is?"
```cypher
MATCH (f:File {path:$path})<-[:ABOUT]-(d:Decision {status:'active'})<-[:RECORDS]-(src)
OPTIONAL MATCH p = (f)<-[:CHANGED]-(:Commit)<-[:PRODUCED]-(:AgentSession)-[:RECORDS]->(d)
RETURN d.what, d.why, labels(src)[0] AS source, src.id, p
```
The LLM only turns the returned path into a sentence. Every claim cites a node id.

**Criticality:** `CALL algo.betweenness(...)` over `Service-[:DEPENDS_ON]->Service`, stored as `s.criticality`.
**Best mentor / successor:** harmonic centrality, or the shortest path from the new dev to each orphaned node through people who share neighbouring knowledge.
**Bus-factor radar (while everyone is still here):** services where `count(knowers) = 1`.

> ⚠ On Oct 15, check that the FalkorDB Docker tag you use has `algo.betweenness`, harmonic centrality, and `GRAPH.COPY`.

---

## 3. FalkorDB crash course (you've never used it)

**What it is:** a graph database that runs as a Redis module. You talk to it with **Cypher** (the same language as Neo4j). Each "graph" is a named key, so you can keep `company` and `company_dryrun_arjun` side by side.

### 3.1 Run it locally
```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
```
- `6379`: the database · `3000`: **FalkorDB Browser** (http://localhost:3000). Run Cypher and see the graph drawn.

### 3.2 Cypher in 30 minutes (practice in the Browser)
```cypher
CREATE (:Person {id:'arjun'})-[:AUTHORED]->(:PR {id:212})          // create
MATCH (p:Person)-[:AUTHORED]->(pr:PR) RETURN p.id, pr.id             // read
MATCH (p:Person {id:'arjun'}) SET p.active = false                   // update
MERGE (s:Service {id:'payments'})                                    // create if missing
MATCH path=(f:File)<-[*1..4]-(d:Decision) RETURN path                // multi-hop path
```
Practice: build the §2 seed by hand. When you can *see* the D1 trail drawn, you understand the project.

### 3.3 From Python
```bash
pip install falkordb
```
```python
from falkordb import FalkorDB
g = FalkorDB(host="localhost", port=6379).select_graph("company")
rows = g.ro_query("MATCH (p:Person {active:true}) RETURN p.id", {}).result_set
```
Rules from day 1:
- **Parameters always** (`$path`, `$leaver`). The LLM never writes query text; it picks from fixed queries.
- **`ro_query`** for everything the agent or MCP tool calls.
- Ingest with `UNWIND $rows AS r MERGE ...` so re-running ingestion is safe (idempotent). This matters because ingestion runs every day.
- Indexes: `CREATE INDEX FOR (f:File) ON (f.path)`, plus `Person.id`, `PR.id`, `Decision.id`.

### 3.4 Docs
Cypher https://docs.falkordb.com/cypher/ · Algorithms https://docs.falkordb.com/algorithms · GRAPH.COPY https://docs.falkordb.com/commands/graph.copy.html · Python https://github.com/FalkorDB/falkordb-py · MCP server https://github.com/FalkorDB/FalkorDB-MCPServer

---

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Graph | **FalkorDB** (Docker locally, **FalkorDB Cloud free tier** in prod) | required |
| Ingestion | **Python** scripts: GitHub REST API (commits, PRs, reviews, issues), Claude Code JSONL transcripts, JSON files for synthetic Slack/Jira | one script per source |
| Decision extraction | **Claude API** (`claude-sonnet-5-5`) reads a PR, thread or AI session and outputs `{what, why, about[]}` as JSON, stored with its source edge | the LLM suggests nodes; you review them; queries decide |
| Backend | **FastAPI** | `/agenda`, `/dryrun`, `/why`, `/learned`, `/radar`, `/graph` |
| MCP | small **MCP server** exposing `why(path)`, `who_knows(topic)`, `kt_agenda(person)` (all read-only) | Track 01 + the "inheritance" demo |
| Frontend | **React + Vite + TS**, `react-force-graph-2d`, Tailwind | |
| Tests | **pytest** + a why-question benchmark | |
| Deploy | **Vercel** (frontend) · **Render** free (backend) · **FalkorDB Cloud** free (DB) | |

**Keyless demo mode:** pre-extracted decisions are stored in the seed, so judges can use everything without an API key. Only *new* ingestion needs the LLM.

---

## 5. Repo layout

```
kt-brain/
├─ ingest/
│  ├─ github.py          # commits, PRs, reviews, issues → graph
│  ├─ agent_sessions.py  # Claude Code JSONL → AgentSession nodes (+ link to commits by time/files)
│  ├─ chat_tickets.py    # synthetic Slack/Jira JSON → Thread/Ticket
│  ├─ decisions.py       # LLM extracts Decision nodes from PRs/threads/sessions
│  └─ derive.py          # nightly: KNOWS scores, criticality
├─ backend/
│  ├─ app.py             # FastAPI endpoints
│  ├─ graph.py           # ALL Cypher in one file (easy for judges)
│  ├─ mcp_server.py      # read-only MCP tools
│  └─ tests/
├─ data/
│  ├─ synthetic/         # Slack/Jira JSON you generate
│  └─ seed/              # pre-extracted demo graph (keyless mode)
├─ frontend/             # radar, dry-run, agenda, why-trace, handover tracker
├─ docs/
│  ├─ design-pre-event/  # Rule 8 proof (photos/diagrams before Oct 15)
│  ├─ BUILD-LOG.md       # daily notes = your blog post
│  └─ ai-log/            # AI-session exports (disclosure)
└─ README.md
```

---

## 6. Data (Rule 6: public, synthetic or own data only)

| Source | Use | Notes |
|---|---|---|
| **A public open-source repo with a real maintainer change** | commits, PRs, reviews, issues = real "day 1 → exit" history of a person | pick a mid-size repo (1–5k PRs) where a core maintainer stepped back and someone took over; verify the handover from the repo history itself. Fetch via the GitHub REST API (`gh api`) |
| **Your own Claude Code transcripts** (`~/.claude/projects/*/…jsonl`) | real AI-coding sessions: your own data | strip anything private before committing |
| **Synthetic Slack + Jira** | threads and tickets that link to the real PRs | generate ~50 threads and ~40 tickets; label them synthetic in the README |
| **Your demo "startup" seed** (§2) | the tight story for the video | small, hand-checked |

**Two demo modes:**
1. **Startup story** (seed): Arjun leaving, the tight 3-minute demo.
2. **Real OSS repo**: "here's what the brain says about a real maintainer handover", which proves it works beyond a toy.

**Privacy (say this in the README):** a real deployment needs the employee's consent from day 1, clear rules on what's captured (work tools only, no DMs), and a policy for what happens to the brain after they leave.

---

## 7. Day-by-day plan

### Before Oct 15 (design only)
- [ ] Draw the §2 model on paper → photo into `docs/design-pre-event/`
- [ ] Write the 5 key queries by hand
- [ ] Choose the OSS repo; write down the maintainer-change story in plain English (no scraping code yet)
- [ ] Write 20 "why is it like this?" benchmark questions + expected answers for the seed
- [ ] Write the demo script (§10)
- [ ] Join the FalkorDB Discord; sign up for FalkorDB Cloud, Render, Vercel, Anthropic (accounts only)

### Day 1 (Oct 15): graph + ingestion
- [ ] Docker FalkorDB; seed §2 by hand in the Browser
- [ ] `graph.py` with seed + indexes; `ingest/github.py` for the OSS repo (idempotent MERGE)
- [ ] `derive.py`: KNOWS scores
- [ ] Radar query: services with exactly 1 knower
- [ ] **End of day: "who knows what" works on real repo data.** Commit.

### Day 2 (Oct 16): decisions + dry run + why-trace
- [ ] `agent_sessions.py` (your Claude Code logs) + synthetic Slack/Jira
- [ ] `decisions.py`: LLM extraction → Decision nodes with source edges; spot-check 20 by hand
- [ ] Dry run with `GRAPH.COPY` → KT agenda; betweenness for criticality
- [ ] Why-trace endpoint returning path + citations
- [ ] **Benchmark:** 20 why-questions, plain RAG (vector search over the same texts) vs graph. Score correct + cited.
- [ ] **End of day: the agenda and the benchmark numbers exist.**

### Day 3 (Oct 17): UI + handover + MCP
- [ ] React: radar → "simulate Arjun leaving" → agenda → click an item → why-trace path drawn
- [ ] Handover tracker: mark a KT session / new-dev PR → LEARNED edge → counter goes down
- [ ] MCP server (read-only); demo: the new dev's Claude Code asks `why("payments/retry.py")` before editing
- [ ] Deploy (§9) **today**

### Day 4 (Oct 18): polish + submit
- [ ] README (§11), Cypher list, AI disclosure; video (§10) in your own voice
- [ ] Blog post from BUILD-LOG.md
- [ ] Fresh-clone test of your own README
- [ ] Submit with **Tracks 03 + 02 (+01)** named, well before 11:59 PM IST

**Cut list if behind:** drop MCP first, then the handover tracker. Radar + dry-run agenda + why-trace + benchmark still makes a strong Track 03 entry.

---

## 8. Testing

| Test | What it proves |
|---|---|
| `test_ingest_idempotent` | running ingestion twice creates no duplicates |
| `test_knows_derived` | an author or reviewer of a payments PR gets KNOWS→payments |
| `test_agenda_only_orphans` | dry run of Arjun lists payments/D1/D2, **not** auth (Kavya knows it) |
| `test_dryrun_does_not_touch_live` | after the dry run, the live graph still has Arjun active |
| `test_learned_clears_item` | adding meera-LEARNED→D1 removes D1 from the agenda |
| `test_why_trace_cites_sources` | every why-answer has at least one source node id |
| `test_superseded_decision_hidden` | an old decision replaced by a newer one isn't returned as current |
| `test_query_is_parameterized` | a file path containing Cypher changes nothing |
| benchmark | graph beats plain RAG on the 20 why-questions (report both numbers honestly) |

---

## 9. Deploying on free tiers

1. **DB → FalkorDB Cloud free tier.** Env vars `FALKOR_HOST/PORT/PASSWORD`; load the seed + OSS-repo graph once.
   _Fallback:_ a full local Docker setup in the README.
2. **Backend → Render** web service, root `backend/`, `uvicorn app:app --host 0.0.0.0 --port $PORT`. `ANTHROPIC_API_KEY` is optional (keyless mode uses pre-extracted decisions). The free tier sleeps, so the first request takes ~50 s; show "waking up…" in the UI.
3. **Frontend → Vercel**, root `frontend/`, `VITE_API_URL=https://<you>.onrender.com`; allow that origin in FastAPI CORS.
4. **MCP server:** runs locally in the demo (`claude mcp add ...` pointed at the cloud DB); document the one-line setup in the README.
5. Smoke test from your phone: radar → simulate departure → agenda → why-trace.

Never commit keys or `.env`. Ingestion endpoints are disabled in the public deployment; the public site is read-only.

---

## 10. Demo video script (≤ 3 min)

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Your face or slide | "At my startup, KT takes an hour or weeks, and it still misses things." (§0 story) |
| 0:20–0:40 | Timeline: Arjun's day 1 → today; the graph growing | "KT Brain starts recording on day one, not on the last day." |
| 0:40–1:05 | Radar → "Simulate Arjun leaving" (GRAPH.COPY) → **14 items only Arjun knows** | "The graph knows what nobody else knows." |
| 1:05–1:35 | Click "retries=7" → path drawn: file → commit → Claude Code session → ticket → Slack thread | "Every answer is a path, not a guess." |
| 1:35–1:55 | Benchmark: plain RAG vs graph on 20 why-questions | the honest numbers |
| 1:55–2:25 | Meera's KT session + her first PR → counter 14 → 0 | "KT is done when the number is zero, not when the call ends." |
| 2:25–2:50 | Meera's Claude Code (MCP) asks why() before editing retry.py → warns about Stripe | "Her agent inherited Arjun's memory." |
| 2:50–3:00 | The agenda query on screen | "One Cypher query. Without the graph, there's no agenda." (Rule 3) |

---

## 11. README checklist (Rule 10)

- [ ] Thesis: "KT is a coverage problem, not a Q&A problem" + the startup story
- [ ] Live URL + cold-start note + local setup
- [ ] **Graph data model** (diagram + §2 tables), including how KNOWS is derived and how it decays
- [ ] **Cypher queries and algorithms used** (agenda, dry run with GRAPH.COPY, why-trace, betweenness, harmonic centrality, radar)
- [ ] "Why a graph, not a vector DB": RAG can't prove *nobody else* knows something
- [ ] Benchmark table + how to reproduce it
- [ ] Data sources: OSS repo + license, own transcripts, synthetic Slack/Jira (labelled)
- [ ] Privacy and consent section
- [ ] How AI was used (§13)
- [ ] Tracks: **03 Company Brain, 02 Agent Memory & Coordination, 01 Agents That Act on Connected Data**
- [ ] Video link

---

## 12. Tools while developing: plugins, MCP servers, skills

| Tool | Use it for |
|---|---|
| **FalkorDB Browser** (port 3000) | write and debug every query visually; screenshot the D1 trail for the README |
| **FalkorDB MCP server** | let Claude Code inspect the live graph while you debug |
| **Your own KT Brain MCP server** | the product itself; dogfood it: use it on your own repo during the hackathon |
| **FalkorDB Claude Code skills** | Cypher and FalkorDB-specific help inside Claude Code |
| **`gh` CLI / GitHub MCP** | pull PRs, reviews and issues for ingestion; issues as your task board |
| **Claude in Chrome** | click through the deployed UI |
| **`/code-review`, `/security-review`** | daily diff review (the MCP server and ingestion handle untrusted text) |
| **claude-api skill** | structured JSON extraction for decisions; correct model ids |
| **dataviz / artifact skills** | the radar and benchmark charts |

Check each tool's install steps on Oct 15; skip anything you don't end up using.

---

## 13. Staying clear of the "fully AI-generated" rule

- **You write:** `graph.py` (all Cypher), the `derive.py` scoring formula, the dry-run/agenda logic, the benchmark questions and scoring.
- **AI may help with:** the React UI, FastAPI and MCP boilerplate, ingestion plumbing, test scaffolding.
- The decision extractor is an LLM, so **spot-check its output by hand** and record the accuracy in the README (e.g. "18/20 correct").
- Commit small and often; keep a daily BUILD-LOG; export AI sessions to `docs/ai-log/`; say exactly what was AI-assisted.
- Be able to explain without notes: why KNOWS is derived, the decay formula, why GRAPH.COPY instead of editing the live graph, why "zero backups" counts as proof, and how the why-trace avoids hallucination.
- Record the video in your own voice.

---

## 14. Risks and answers

| Risk | Answer |
|---|---|
| "This is just chat-with-docs" | lead with the dry-run agenda and the zero-backups proof, not Q&A |
| Market already crowded (Viven, Unblocked, Glean) | they answer questions; you measure and close the handover gap. Say it in the README |
| LLM extracts wrong decisions | every decision links to its source; hand spot-check; show the accuracy number |
| KNOWS too noisy (touching ≠ knowing) | weight reviews and decisions above typo commits; time decay; explain the formula |
| Synthetic Slack/Jira looks fake | link it to *real* PRs from the OSS repo; label it honestly |
| GitHub API rate limits | use `gh` with your token; cache raw JSON in `data/` |
| Time runs out | follow the cut list in §7 |
| Privacy questions from judges | the consent and scope section in the README; the public demo uses only public, synthetic and own data |
