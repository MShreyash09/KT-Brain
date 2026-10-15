# KT Brain: Part-Time Roadmap (~7 h/day)

_Written 2026-10-14. Companion to `KT-BRAIN-PLAN.md` (model, queries, stack). This file only answers: what to do, in what order, with limited hours._
_Assumption: ~7 h/day x 4 days = ~28 h. If 6-8 h is the **total**, jump to "Ultra-lean" at the bottom._

> **Rule 8:** before 12:01 AM IST Oct 15 only ideas, notes, diagrams, accounts and installs. No project code. Toy Cypher practice is fine if it stays outside this folder and is never committed.

---

## 0. Scope for part-time (cuts vs the full plan)

| Keep (the thesis) | Cut / shrink |
|---|---|
| Ingest GitHub history of ONE real OSS repo | Synthetic Slack/Jira -> **cut** (add only if Day 3 is ahead) |
| KNOWS derivation + who-knows-what radar | React polish -> one page, 3 panels |
| Dry-run departure on `GRAPH.COPY` -> KT agenda | Handover tracker -> tiny: button adds LEARNED edge, counter drops |
| Why-trace with citations (PR/commit based; your own Claude Code sessions as a bonus source) | MCP server -> **stretch only** |
| **Backtest** on a real maintainer handover (replaces the 20-question benchmark) | Betweenness criticality -> only if it exists in your Docker tag |

One-line pitch: **"KT is a coverage problem. The graph tells you what only the leaver knows, and how far the handover is from zero."**

---

## 1. Before the start (today, Oct 14), ~3 h, allowed

1. **Install + pull (30 min):** Docker Desktop, `docker pull falkordb/falkordb:latest`, Python 3.11+, Node 20, `gh` CLI (`gh auth login`). Do NOT start a project folder yet.
2. **Accounts only (20 min):** FalkorDB Cloud (free), Render, Vercel, Anthropic API key, FalkorDB Discord. Register for the hackathon + team if not done.
3. **Pick the OSS repo (60 min, research only):** mid-size (1-5k PRs), permissive license, one core maintainer who clearly stepped back and was succeeded. Verify the handover from the repo's public history/announcements. Write down: repo, leaver's GitHub handle, leave date, successor, 5 things you expect only the leaver knew. This is your **ground truth for the backtest**. Have a 2nd candidate in case the first has too little history.
4. **Paper design (45 min):** redraw the model from `KT-BRAIN-PLAN.md` §2 by hand, photograph into `docs/design-pre-event/` on Day 1 (Rule 8 proof). Write the KNOWS formula in words:
   `score(person, thing) = sum over events of weight(type) * exp(-age_days / 180)`, with weights like review 1.0, authored PR 1.5, decision 3.0, typo commit 0.1.
5. **Learn the basics (60 min):** do the crash course below, on throwaway toy data.
6. **Sleep.** The event is 4 days; you don't need to be up at 12:01 AM.

---

## 2. FalkorDB crash course (do this today, ~1 h)

**Mental model:** FalkorDB = graph DB living in Redis memory. You send **Cypher**. Each named graph is a key; `GRAPH.COPY a b` clones a whole graph in one command (your dry run). Nodes have labels + properties; edges have a type + direction + properties.

**Run:** `docker run -p 6379:6379 -p 3000:3000 --rm falkordb/falkordb:latest` -> open http://localhost:3000 (Browser: type Cypher, see the graph drawn).

**The 8 Cypher ideas that cover 90% of this project** (practise each on a toy graph of 5 people / 5 files):

| # | Idea | Shape |
|---|---|---|
| 1 | Create | `CREATE (:Person {id:'a'})` |
| 2 | Idempotent write | `MERGE (p:Person {id:'a'}) SET p.name='A'`  (ingestion must be re-runnable) |
| 3 | Match a pattern | `MATCH (p)-[:AUTHORED]->(pr)-[:TOUCHES]->(f) RETURN p.id, f.path` |
| 4 | Aggregate | `... WITH p, f, count(*) AS n RETURN ...` |
| 5 | Variable-length path | `MATCH path=(f)<-[*1..4]-(d) RETURN path` |
| 6 | OPTIONAL MATCH + count = 0 | "things with no other knower" = your KT agenda |
| 7 | Batch load | `UNWIND $rows AS r MERGE ...` (Python passes `rows`) |
| 8 | Parameters | `$id`, never string-built queries |

**FalkorDB-specific things to try once:**
- `GRAPH.COPY toy toy_copy`, change the copy, confirm `toy` is untouched.
- `GRAPH.RO_QUERY` (read-only; use for everything the UI/agent calls).
- `CREATE INDEX FOR (f:File) ON (f.path)`.
- `CALL algo.pageRank / algo.betweenness` on the toy graph (check which exist in your tag; the 6.0 Rust engine lags the C engine until 6.2).
- Python: `pip install falkordb`, then `FalkorDB().select_graph('toy').ro_query(q, params).result_set`.

**Done when** you can, without notes: build a 5-person toy graph, find "files only person X touched", copy the graph, delete X on the copy, and re-run to list the orphans. That exercise IS the project's core.

Docs: https://docs.falkordb.com/cypher/ , https://docs.falkordb.com/algorithms , https://docs.falkordb.com/commands/graph.copy.html

---

## 3. Day-by-day (7 h each, with a hard "demoable at end of day" gate)

### Day 1, Thu Oct 15: graph + ingestion (7 h)
- 0:30 Create repo, commit `KT-BRAIN-PLAN.md`, this file, and the design photos (Rule 8 proof). Check Docker tag has what you need (`GRAPH.COPY`, algos).
- 2:00 Generate the Company X fixtures from `COMPANY-X-SCENARIO.md` (Claude expands the beats; hand-check D1-D15), then write an ingest script for them (GitHub-API-shaped JSON) -> `UNWIND/MERGE` into the `companyx_template` graph: Person, PR, Commit, File, Service(=top-level dir), AUTHORED/REVIEWED/CONTAINS/CHANGED/PART_OF. Idempotent. The OSS repo goes through the same ingest on Day 2, for the backtest only.
- 1:30 `derive`: KNOWS scores (your formula, hand-written). Indexes.
- 1:00 Radar query: services/dirs with exactly one knower.
- 1:00 Sanity-check against your ground-truth list from today. Tune weights.
- **Gate:** "who knows what" + bus-factor list on real data. Commit.

### Day 2, Fri Oct 16: the thesis (7 h)  _college day: if you get only 4 h, do the first three bullets only_
- 1:30 Dry run: `GRAPH.COPY` -> mark leaver inactive on the copy -> KT agenda query (things with zero other knowers, ranked). Assert the live graph is unchanged.
- 2:00 Decision extraction: Claude API reads the leaver's top ~30 PRs/review threads -> `{what, why, about[]}` JSON -> Decision nodes with a RECORDS edge to the source. Hand-check each, note accuracy (e.g. 24/30).
- 1:30 Why-trace endpoint: file -> Decision -> source path, every claim cites a node id.
- 1:00 **Backtest:** run the dry run as of the day before the leaver left. Compare the agenda to what actually broke / what the successor later had to ask or fix (issues, reverted PRs, "why is this" comments). Report precision/recall honestly.
- 1:00 Buffer.
- **Gate:** agenda + one why-trace + first backtest number. Commit.

### Day 3, Sat Oct 17: UI + handover + deploy (7+ h)
- 3:00 One React page: radar table -> "Simulate X leaving" -> agenda list -> click item -> why-trace path (react-force-graph). Let the AI scaffold the UI; you own the queries.
- 1:00 Handover tracker: "mark learned" adds `LEARNED` edge; counter N -> 0; one test that it clears the item.
- 1:30 **Deploy today:** FalkorDB Cloud (load graph once), Render (FastAPI), Vercel (UI). Read-only public site. Smoke-test from your phone.
- 1:00 Stretch if ahead: your own Claude Code sessions as AgentSession source, or the MCP `why(path)` tool.
- **Gate:** public URL works end to end.

### Day 4, Sun Oct 18: ship (6-7 h, submit by 8 PM IST, not 11:59)
- 1:30 README: thesis, data model, KNOWS formula, every Cypher query used, backtest table, why-not-RAG, privacy/consent, AI disclosure, tracks 03 + 02 (+01 only if MCP shipped).
- 1:30 Demo video (<= 3 min, own voice; script in PLAN §10, minus the parts you cut).
- 1:00 Blog post from your BUILD-LOG notes (side prize).
- 1:00 Fresh-clone test of your own README on a clean folder.
- 0:30 Submit, then verify the submission page shows repo, video, URL, tracks.

---

## 4. Daily habits that make this feasible
- Keep `BUILD-LOG.md`: 5 lines per day. It becomes the blog post and Rule 10 evidence.
- Commit at least every 90 min; export AI sessions to `docs/ai-log/`.
- **You write:** all Cypher, the KNOWS formula, agenda/dry-run logic, backtest scoring. **AI may write:** UI, FastAPI/MCP boilerplate, ingest plumbing, test scaffolds.
- Say "no recorded evidence anyone else knows this", not "nobody knows this".
- Pitch against **CodeScene** by name (its off-boarding simulation shows risky code but not the *why*, and doesn't hand reasoning to the successor).

## 5. Decision rules when behind
1. End of Day 1 not green -> shrink to a 300-PR slice of the repo; do not add sources.
2. End of Day 2 no backtest -> use a simple version (agenda vs 5 hand-listed facts); still report it.
3. Day 3 deploy fails by 3 h -> ship local Docker setup + recorded demo; Cloud is "preferred", not required.
4. Anything not in the keep column of §0 is dead until Day 4 is done.

---

## Ultra-lean (if 6-8 h is the TOTAL)
- Before Oct 15: do §1 steps 1-5 (they're not counted against the event).
- Build only: ingest 1 repo (2 h) -> KNOWS + dry-run agenda via `GRAPH.COPY` (2 h) -> single-page UI listing the agenda with the path for 2-3 hand-picked items (1.5 h) -> README + 2-min video (1.5 h).
- Skip: decision extraction by LLM (hand-write 5 Decision nodes from the repo), backtest (do the 5-fact check), deploy (local Docker + video).
- Or switch to the fallback, Custody (`CUSTODY-PLAN.md`): a smaller, more self-contained build.
