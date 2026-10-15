# KT Brain: Hack Plan v2 (usable SaaS + TiffinBox demo workspace)

_Written 2026-10-15 (Day 1). v2 replaces v1 from this morning, and v1 replaced §3 of `KT-BRAIN-ROADMAP.md`. Story and answer key: `COMPANY-X-SCENARIO.md`. Base model: `KT-BRAIN-PLAN.md` §2._

**What judges get:** a real web app. They open it, create a workspace (no signup), then either:
- **Load the TiffinBox demo**: the synthetic 6-month startup scene with the planted answer key, or
- **Bring their own data**: paste a public GitHub repo URL, upload docs, or upload AI coding session logs.

Both paths run through the **same** ingest → graph → dry-run → why-trace engine. Each workspace is its own FalkorDB graph (`ws_<id>`). Multi-tenancy is native to FalkorDB.

Budget: about 7 h/day. Each day ends with a gate. Cut order is at the bottom.

---

## 1. Data: what is synthetic, what is real
| Layer | Source | Why |
|---|---|---|
| TiffinBox scene: 5 roles, resignations, D1-D15 | **Synthetic**, labelled as such | Public data can't give us roles, a resignation and a known answer key |
| Decisions inside the scene | Synthetic, but **cite real public postmortems** as `ExternalSource` nodes | Shows the "failed → researched → improved" chain with real evidence |
| BYO repo | **Real**: any public GitHub repo (commits, PRs, reviews, issues) | Proves it works on data we didn't write |
| BYO docs and AI sessions | **Real**: the judge's own uploads (or our own Claude Code sessions from building this project) | Proves the connectors work |

### Three knowledge types added to TiffinBox (new beats on Day 1)
1. **Failure → research → improvement (infra)**
   - May checkout outage: all-at-once deploy → Priya's research doc cites Cloudflare's 2 Jul 2019 outage report (a global rule push) → D6 canary deploys. The old decision ("deploy all at once") gets `SUPERSEDES`.
   - "Backups exist but were never restored" → research cites GitLab's 31 Jan 2017 database incident → D9 quarterly restore tests.
   - `(Incident)-[:CAUSED_BY]->(Decision old)<-[:SUPERSEDES]-(Decision new)-[:INFORMED_BY]->(Research)-[:CITES]->(ExternalSource {url})`
2. **System design patterns**
   - D1 retry with backoff, D2 idempotency key, D3 optimistic locking, D6 canary release, D11 fallback/circuit breaker.
   - `(Decision)-[:APPLIES]->(Pattern)` and `(Pattern)<-[:IMPLEMENTS]-(File)`
   - Agenda line this produces: "Only Arjun understands how retry+idempotency are wired in payments."
3. **PM ground research**
   - Neha's interview notes, survey and competitor scan → insights → PRD → feature → PR. Example: "11/15 interviewees pause during travel; most trips < 2 weeks" → D15 pause cap → `billing.py`.
   - `(Research)-[:FOUND]->(Insight)-[:JUSTIFIES]->(Decision)-[:ABOUT]->(Feature)<-[:IMPLEMENTS]-(PR)`
   - Demo: click `billing.py` and the why-trace reaches the user interviews.

_Not chosen:_ GitLab is the one org with code, postmortems, design docs and UX research all public, but it's on GitLab (needs a second connector) and is huge. Not worth it in 4 days.

---

## 2. What goes in the graph (and what doesn't)
| Tier | Stored where | What |
|---|---|---|
| Structure | FalkorDB nodes and edges | Person, File, Service, PR, Commit, AgentSession, Doc, Decision, Pattern, Incident, Research, Insight, KNOWS, LEARNED |
| Searchable text | FalkorDB `Chunk` nodes (~400 tokens each) with a **vector index** and a **full-text index** | `(Chunk)-[:PART_OF]->(Doc\|AgentSession\|Thread)`, `(Chunk)-[:MENTIONS]->(File\|Decision)`. Search hits a chunk, then the graph walks to its neighbours. Decisions keep `what`, `why` and an `evidence` quote |
| Originals | **Not stored** (decided 2026-10-15: one database) | `Chunk` nodes are linked in order by `NEXT`, so any document can be rebuilt. Session logs are slimmed first: keep prompts, assistant text, file paths, branch and timestamps, and drop tool output. PDFs are dropped after text extraction. With the CLI, raw logs never leave the laptop |

FalkorDB is the only database: workspaces, tokens and jobs also live in a small `system` graph. Since it keeps everything in RAM, we slim the data instead of adding a second store. See `ARCHITECTURE.md`. Vector search inside FalkorDB also strengthens our Rule 3 case. **Check today** that the Docker tag supports `CREATE VECTOR INDEX` and `db.idx.vector.queryNodes`.

---

## 3. Capturing local AI sessions and docs
| Way in | What it does | When |
|---|---|---|
| Web upload | Drag `.md`/`.pdf` docs and Claude Code `.jsonl` into the workspace | Day 2-3 (must have) |
| `ktbrain sync` CLI (one Python file) | Scans `~/.claude/projects/*/*.jsonl`, `~/.codex/sessions/**/rollout-*.jsonl` and a docs folder → keeps sessions whose `cwd` is the repo → **redacts secrets on the laptop** → extracts metadata → POSTs **only extracted nodes + short snippets** with a workspace token | Day 4 (stretch) |
| Automatic | Claude Code `SessionEnd` hook runs `ktbrain push` with the hook's `transcript_path`. For Codex, a git `post-commit` hook runs `ktbrain sync` | Stretch |
| Cursor | Chats live in an undocumented SQLite file (`state.vscdb`) whose format changes between versions | "Planned", not built |

**Verified today:** each line of a local Claude Code session log has `sessionId`, `cwd`, `gitBranch`, `timestamp` and `aiTitle`. Its `Edit`/`Write`/`Read` tool calls carry a `file_path`, which gives us the files touched.

**Linking a session to code:** `(AgentSession)-[:PRODUCED]->(Commit)` when the files touched overlap, the branch matches, and the commit lands within the session window. A `Co-Authored-By: Claude` trailer counts as an extra signal.

Codex is not installed on this machine, so its format is unverified. We need one sample `rollout-*.jsonl` before we parse it.

---

## 4. Stack
- **FalkorDB**: Docker locally, FalkorDB Cloud in prod. One graph per workspace. The demo seed is a template graph we `GRAPH.COPY` into each new workspace.
- **FastAPI**: `BackgroundTasks` for ingest jobs (no queue). All Cypher in `graph.py`.
- **React + Vite SPA**, built to static files and served by FastAPI. One deploy on Render.
- **Claude API**: a server-side extractor (docs/sessions/PRs → Decision/Pattern/Insight JSON), with a cap per workspace. The TiffinBox extractions are cached, so the demo needs no API key.
- **Limits**: a server GitHub token, BYO repos capped at the last 300 PRs, workspaces expire after 48 h.

```
kt-brain/
├─ backend/  app.py  graph.py  ingest/{github,docs,claude_code,codex,fixtures}.py  extract.py  derive.py  tests/
├─ frontend/ (Vite + React)
├─ cli/ktbrain.py
├─ data/tiffinbox/ (beats.md, fixtures, cached extractions)
└─ docs/ (BUILD-LOG.md, ai-log/, design-pre-event/)  README.md
```

---

## 5. Day by day
### Day 1, Thu Oct 15: engine on TiffinBox
- 0:30 Create the repo + Docker. Check the tag supports `GRAPH.COPY`, `algo.*`, the vector index and the full-text index.
- 2:00 Write `beats.md` (~45 beats, including the three new knowledge types and the post-Sep 22 Meera segment) → Claude expands them into fixtures → hand-check D1-D15 plus the incident, pattern and research chains.
- 2:00 Fixture ingest into graph `tiffinbox_template` (`UNWIND`/`MERGE`, re-runnable, `--until`).
- 1:30 `derive.py` (KNOWS formula + threshold) and the radar query.
- 1:00 `test_answer_key.py` (all rows; the radar rows must pass).
- **Gate:** the radar is correct on TiffinBox.

### Day 2, Fri Oct 16: the thesis + generic ingest _(college day; the first 3 bullets are the minimum)_
- 1:30 Dry run on a `GRAPH.COPY`, then the agenda. Tests: D8 only when both leave, no D2, no D13.
- 1:30 Why-trace through decision, incident, research, external source, pattern and insight. Mentor query (Kavya).
- 1:30 `extract.py` + chunking + embeddings + vector index, all **generic**: the same code runs on the fixtures and on uploads. Score the extraction against the answer key.
- 1:30 Ingest for uploaded docs (md/pdf) and Claude Code JSONL, using real sessions from building this project.
- 1:00 The LLM-reads-everything baseline vs the graph, scored against the answer key.
- **Gate:** API answers the dry-run and why questions for TiffinBox, and our own Claude Code sessions show up as AgentSession nodes.

### Day 3, Sat Oct 17: SaaS shell + deploy
- 0:30 Workspaces: `POST /ws` creates `ws_<id>`, "Load demo" runs `GRAPH.COPY tiffinbox_template ws_<id>`, plus expiry.
- 1:30 GitHub connector for a public repo URL (commits, PRs, reviews, issues), reusing Day 1's mapping. Shows a progress status.
- 3:00 React app with these screens: Sources (demo / GitHub / upload) → Radar → Simulate departure → Agenda + why-trace graph → Handover (LEARNED, counter) → Ask (vector search + graph walk, with citations). Includes the Play/replay for TiffinBox.
- 1:30 Deploy: FalkorDB Cloud + Render, a daily keep-alive Action, a one-command reseed. Test on your phone with a repo you've never tried.
- **Gate:** a stranger can create a workspace, run the TiffinBox scene, and ingest a public repo.

### Day 4, Sun Oct 18: ship (submit by 8 PM IST)
- 1:30 `cli/ktbrain.py sync` for Claude Code (+ Codex if you have a sample) and a docs folder, with local redaction. **Cut this first if behind.**
- 1:30 README: data model, every Cypher query, the three storage tiers, privacy/local-first, answer-key and baseline tables, AI disclosure, tracks 03 + 02 (+01 if MCP shipped).
- 1:30 Video: the TiffinBox scene (2 min) + "now on a real repo" (30 s) + "your Claude Code sessions" (30 s).
- 1:00 Clone the repo fresh and follow the README. 0:30 Submit and verify.

## Cut order when behind (first to go at the top)
Cursor → Codex → CLI (keep web upload) → MCP → PDF upload (keep md) → LLM extraction on BYO repos (keep KNOWS/radar/dry-run, which need no LLM) → replay animation (use a date slider). **Never cut:** the TiffinBox dry run, D8, the why-trace, the public URL.

**Every day:** BUILD-LOG (5 lines), commit every 90 min, export AI sessions to `docs/ai-log/`. **You write** the Cypher, the KNOWS formula and the agenda/dry-run logic.
