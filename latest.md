# Graph Hacks × FalkorDB: Summary, Past Winners, and Idea Ranking

_Researched 2026-10-10. Builds on RESEARCH.md (2026-10-02)._

The best fit is **Custody**, a graph firewall for multi-agent systems. It enters Track 01 and Track 02, and FalkorDB makes every allow-or-block decision, so the product stops working without it (Rule 3). Details are in section 3.

Until Oct 15, Rule 8 allows only ideas, notes, and graph-model sketches.

## 1. FalkorDB in brief

**What it is:** a graph database that holds the whole graph in memory, runs as a Redis module, and is queried with Cypher. It was founded in 2023 by the former Redis engineers who built RedisGraph. Its core idea is to store connections as sparse matrices (using the GraphBLAS library) and answer multi-step queries with matrix math. That makes queries that follow several connections in a row fast enough to run on every step an agent takes. Version 6.0 (Sep 29, 2026) moved to a new Rust engine: 39% fewer CPU instructions, 226 bugs fixed, and existing Cypher still works.

**What it solves:** AI agents and RAG systems retrieve text that looks similar. Real questions are usually about connections: "which accounts link to this?", "who has worked on this before?", "what breaks if X goes down?". Vector search can't follow those links, can't prove two things are *not* connected, and can't explain an answer. FalkorDB aims at that gap and markets itself as "the context layer for agents."

**How it's different**

| Alternative | What it is | How it compares |
|---|---|---|
| Neo4j | Market leader; Java, stored on disk, large algorithm library | FalkorDB's own benchmark shows p99 latency of 24–100 ms vs 1.3–2.5 s for Neo4j. The "496× faster" headline is the p99 ratio; at p50 the gap is about 13×. Vendor numbers. Neo4j wins on ecosystem and maturity. |
| Memgraph | In-memory, C++, Cypher | The closest rival. FalkorDB's edge is the matrix engine, Redis-style operations, and cheap per-tenant graphs. |
| Neptune / TigerGraph | Managed or enterprise products | FalkorDB runs locally with a single `docker run`. |
| Kùzu | Embedded graph database | Archived Oct 2025 after Apple bought the company. FalkorDBLite (embedded) targets its users. |
| Vector databases | Similarity search | No relationships, so they can't prove absence or show a path. FalkorDB has vector and full-text indexes inside the graph. |
| Graphiti / Mem0 / Cognee | Agent-memory frameworks | Not rivals: they run on top of FalkorDB. |

**Weak spots:**
- Data must fit in RAM.
- The SSPL license is not OSI-approved open source.
- The ecosystem is smaller than Neo4j's.
- A query sees one graph at a time.
- The 6.0 engine won't match the old C engine fully until 6.2.

**Features worth showing judges:**
- **One isolated graph per user, agent, or tenant:** thousands fit on one instance.
- **11 built-in algorithms:** BFS, shortest path (SPpath), path enumeration (SSpath), A*, minimum spanning forest, PageRank, betweenness, harmonic centrality, connected components (WCC), community detection (CDLP), and the new **MaxFlow**.
- **`GRAPH.COPY`:** snapshot copy of a whole graph, so you can try changes before applying them.
- **JavaScript UDFs with `graph.traverse()`:** custom read-only traversal logic.
- **`GRAPH.RO_QUERY`:** read-only queries, the safe way to let an agent query the graph.
- **MCP server and Browser:** tool access for agents and a visual explorer.
- ⚠ **On Oct 15:** check that the Docker image tag includes every procedure you rely on.

## 2. Past winners where the graph did real work

| Project (event) | What the graph did | Why it won |
|---|---|---|
| **Atrium**, 1st overall at FalkorDB's *Memory Meets Motion* (Aug '26) | Each misconception is a node; a two-step query groups students who share one | "a flat table or a vector search simply cannot express" |
| **Hopper**, standout at the same event | Chain from security advisory → package → repo → service → customer → contract clause, answered in under 100 ms | "treats no path found as a real proof of safety" |
| **Smart Home Orchestrator**, standout at the same event | Room → occupants → history of who conceded | "fairer over time because FalkorDB remembers who conceded last time" |
| **Board of SuperVision**, FalkorDB *Hack for Humanity* (Sep '26) | Votes stored as edges; read-only queries with a 3 s timeout and result limit | Every answer cites a video timestamp |
| **LOCAL GACHA**, same event | Two-step recommendations that return the reason for each | "The via column is the whole point" |
| **Lethe** and **Classroom Memory**, WeMakeDevs × Cognee winners (Jul '26) | Memory that provably forgets decommissioned systems, measured against plain RAG; a prerequisite graph for teaching | Contrarian thesis, measured baseline, specific user |

**What the winners have in common:**
- The question is a pattern across many records, not a text lookup.
- Every answer carries the path that produced it.
- "No path found" counts as proof only when a real traversal produced it.
- The model suggests and a read-only query decides.
- Memory builds up over time, and results are measured against a baseline.

**Crowded ideas to avoid:** fraud rings, security-finding triage, codebase graphs, SRE/incident bots, "memory that forgets stale facts," generic agent-memory layers (one Graph Hacks repo already exists), chat-with-company-docs, prerequisite tutors, and commitment trackers.

## 3. Ideas, ranked

### 🥇 1. Custody: a graph firewall for multi-agent systems (Tracks 01 + 02, recommended)

**Thesis:** prompt injection is a path problem, not a text problem. An agent becomes dangerous when untrusted content can reach its context and from there a tool that moves money or data. Filters read the text; Custody follows the path.

Every read, memory write, memory read, and agent-to-agent handoff becomes an edge in the graph. Before any risky tool call, one read-only query decides:

```
(:Source {trusted})-[:FLOWS_TO]->(:Content)-[:FLOWS_TO]->(:Session)-[:FLOWS_TO]->(:Memory)-[:FLOWS_TO]->(:Session)
(:Agent)-[:CAN_CALL]->(:Tool {sink})   (:Agent)-[:DELEGATES_TO]->(:Agent)   (:Incident)-[:CAUSED_BY]->(:Source)

Gate: MATCH p=(:Source {trusted:false})-[:FLOWS_TO*1..8]->(:Session {id:$sid}) RETURN p LIMIT 1
```

- **Gate:** if a path exists, block the call or ask a human, and show the path. If none exists, allow it; the empty result is the proof.
- **Recall:** if a source is flagged later, everything that came from it is quarantined: memories, sessions, and other agents.
- **Audit:** finds agents that, through chains of delegation, can reach untrusted input, private data, and a way to send data out (the "lethal trifecta").
- **Fix:** `algo.maxFlow` counts independent attack paths and finds the smallest set of permissions to revoke. Betweenness finds the chokepoint. `GRAPH.COPY` tries the fix on a copy first: rerun the audit, confirm zero paths, then apply it.

**Why it passes Rule 3:** a plain permission table says "Billing may refund," so the refund is allowed. Only the four-step path shows the refund request came from a poisoned ticket, via Support's note in shared memory. Without FalkorDB there is no gate at all.

**Why it should win:**
- It hits every pattern in section 2.
- It uses features only FalkorDB has: fast enough per step, one graph per tenant, MaxFlow, and `GRAPH.COPY`.
- Research backs it: DeepMind's CaMeL and Microsoft's FIDES show that tracking where data came from stops prompt injection. Snyk calls this "toxic flow" analysis. I found no project that runs it as a live graph.
- Timely: Graphiti's CVE-2026-32247 let prompt injection reach Cypher through an MCP tool.

**Demo (under 3 min):**
1. Three agents (Support, Billing, Outreach) work a mock helpdesk.
2. A poisoned ticket arrives; Billing's refund call is blocked with the path shown.
3. Switch Custody off and rerun: the money moves. That shows Rule 3 live.
4. The audit suggests revoking two permissions; you try it on a copy and get zero paths.
5. Scoreboard over about 30 injection scenarios: attack success rate for a plain agent, a per-tool allowlist, and Custody, plus false blocks and gate p95 latency.

**Watch-outs:**
- If everything an agent touches is tainted, everything gets blocked. Add a `SANITIZED` edge for fields that passed schema validation, as CaMeL does.
- Always pass values to Cypher as parameters; never let the LLM build query text. That is how the Graphiti CVE happened.

### 🥈 2. Dry Run: rehearse a company change before you make it (Tracks 03 + 01)
Most Company Brain entries answer questions; this one tests changes, e.g. "the only payments engineer goes on leave" or "deprecate API v1."
- Copy the company graph with `GRAPH.COPY`, apply the change to the copy, and run checks (every production service still has an owner and a backup; no live decision depends on a deprecated system).
- The agent explains each break as a path back to source docs, proposes a stand-in using harmonic centrality, and on approval applies the change and files tickets.
- **Weakness:** harder to measure against a baseline than #1.

### 🥉 3. Relay: give each agent only the graph it needs (Track 02)
When agent A hands work to agent B, B gets the part of the graph within a few steps of the task, not the full transcript or a top-k vector search.
- **Demo:** an airline-cancellation storm with hundreds of simultaneous writes shows off Track 02's concurrency focus.
- **Metric:** tokens per handoff and correct-outcome rate, versus full-transcript and vector top-k.
- **Weakness:** the demo is less dramatic.

### 4. Wildcard: Paperwork Pathfinder (Tracks 01 + 02)
Indian government services modeled as a graph of what each requires: service → documents → issuing office → that office's requirements.
- Each user has their own graph remembering which documents they already hold. The agent returns the shortest remaining sequence of steps, or "no path, and here is the missing link," each step cited to its public source.
- **Why it could win:** prerequisite graphs have won before, and the domain hits home for this audience.
- **Risk:** collecting the rules data takes time.

**Pick: #1 (Custody).** Strongest two-minute demo, a hard number against a baseline, FalkorDB is clearly what makes it work, and it enters two tracks.

## Sources

- Event: [Event page](https://www.wemakedevs.org/hackathons/falkordb) · [Rules](https://www.wemakedevs.org/hackathons/falkordb/rules) · [Existing Graph Hacks memory repo](https://github.com/renigat7-cpu/graph-hacks-2026)
- FalkorDB: [Site](https://www.falkordb.com/) · [6.0 release](https://www.falkordb.com/blog/announcing-falkordb-6-0/) · [Memory Meets Motion](https://www.falkordb.com/blog/memory-meets-motion-the-falkordb-standouts/) · [Hack for Humanity](https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems/) · [MaxFlow/UDF](https://www.falkordb.com/news-updates/falkordb-graph-database-algorithms-maxflow-udf/) · [Agent memory thesis](https://www.falkordb.com/blog/ai-agent-memory-retrieval-architecture/)
- Docs and benchmarks: [Algorithms](https://docs.falkordb.com/algorithms) · [UDFs](https://docs.falkordb.com/udfs) · [GRAPH.COPY](https://docs.falkordb.com/commands/graph.copy.html) · [Benchmark](https://benchmark.falkordb.com/) · [GitHub](https://github.com/FalkorDB/FalkorDB)
- Kùzu: [Kùzu status](https://www.puppygraph.com/blog/what-is-kuzudb)
- Agent security: [CaMeL](https://arxiv.org/pdf/2503.18813) · [FIDES](https://arxiv.org/pdf/2505.23643v2) · [Snyk toxic flows](https://snyk.io/es/articles/understanding-toxic-flows-mcp/) · [CVE-2026-32247](https://sentinelone.com/vulnerability-database/cve-2026-32247/)
