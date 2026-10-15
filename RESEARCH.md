# Graph Hacks × FalkorDB — Research Notes (2026-10-02)

## 1. The event
- **Name:** Graph Hacks: Context for AI Agents (WeMakeDevs × FalkorDB) — https://www.wemakedevs.org/hackathons/falkordb
- **When:** Oct 15, 12:01 AM IST → Oct 18, 11:59 PM IST (4 days, online). Registration open until deadline.
- **Teams:** solo or up to 4; one team per person.
- **Prizes ($20k):** Track 01 iPhone 18 Pro · Track 02 PS5 + GTA VI · Track 03 M6 Mac Mini (every team member). Best blog post: 5 × AirPods 5. Top 50 teams: t-shirts.
- **Sessions:** kickoff, FalkorDB workshop, office hours — dates TBA (page + FalkorDB Discord).

**Problem:** agents see pieces — forget earlier sessions, miss how people/systems/records relate, can't explain choices. Build an agent with FalkorDB as its context layer: *"the graph has to shape what the agent does, not sit on the side."*

### Tracks (one project may enter several; name each)
- **01 Agents That Act on Connected Data:** multi-hop reasoning, graph queries/algorithms as agent tools, MCP tool selection, actions based on graph, explainable results.
- **02 Agent Memory & Coordination:** episodic/semantic/procedural memory, persistent history, shared state + handoffs, high-concurrency reads/writes, per-user/tenant memory.
- **03 Company Brain:** docs/tickets/chats in one graph, who owns/knows what, decision tracing to source, keeping knowledge current, cited answers.

### Disqualifying rules
- **R3:** if the product still works with FalkorDB removed, the graph is decoration → doesn't qualify.
- **R6:** only public, synthetic, or own data.
- **R8:** main coding/design starts after Oct 15. Before: ideas, notes, graph-model sketches, diagrams only.
- **R10 submission:** public repo; README with setup **and graph data model**; **the Cypher queries/algorithms the product depends on**; demo video; live deployment (or full local setup); tracks entered.
- **R11–13:** disclose AI assistants; must be able to explain graph model, queries, architecture; fully AI-generated projects may be rejected.

### Judging (not published)
Recent WeMakeDevs sponsor events (Cognee, SigNoz, OpenMetadata) used: Impact · Creativity & Innovation · Technical Excellence · Best Use of sponsor · UX · Presentation (README + demo). Expect the same.

### The pivot
Wayback snapshot (Aug 11): originally *"Graph Hacks: Building Next-Gen RAG"*, September, $10k, tracks Investigation & Risk / Agentic AI / GraphRAG SDK. Relaunched: prize doubled, GraphRAG-SDK track dropped, Company Brain added → FalkorDB wants to be the **context/memory layer for agents**. Some fraud-ring repos were already built for the September version (crowded idea).

## 2. Organisers
**WeMakeDevs** — founder Kunal Kushwaha; 200k+ devs; positions itself as GTM engine for dev tools (sponsors pay for stars, signups, merged PRs; claims 80k+ stars, 400+ PRs). → Projects that make FalkorDB look good publicly (README, blog, posts tagging both) align with incentives.

**FalkorDB** — founded 2023 by ex-Redis engineers Guy Korland (CEO), Roi Lipman (built RedisGraph), Avi Avni; $3M seed (2024, Angular Ventures). Cypher, vector + full-text indexes, thousands of isolated graphs per instance (one per tenant). GitHub: FalkorDB ~6.6k★, QueryWeaver ~1.1k★, GraphRAG-SDK ~1k★ (claims 71.48 vs 55.39 vector RAG on GraphRAG-Bench). Also MCP server, falkordblite (embedded), Claude Code skills, Graphiti/Mem0/LangChain integrations. DevRel lead Liz Zhang writes their hackathon recaps.

**What FalkorDB praises (own write-ups, Aug/Sep 2026 SF hackathons):**
- "a two-hop Cypher traversal that a flat table or a vector search simply cannot express" (Atrium, 1st)
- "treats no path found as a real proof of safety… a negative result needs an actual traversal, not a similarity score" (Hopper)
- "The via column is the whole point… it says why" (results carry their reason)
- Read-only queries, 3s timeout, capped LIMIT; "the model got to suggest and a read-only query got to decide"; "Telling them the truth about what the system knows is the feature."
- Idempotent `UNWIND … MERGE` batch loads; one graph per user.

## 3. Previous winners
Full lists: `archive.wemakedevs.org/hackathons/<slug>/projects`

| Event (sponsor) | Winners → what they built |
|---|---|
| **Hangover Part AI** (Cognee, Jul '26; 8.5k reg, 1,200+ projects) — closest analog | **Lethe** (Vinayak Sonthalia): on-call memory that provably forgets decommissioned systems, benchmarked vs plain RAG · **Classroom Memory** (Rajdeep Singh): prerequisite graph → "teach functions before recursion" · Blog: Mahimai Raja J |
| Agents of SigNoz (Jul '26; 350+ projects) | OTel for CrewAI (Srinjoy Roy) · DebugProof (Dhruv Sachdev) · RootCause hydroponic farm (Shashwat Pratap Singh) |
| Pirates of the Coral-bean (Coral, May '26; 5.4k / 800+) | Manthan (Miny Labs) · GSoC/OSS Matchmaker (Yash Dedhia) |
| Back to the Metadata (OpenMetadata, Apr '26) | Himanshu · Prasanth Cherukuri · DUNE |
| Vision Possible (Stream, Feb '26) | ETMS elder safety · OceanWatch (Karthika M) · Watcher posture |
| 2 Fast 2 MCP (Archestra, Feb '26) | TrendOps (Anish) · Preffer (Veer Adyani) · AgriBot (Althaf Asharaf) |
| UI Strikes Back (Tambo, Feb '26) | DealDesk (CipherX) · Fireflow (Akinkunmi) · Brilliant (MergeConflict) |
| Backend Reloaded (Motia, Dec '25) | Orchestrix (Aymaan Pathan) · SocialOps · OpsGuard |
| AI Agents Assemble (Dec '25) | InFoundry (Rahul Joshi) · InfuseAI · Vriksha AI · Tria · Cadara |
| Lingo (Nov '25) | Podcastify (Honey Paptan) · SignLingua (Ariya P) · GlobSEO (Rahul Joshi) |
| FutureStack (Oct '25) | VoiceGraph (Honey Paptan) · Sure AI · SRE Sentinel (Aryan Kumar) |
| AgentHack (Portia, Aug '25) | DCRCA disaster agent · AML agent · YouTube Companion |
| Zerops / Scrape-Verse / Agent Harness (Aug '26) | Deplot AI · Research Factory, ScrapeSentry, PriceGuardAI · ONCALL, CapyGuard, QUEST, Mayday (blog) |
| First Commit (AWS, Sep '26) | Suraksha (aging-parent companion) · Beacon Night Shift (voice on-call) · CampusEvac |
| FalkorDB's Memory Meets Motion (Aug '26) | Atrium: each misconception a node; 2-hop query groups students |

## 4. Winning pattern
1. **Sponsor tech is load-bearing, README proves it** ("Why a Graph, Not a Vector Database"; proof points the data lives in FalkorDB).
2. **One-line contrarian thesis** (Lethe: memory that only grows is the failure).
3. **Measured proof vs a baseline** (Lethe vs RAG; GroundTruth 18/20 vs 0; DebugProof 100 vs 40). Graph-vs-vector eval speaks FalkorDB's language.
4. **Painful, specific job for a specific person.** "A small problem solved well beats a big one solved vaguely."
5. **Honesty & guardrails as features:** human approval, read-only queries, fail loudly, cite sources, "not documented" over hallucinating.
6. **Show the path** behind each answer (nodes/edges used).
7. **Judge can try it in 2 min:** live URL (14/18 Cognee picks), seeded data, keyless demo mode, ≤3-min video problem→fix. "One feature that runs beats five that almost do."
8. **MCP is common** among top entries; Track 01 asks for it.
9. **Stars don't matter; same people win repeatedly** (Honey Paptan, Rahul Joshi, Aryan Kumar, Ariya P, Aymaan Pathan) — deployed polished UI + clear README + video every time.
10. **Side prizes have better odds:** 5 blog winners; winning blogs are honest build logs that "do not skip the part where things broke."

**Overcrowded:** SRE/incident bots (~9 winning entries / 8 events), "memory that forgets stale facts" (~1/3 of Cognee top 20), fraud rings, codebase graphs (FalkorDB ships code-graph), generic chat-with-docs.

## 5. Pre-event checklist (allowed before Oct 15)
Pick idea · sketch graph model + key Cypher on paper · line up public data · write demo script · join FalkorDB Discord · attend kickoff/workshop. No product code.
