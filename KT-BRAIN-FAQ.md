# KT Brain: 11 Hard Questions, Answered

_Researched 2026-10-14. Companion to `KT-BRAIN-PLAN.md` and `KT-BRAIN-ROADMAP.md`. Numbers marked **(est.)** are my back-of-envelope estimates; measure them on Day 1. Vendor claims are marked as vendor claims._

---

## 1. SaaS, browser extension, or software?

**Answer: a web app plus two small helpers. Not a browser extension.**

| Piece | Form | Why |
|---|---|---|
| The brain (graph + API + UI) | Web app. Self-hostable with Docker Compose first; managed SaaS later | The data is sensitive (see Q2 and Q8), so startups will want it in their own cloud |
| Connectors | Server-side jobs that use each tool's API or webhooks (GitHub, Slack, Jira…) | The data already lives in company systems, so nothing needs to run in a browser |
| Local collector | A tiny opt-in CLI on the dev's laptop that uploads AI-session logs (Claude Code, Codex) | Those logs live on the laptop (Q10) |
| Successor's agent | An MCP server (`why(path)`, `who_knows(topic)`) | This is how the brain reaches Claude Code or Cursor (Track 01) |

**Why not an extension:** an extension that reads every tab looks like surveillance (Q6). It also breaks on every UI change, and it covers only one browser. The one case it would fit is ChatGPT on the web without an Enterprise plan, and even there a manual "export and share this chat" step is better.

**For the hackathon:** the web app (Render + Vercel + FalkorDB) and the local collector reading your own logs. MCP is a stretch goal.

---

## 2. Private data in chats (env keys, research, finance sheets)

**Answer: the safest secret is one you never ingest. There are five layers, and the first two do most of the work.**

1. **Allowlist, not blocklist.** Ingest only channels and projects an admin opts in (e.g. `#eng-payments`, `#incidents`). Never DMs, never `#finance` or `#hr`. A connector that isn't invited to a channel can't read it: Slack and Google Chat apps only see conversations they're added to.
2. **Store decisions, not raw text.** The graph keeps `{what, why}` plus a **link** back to the source message, not the message itself. A finance sheet or research doc becomes a node with a title and a permission, not its contents.
3. **Redact before anything leaves the source or reaches an LLM.** Run a secret scanner (regex + entropy, e.g. open-source `gitleaks` or `detect-secrets`) and a PII pass on every text. Anything flagged gets masked (`sk-****`), and that text is never sent to the LLM.
4. **Permissions live in the graph.** `(:Person)-[:MEMBER_OF]->(:Channel)<-[:IN]-(:Thread)-[:RECORDS]->(:Decision)`. Every query filters by what the asking user could already see. This is one more reason the graph is load-bearing (Rule 3). Viven, a funded competitor, built a "pairwise context and privacy" system for the same problem ([source](https://founders-daily-briefing.beehiiv.com/p/viven-raises-35m)).
5. **Reuse existing DLP; don't rebuild it.** Nightfall, GitGuardian and Strac already scan Slack for API keys and PII ([Nightfall](https://www.nightfall.ai/integrations/slack-dlp), [GitGuardian](https://docs.gitguardian.com/internal-monitoring/integrate-sources/messaging-integrations/slack), [Strac](https://slack.com/marketplace/A0A3YFHRF1Q-strac-dlp-enterprise)). KT Brain should sit behind them, not compete with them.

**For the hackathon:** use only public and synthetic data, add a redaction pass with one test (a fake `sk-…` key never reaches the graph or the LLM), and put a short "Data safety" section in the README with the five layers. Judges will ask.

---

## 3. How much compute, from day 1 into the future?

**Answer: very little. The graph stays small if you keep raw text out of it, and the LLM bill is bigger than the server bill.**

Assumptions **(est.)**, per developer per year: ~800 commits, 250 PRs, 400 reviews, 200 tickets, 1,500 messages in allowlisted channels, 600 AI sessions, about 100 extracted decisions. That's roughly **4k nodes and 15k edges per dev-year**.

| Stage | Nodes / edges (est.) | RAM for FalkorDB (est., no raw text) | Fits on |
|---|---|---|---|
| Hackathon: 1 OSS repo (~3k PRs) | ~20-50k / ~100-200k | < 100 MB | free tier / laptop |
| 10 devs x 1 year | ~40k / ~150k | ~50-100 MB | 1 GB instance |
| 50 devs x 3 years | ~600k / ~2M | ~1-2 GB | 2-4 GB VM |
| 500 devs x 5 years | ~10M / ~40M | ~10-20 GB | one 32 GB machine |

- **CPU is tiny.** Ingestion runs when events happen, KNOWS is recomputed nightly, and queries take milliseconds.
- **RAM is the real limit.** FalkorDB holds the whole graph in memory ([weak spot noted here](https://www.stork.ai/de/falkordb)). So the design rule is: **raw text goes in cheap storage (Postgres or S3); the graph holds ids, summaries and edges.**
- **Measure it on Day 1:** load the OSS repo, check memory with Redis `INFO memory`, and replace these estimates with real numbers in the README. That's a strong answer for judges.

---

## 4. Where does AI work in this idea?

**Answer: AI reads and writes text. The graph decides. That split is the Rule 3 argument.**

| Step | AI (LLM) | Graph (Cypher, deterministic) |
|---|---|---|
| Turn a PR, thread or AI session into `{what, why, about[]}` Decision nodes | yes (Sonnet 5.5; Haiku 5.5 as a cheap pre-filter) | stores it with a RECORDS edge to the source |
| Link fuzzy mentions ("the retry thing") to files or services | partly (suggests a match) | the match is confirmed by shared files and time window |
| Who knows what (KNOWS score) | no | yes: weighted, time-decayed formula |
| KT agenda: what only the leaver knows | no | yes: "zero other knowers" query on a `GRAPH.COPY` |
| Criticality, best mentor | no | yes: betweenness / harmonic centrality |
| Explain a why-trace in a sentence | yes: narrates the returned path, citing node ids | returns the path |
| Draft the questions to ask the leaver in the KT call | yes, one set per agenda item | picks the items |
| Successor's coding agent asks before editing | the agent asks | the MCP tool answers with read-only queries |

If you remove the LLM, you still get the agenda, the bus-factor radar and the handover counter; you lose the nice sentences. If you remove FalkorDB, nothing is left. That is exactly what Rule 3 wants.

---

## 5. Is it economical for a startup to run?

**Answer: yes. It costs roughly the same as one or two seats of a SaaS tool, and it protects against a loss worth months of salary.**

- **Running cost for a 20-dev startup (est.):** ~$50-150 per month in total (breakdown in Q9).
- **The alternative:** Glean is estimated at ~$50 per user per month with a ~100-seat minimum, about $60k a year. Those are third-party estimates; Glean doesn't publish prices ([eesel](https://www.eesel.ai/blog/glean-ai-pricing), [GoSearch](https://www.gosearch.ai/blog/glean-pricing-explained)). Unblocked starts at ~$19 per user per month per one aggregator, which I couldn't confirm ([PricingSaaS](https://pricingsaas.com/companies/unblocked)).
- **The loss it prevents:** HR sources put replacement cost at 50-400% of salary. Those figures are weak and unverified, so don't quote them as fact. A safer framing you can compute yourself: a ₹12 LPA dev ramping at ~50% productivity for 3 months costs about ₹1.5L in lost output **(est.)**. If KT Brain cuts ramp-up by even a few weeks for one hire a year, it has paid for itself.
- **Cost levers:** pre-filter with Haiku 5.5 ($0.10 / $0.50 per million tokens), send only real decision candidates to Sonnet 5.5 ($2 / $10), and use the Batch API (50% off) for the nightly run. A tiny team can self-host the open-source version for the price of one VM.

---

## 6. Are we tracking employees 24/7?

**Answer: no, and the README should say so in bold.**

- **What it reads:** work artifacts the company *already stores*: commits, PRs, reviews, tickets, and opted-in channels. It is event-driven: nothing happens until a dev pushes a commit or posts in an allowlisted channel.
- **What it never reads:** keystrokes, screens, browsing, DMs, hours online, or private chats.
- **What it never computes:** productivity scores or per-person output rankings. It measures **knowledge coverage per topic** ("payments has one knower"), not how hard someone works.
- **AI sessions are the sensitive part,** so they are opt-in and curated by the developer ("share this session to KT Brain"), never collected silently.
- **The employee sees their own graph** and can flag mistakes.
- **Legal (India, DPDP Act 2023):** Section 7(i) allows some processing "for purposes of employment" without consent. Lawyers disagree on how far that goes, and a union-side reading says monitoring that judges *efficiency* needs consent ([LiveLaw](https://www.livelaw.in/articles/employment-surveillance-clauses-void-dpdp-regime-539957), [KS&K](https://ksandk.com/data-protection-and-data-privacy/can-employers-monitor-employees-dpdp-act/), [Mondaq](https://webiis10.mondaq.com/india/data-protection/1755320/is-consent-required-to-process-employees-personal-data-under-the-dpdp-act)). The core provisions take effect on **13 May 2027**. The safe design is **explicit consent at onboarding plus no productivity metrics**. This is not legal advice.
- **After exit:** a retention policy, e.g. keep decisions and links, and drop personal-ish data such as AI-session text after N months.

---

## 7. Why is FalkorDB core? Why not Neo4j?

**First, why a graph at all:** the key question is "which knowledge has **zero** other knowers, through any path (authored, reviewed, decided, learned)?" That is proving *absence* across multi-hop relationships. A vector DB returns similar text; it can't prove nobody else touched something. SQL can, but only with a pile of recursive joins that gets rewritten for every new edge type.

**Why FalkorDB specifically (honest version):**

| Need in KT Brain | FalkorDB | Neo4j |
|---|---|---|
| Dry-run a departure without touching the live graph | `GRAPH.COPY` clones a whole graph in one command ([docs](https://docs.falkordb.com/commands/graph.copy.html)) | Community Edition allows exactly **one** database ([Neo4j docs](https://neo4j.com/docs/operations-manual/current/database-administration/)); cloning means Enterprise multi-database plus admin copy tooling |
| One isolated graph per company (SaaS later) | Many graphs in one instance; the vendor claims 10k+ tenants ([FalkorDB](https://docs.falkordb.com/cloud/features)) | Community: one DB, so in practice one instance per tenant ([example](https://docs.cognee.ai/core-concepts/multi-user-mode/dataset-database-handlers/existing-dataset-database-handlers/neo4j-community)) |
| The successor's coding agent calls `why()` before every edit | In-memory, low latency (vendor benchmark: p99 24-100 ms vs 1.3-2.5 s for Neo4j; vendor numbers) | Slower in that benchmark; more mature |
| Read-only access for agents | `GRAPH.RO_QUERY` | read-only transactions (comparable) |
| Graph algorithms | betweenness, harmonic, PageRank, WCC, CDLP, MaxFlow built in | GDS library is larger |
| Price | Startup tier from $73/month for 1 GB ([FalkorDB](https://docs.falkordb.com/cloud/startup-tier)) | Aura Professional $65/GB/month ([Neo4j](https://neo4j.com/cloud/aura/pricing/)): **about the same** |

**What to say to judges:** "Neo4j *could* run these queries. FalkorDB makes the two things this product depends on cheap and native: a throwaway copy of the company for every what-if, and a separate graph per company. Price is not the reason." Also admit the weaknesses: RAM-bound, SSPL licence, smaller ecosystem.

---

## 8. Is the data on the startup's infra or our cloud?

**Answer: on the startup's infra by default. That is the only answer that survives Q2 and Q6.**

| Mode | Where data lives | LLM | Who it's for |
|---|---|---|---|
| **Self-hosted (default)** | Docker Compose in the startup's own VPC | the startup's own Anthropic key, or Claude via Bedrock/Vertex in their cloud | most startups |
| **BYOC** | FalkorDB Cloud running in *their* AWS/GCP/Azure account ([FalkorDB startup tier: BYOC](https://docs.falkordb.com/cloud/startup-tier)) | same | teams that want managed ops |
| **Managed SaaS (later)** | our cloud, one isolated graph per company (FalkorDB multi-tenancy) | ours | small teams that just want it working |
| **Hackathon demo** | our free-tier deployment, public and synthetic data only | ours (keyless demo mode uses pre-extracted decisions) | judges |

---

## 9. Total cost

**For the hackathon: about $0-5.**

| Item | Cost |
|---|---|
| FalkorDB Cloud free tier (100 MB) | $0. **Warning:** instances idle for a day are stopped and **deleted after 7 days** ([docs](https://docs.falkordb.com/cloud/free-tier)). Judging happens after Oct 18, so either schedule a daily keep-alive query (e.g. a GitHub Actions cron), or host FalkorDB in Docker on a free VM, and keep a seed script so the graph can be rebuilt in one command |
| Render free (backend) + Vercel free (frontend) | $0 (Render sleeps; first request takes ~50 s) |
| Claude API for decision extraction on one repo | ~$1-5 **(est.)**: a few hundred PRs at a few thousand tokens each through Haiku 5.5, plus Sonnet 5.5 on the real candidates |

**For a 20-dev startup in production (est., per month):**

| Item | Self-hosted | Managed |
|---|---|---|
| FalkorDB | in a 4 GB VM, ~$20-40 | FalkorDB Cloud Startup, from $73 |
| Backend + connectors + nightly job | same VM or +$10-25 | +$10-25 |
| Raw-text storage (Postgres/S3) | ~$0-10 | ~$0-10 |
| LLM: Haiku pre-filter on everything, Sonnet on ~20%, Batch API | ~$15-50 | ~$15-50 |
| **Total** | **~$40-100** | **~$100-160** |

LLM estimate behind that row: ~3.6k items a month; Haiku reads ~10-40M tokens ($1-4), and Sonnet reads ~5-10M tokens and writes ~0.5M ($15-25). Batch API halves it. Long AI sessions are the biggest variable, so measure on Day 2.

---

## 10. Handling many tools (ChatGPT, Codex, Claude Code, Slack, Google Chat, research tools)

**Answer: one connector per tool, all writing one common event shape. The graph doesn't care where an event came from.**

```
tool API / log file → connector → common event {actor, at, source, kind, text_ref, links[]}
                    → redact (Q2) → LLM decision extraction → MERGE into graph
```

| Source | How to get it | Notes |
|---|---|---|
| GitHub / GitLab | REST API + webhooks | the backbone; start here |
| Slack | bot invited to allowlisted channels; Events API | DLP tools already exist (Q2) |
| Google Chat | Chat API app added to specific spaces | same allowlist model |
| Jira / Linear | REST + webhooks | link a ticket to a PR through ids in the PR title or branch name |
| **Claude Code** | local JSONL under `~/.claude/projects/` (opt-in collector); on Enterprise, the Compliance API covers Claude Code sessions ([Anthropic docs](https://platform.claude.com/docs/en/manage-claude/compliance-api.md)) | you already have your own logs; use them |
| **Codex CLI** | local JSONL under `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` ([source](https://codex.danielvaughan.com/2026/04/13/codex-cli-session-management-resume-fork-transcripts)); verify on a real install | same collector |
| **ChatGPT** | Enterprise: Compliance API / Compliance Logs Platform, JSONL exports ([OpenAI](https://openai.com/index/new-tools-for-chatgpt-enterprise)); other plans: the user's own data export, shared manually | opt-in only |
| Notion / Google Docs | their APIs; store title + link + extracted decisions | not full text |
| Other research tools | "save to brain" by URL | don't build 20 connectors |

**The two hard parts (put both in the README):**
1. **Identity:** the same person shows up as different handles in different tools. `(:Person)-[:HAS_ACCOUNT]->(:Account {tool, handle})`, matched by work email.
2. **Linking AI sessions to code:** match on working directory + branch + files touched + a time window around the commit. Store a `confidence` on the edge and show it in the UI.

**For the hackathon:** GitHub + Claude Code + Codex local logs only. Mention the rest as the connector roadmap.

---

## 11. Is this really needed? Is it worth the hackathon?

**Answer: yes. The need is measured, and investors are already paying for this space. The risk is looking like chat-with-docs, and the coverage thesis is what avoids that.**

**Proof that the problem is real:**
- 68% of developers hit a knowledge silo at least once a week (Stack Overflow 2022). 61% spend more than 30 minutes a day searching for answers, and 3 in 4 answer questions they've answered before (Stack Overflow 2024) ([2022](https://stackoverflow.blog/2022/06/22/asked-and-answered-the-results-for-the-2022-developer-survey-are-here/), [2024](https://survey.stackoverflow.co/2024/professional-developers), [2024 insights](https://stackoverflow.co/teams/resources/your-developers-deserve-better-insights-from-the-2024-developer-survey)).
- Research: a newcomer takes considerable time to match a departing core developer, and more orphaned code is linked to more defects ([arXiv 2207.12851](https://arxiv.org/pdf/2207.12851)).
- Your own startup: KT ranges from a 1-hour call to weeks, and layoff KT is rushed. That is your demo story.

**Proof the market is real (and crowded):**
- Viven raised a $35M seed (Khosla, Oct 2025) to build AI "digital twins" of employees that coworkers can query when the person is unavailable ([TechCrunch](https://techcrunch.com/2025/10/15/eightfold-co-founders-raise-35m-for-viven-an-ai-digital-twin-startup-for-querying-unavailable-coworkers), [SiliconANGLE](https://siliconangle.com/2025/10/15/ai-startup-viven-raises-35m-create-digital-twins-fill-absent-team-members/)).
- Unblocked answers "why" questions across Slack, Jira and GitHub for devs and agents ([StackPick](https://www.stackpick.net/pricing/unblocked/)).
- CodeScene's off-boarding simulator highlights code at risk when developers leave ([docs](https://codescene.io/docs/guides/simulations/offboarding-simulator.html)).
- Glean: enterprise search at ~$60k/year minimum (est.).

**How KT Brain is different:**

| | Glean | Unblocked | Viven | CodeScene | **KT Brain** |
|---|---|---|---|---|---|
| Core idea | search company knowledge | answer "why" questions for devs and agents | query an AI twin of an absent coworker | code-ownership risk from code analysis | **measure and close the KT gap** |
| Answers questions you ask | yes | yes | yes | no | yes (why-trace) |
| Tells you what you **didn't know to ask** (only-one-knower list) | no | no | no | partly (code only) | **yes, with a zero-other-knowers query** |
| Dry-run a departure before it happens | no | no | no | yes (code only) | **yes, on a `GRAPH.COPY`, across code + decisions + AI sessions** |
| The *why* behind code (decisions, threads, AI sessions) | partly | yes | yes | **no** (the docs page mentions no decisions, chats, tickets or AI sessions) | **yes, as a cited path** |
| AI coding sessions as a knowledge source | no | not shown | not shown | no | **yes** |
| Tracks the handover until it's done | no | no | no | no | **yes: LEARNED edges, N → 0** |
| Hands the leaver's reasoning to the successor's coding agent | no | for agents in general | no | no | **yes, via MCP, scoped to the files being edited** |

(Rows marked "no" or "not shown" are based on public pages; I didn't find these features, which isn't proof they don't exist. In the README, say "we found no product that combines…", not "first ever".)

**One-line pitch:** *Everyone else answers questions about knowledge. KT Brain finds the knowledge that is about to walk out the door, proves nobody else has it, and counts the handover down to zero.*

**Verdict:** worth it, as long as the demo leads with the dry-run agenda and the backtest, not with a chat box.
