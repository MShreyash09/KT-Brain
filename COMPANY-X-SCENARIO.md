# Company X: The Demo Scenario (story bible + answer key)

_Written 2026-10-14 as a design note (allowed under Rule 8). The generator script and data files get built from Oct 15. All of this data is **synthetic**; label it that way in the README._

---

## 0. The core idea: simulate 6 months, demo in 3 minutes

Three days of company history is too thin: knowledge doesn't pile up on one person in 3 days. **Simulated time is free.** Generate ~6 months of timestamped events, then **replay** them in the UI (6 months in ~20 seconds), so the graph visibly grows. Then trigger the resignations.

```
STORY BIBLE (this file, hand-written: personas, decisions, answer key)
      │  Day 1: Claude expands each "beat" into realistic artifacts (generated once, hand-checked, committed)
      ▼
FIXTURES  data/companyx/  (GitHub-API-shaped PRs/commits/reviews, Slack-export-shaped threads,
      │                    Jira-like tickets, AI-session JSON; every event has a timestamp `at`)
      │  the same connectors you'd point at real GitHub/Slack later
      ▼
REPLAY  "play" ingests events in time order into graph `companyx_template`
      ▼
PER-VISITOR SANDBOX  GRAPH.COPY companyx_template → sandbox_<id>
      (each judge clicks "resign" on their own copy; delete sandboxes after 1 h)
```

Why this design:
- **Fixtures, not live LLM calls:** the demo is deterministic and keyless, and you know the right answers.
- **Real export shapes:** proves the connectors would work on real data, not just a toy.
- **Per-visitor `GRAPH.COPY`:** the public demo can't be broken by one judge, and it shows off FalkorDB multi-tenancy for free. It also fixes the free-tier deletion problem: a "reset" is just re-running the seed.

---

## 1. The company and the product

**Company X → "TiffinBox"**, a fictional meal-subscription startup: web app, API, payments, delivery-time (ETA) model, recommendations. The payment gateway is fictional too, so you make no claims about a real company.

| Person | Role | Fate |
|---|---|---|
| **Kavya** | Frontend | stays |
| **Arjun** | Backend (payments, orders, auth) | **resigns Sep 15, last day Sep 30** |
| **Priya** | DevOps (CI/CD, Terraform, secrets, backups) | **resigns Sep 15, last day Sep 30** |
| **Rohan** | AI/ML (recommendations, ETA) | stays |
| **Neha** | Product manager (PRDs, tickets, ADRs) | stays |
| **Meera** | New backend dev | **joins Sep 22** (one overlap week = the KT window) |

Simulated timeline: **Apr 1 → Sep 30, 2026.**

### Files (~20; Service = top-level folder)
- **web/** `checkout/CheckoutPage.tsx`, `menu/MenuGrid.tsx`, `lib/api.ts`
- **api/** `payments/retry.py`, `payments/webhooks.py`, `orders/service.py`, `auth/tokens.py`, `subscriptions/billing.py`, `recommend/endpoint.py`
- **infra/** `terraform/main.tf`, `k8s/api-deploy.yaml`, `backup/db_backup.yaml`, `.github/workflows/deploy.yml`, `.github/workflows/ci.yml`, `scripts/rotate_secrets.sh`
- **ml/** `recommend/model.py`, `recommend/features.py`, `eta/predict.py`
- **docs/** `prd/subscriptions.md`, `adr/0003-webhook-idempotency.md`, `runbooks/deploy.md`

Dependencies: web → api; api → infra; ml → api.

---

## 2. Planted decisions (this IS the answer key)

> **Built 2026-10-15:** fixtures are in `data/tiffinbox/` and the authoritative key is `data/tiffinbox/answer_key.json` (checked by `build.py`). Changes from this table: chat is **Google Chat** (not Slack); D15 is also known by Arjun and Kavya (they built and reviewed it); the superseded decisions D16 (deploy all at once) and D17 (untested backups) were added; N = **12** when both leave (3 of them only in that case: D8, `rotate_secrets.sh`, `api-deploy.yaml`); and docs are sources, not agenda items.

| ID | Decision (what + why) | Recorded in | Knowers | Purpose in the demo |
|---|---|---|---|---|
| D1 | Payment retries = 7, because the gateway's webhooks drop for ~5 min during its deploys | Slack thread → ticket PAY-88 → Arjun's AI session → PR | **Arjun only** | the star why-trace |
| D13 | (old) retries = 3 | PR in April | Arjun | **superseded by D1**; must NOT show as current |
| D2 | Webhooks are idempotent via `event_id` | PR + ADR 0003 (Neha wrote the ADR) | Arjun + **Neha** | **decoy:** looks backend-only, but the PM documented it, so it's covered |
| D3 | Orders use optimistic locking (double orders at lunch rush) | PR reviewed by Rohan | Arjun + Rohan | covered |
| D4 | Auth token TTL = 15 min (security review) | PR reviewed by Kavya | Arjun + Kavya | covered |
| D5 | Billing: charge on day 1, prorate pauses | PRD + PR | Arjun + Neha | covered |
| D6 | Deploys are canary: 10% for 30 min, after the May checkout outage | incident thread + AI session + PR | **Priya only** | orphan |
| D7 | Terraform state is locked remotely; never run `apply` from a laptop | PR + Slack | **Priya only** | orphan |
| D8 | Rotating the gateway API key also requires updating the webhook secret, or payments silently fail | Slack thread between Arjun and Priya + `rotate_secrets.sh` | **Arjun + Priya** | ⭐ **combination risk:** covered if either one leaves alone, **orphaned only when both leave** |
| D9 | DB backups at 3 AM IST; restore tested quarterly | runbook + PR | **Priya only** | orphan |
| D10 | Recommendations exclude price as a feature (bias complaint) | ticket + AI session | Rohan only | orphan risk, but Rohan stays (shows on the radar, not the agenda) |
| D11 | ETA falls back to a static 40 min if the model times out | PR by Rohan, reviewed by Arjun | Rohan + Arjun | covered by Rohan |
| D12 | Checkout button disables after one click (double-payment fix) | PR by Kavya, reviewed by Arjun | Kavya + Arjun | covered by Kavya |
| D14 | CI cache key includes the lockfile hash (flaky builds) | PR by Priya; Kavya touched `ci.yml` once | Priya + **Kavya (weak)** | "weak backup": Kavya becomes the suggested DevOps mentor |
| D15 | Subscription pause is capped at 2 weeks | PRD | Neha only | PM-only knowledge; Neha stays |

### Expected results (write these as tests on Day 1)
| Dry run | Agenda must contain | Must NOT contain |
|---|---|---|
| Arjun leaves alone | D1, `retry.py`, `webhooks.py` code | D2, D3, D4, D5, D8 (others cover them), D13 (superseded) |
| Priya leaves alone | D6, D7, D9, `deploy.yml`, `main.tf`, `db_backup.yaml`; D14 marked *weak backup: Kavya* | D8 (Arjun covers it) |
| **Both leave** | the union of the two rows above **plus D8** | D2, D3, D4, D5, D11, D12 |
| After Meera's KT session + her first PRs on `retry.py` / `webhooks.py` | backend items clear; infra items remain | – |

The final state of the story: "**6 DevOps items aren't covered by anyone**. Suggested: Kavya (nearest, via D14 and `ci.yml`), or hire." The graph has just produced a hiring signal.

---

## 3. Event volume (enough to look real, small enough to hand-check)

| Kind | ~Count | Format to mimic |
|---|---|---|
| Commits | 120 | GitHub API commit (sha, author, date, message, files[]) |
| PRs + reviews | 45 PRs, ~70 reviews | GitHub API pulls + reviews |
| Tickets | 35 | Jira-like JSON (key, title, assignee, status, links) |
| Slack threads | 50 across `#eng`, `#payments`, `#infra`, `#incidents`, `#product` | Slack export (per channel: messages with `user`, `ts`, `thread_ts`) |
| AI sessions | 20 (Claude Code / Codex) | {id, user, tool, started_at, cwd, branch, files_touched, summary, excerpt} |
| Docs | 6 (PRD, ADR, runbooks) | markdown + front-matter author/date |
| Noise | ~40% of events: typo fixes, lunch chat, dependency bumps | tests that the KNOWS weighting ignores trivia |

**Generation (Day 1, ~2 h):** write ~40 one-line "beats" (e.g. "May 12: checkout outage; Priya leads incident; decides canary deploys → D6"). Have Claude expand each beat into its artifacts in the formats above, with consistent ids and timestamps. **Hand-check every artifact behind D1-D15.** Commit the JSON. Disclose this in the AI-use section.

Optional realism (+45 min): a tiny real git repo for TiffinBox with the ~20 files and back-dated commits per persona (`git commit --date` plus per-commit author). Then the why-trace can show the real `RETRIES = 7` line. PRs, reviews and issues can't be back-dated on GitHub, so those stay as fixtures.

---

## 4. The live demo (≈ 3 min)

| # | Click | The graph shows | Line |
|---|---|---|---|
| 1 | **Play** (Apr → Sep in 20 s) | nodes appear by week; radar fills: infra = 1 knower, api/payments = 1 knower | "This is TiffinBox's last 6 months, captured as it happened." |
| 2 | **Sep 15: Arjun and Priya resign** → *Simulate departure* | `GRAPH.COPY` → agenda: **N items with no recorded backup**, ranked by criticality | "Two weeks' notice. Here's exactly what walks out the door." |
| 3 | Toggle *Arjun only* / *Priya only* / *both* | D8 appears only for *both* | "Each of them alone looked safe. Together they take the payment-key rotation with them." |
| 4 | Ask plain RAG "what does only Arjun and Priya know?" | vague text, no proof | "Search can't prove nobody else knows something. The graph can." (Rule 3) |
| 5 | Click D1 | path: `retry.py` ← commit ← Arjun's AI session ← PAY-88 ← #payments thread | "Every answer is a path with sources." |
| 6 | **Sep 22: Meera joins** → KT session marks items; her PRs land | LEARNED edges; counter **N → 6** | "KT is done when the number hits zero, not when the call ends." |
| 7 | Remaining 6 are infra | suggestion: Kavya (weak backup), or hire DevOps | "The graph just wrote the hiring req." |
| 8 | (stretch) Meera's Claude Code calls `why("api/payments/retry.py")` via MCP | warns about the gateway's deploy gaps | "Her agent inherited Arjun's memory." |
| 9 | Switch to *Real OSS repo* | the backtest numbers | "And it isn't just our toy company." |

---

## 5. Where this fits in the roadmap
- **Today:** finish this file. Change names or the product if you like; keep D2 (decoy), D8 (combination) and D13 (superseded). They are what make the demo convincing.
- **Day 1:** generate fixtures → ingest Company X first (you know the answers, so query bugs are obvious) → the tests in §2.
- **Day 2:** dry run, why-trace, then the OSS repo for the backtest only.
- **Day 3:** replay button + per-visitor sandbox (`GRAPH.COPY` + expiry) + deploy.
