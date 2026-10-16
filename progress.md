# KT Brain: build progress

Running log. Plan: `HACK-PLAN.md` §5. Rebuild + check everything from `backend/`:

```
python ../data/tiffinbox/build.py           # regenerate fixtures, re-check the answer key
uv run python -m ingest.fixtures            # rebuild graph tiffinbox_template (full story, to Sep 30)
uv run python test_answer_key.py            # Day 1 gate (Sep 21 snapshot)
```

## Day 1, Thu Oct 15: engine on TiffinBox ✅ gate passed

| Item | Status | Notes |
|---|---|---|
| Docker FalkorDB pinned + `check_db.py` | ✅ | graph module 6.0.2: GRAPH.COPY, algo.*, vector and full-text indexes all PASS |
| TiffinBox fixtures (`data/tiffinbox/build.py`) | ✅ | story + noise + answer key; `build.py` re-checks the key on every run |
| Fixture ingest → `tiffinbox_template` (`ingest/fixtures.py`) | ✅ | UNWIND/MERGE, re-runnable, `--until`; now a `build(name, until)` function the tests reuse |
| Long synthetic research/design docs | ✅ | 8 new docs (`LONG_DOCS` in build.py), one or more for each person: orders API v2 (Arjun), web perf audit (Kavya), ETA model eval + cold-start recs (Rohan), corporate plans + onboarding funnel (Neha), Redis right-sizing (Priya), payments notes (Meera, Sep 30). They record no answer-key decision, so the key is unchanged |
| Text → `Chunk` nodes | ✅ | Doc, AgentSession and Thread text is no longer a node property. It lives only in `Chunk` nodes (≤300 words, `PART_OF` source, `NEXT` in order, full-text index, `MENTIONS` File by basename). `graph.text(g, ref)` rebuilds any doc exactly, which the test checks for every doc. This is the "no second database" proof |
| KNOWS derivation (`graph.derive`) | ✅ | score = Σ weight × 0.5^(age / 1 year); weights: author 1.0, session/ticket 0.8, commit to a file the decision is ABOUT 0.7, review 0.6, chat 0.5, trivial commit 0.05; edge kept if score > 0.3. Formula is written in `graph.py` |
| Radar query (`graph.RADAR`) | ✅ | active decisions + files that exactly one active person knows. Sep 21: exactly the 12 items in the answer key |
| `test_answer_key.py` | ✅ 6/6 | decision knowers (17), file knowers (18), trivia traps, radar, docs rebuild from chunks, full-text search |

**Numbers (full story):** 80 Chunk nodes hold 31.6 K characters of text (18 docs, 17 AI sessions, 38 chat threads), 62 KNOWS edges.

**Found while testing:** on the full story (Sep 30, Arjun and Priya gone) the radar shows Meera as the only knower of D1, retry.py, webhooks.py and api-deploy.yaml, which is the handover working. D6, D7, D9, main.tf, backup and deploy.yml drop off the radar because *no* active person knows them. Day 2 needs an "orphaned" view (known by nobody active) next to the radar. This matches `after_meera.remaining` in the answer key.

**Open decision:** which embedding model to use for the Chunk vector index (Day 2). Options: a local `fastembed` model (no key, ~130 MB download) or an API (needs a key).

## UI pass (pulled forward from Day 3), Oct 15 ✅

| Item | Status | Notes |
|---|---|---|
| `design.md` | ✅ | principles, IA, wireframes for the 6 steps, light/dark tokens. Mobbin + Google Stitch MCP not connected yet: **TODO** refine with their references once connected |
| `frontend/` React + Vite app | ✅ | Landing → Team → Radar → Departure → Why → Handover → Ask, with a "Next" button on each step and a collapsible Cypher block on each screen |
| Light/dark toggle | ✅ | follows the OS by default, saved in localStorage, set before first paint (no flash) |
| Data | ✅ live | `GET /api/workspace` (all six screens, loaded once in `ui.jsx`) and `GET /api/search` (Ask, FalkorDB full-text). The mock `tiffinbox.json` is deleted. Vite proxies `/api` to `:8000` |
| Checked | ✅ | `vite build` clean; screenshots of every step in light and dark, and at 390 px phone width (no sideways scroll) |

Run: `cd frontend && npm install && npm run dev` → http://localhost:5173

Run: `cd backend && uv run uvicorn app:app` (builds `tiffinbox_sep21` and `tiffinbox_template` on first start if missing), then `cd frontend && npm run dev`.

**Next for the UI:** FastAPI serves `frontend/dist` (Day 3 deploy).

## Day 2, Fri Oct 16: thesis + generic ingest

- [x] Dry run on `GRAPH.COPY` → KT agenda (`graph.dry_run`, `AGENDA`, `WEAK_BACKUP`). 3 / 6 / 12, D8 only when both leave, combination risk = items two leavers know. The copy is deleted after every run.
- [x] Orphaned items (`ORPHANED`) + handover counter 12 → 6 (`COVERED`: LEARNED from the KT session, or KNOWS from her own commits).
- [x] Why-trace (`graph.trace`: sources, replaced decisions + incidents, research + external sources, insights, patterns, features) + mentor query (`MENTOR` → Kavya).
- [x] API: `/api/workspace`, `/api/dryrun?leavers=`, `/api/search?q=`. `test_answer_key.py` 9/9.

**FalkorDB 6.0.2 bug found:** an `OPTIONAL MATCH` that follows `WITH ... count()` returns no rows, so `count(o)` is always 0 and every item looks orphaned. `AGENDA` uses one `MATCH` over all knowers instead (`ponytail:` note in `graph.py`). Worth reporting upstream with the 4-line repro.

**Second FalkorDB 6.0.2 bug (Oct 16):** `OPTIONAL MATCH ... RETURN <7+ grouping keys, one always null>, count(d)` panics the server (`reply.rs:655`, `Option::unwrap()` on `None`) and drops every connection, so admin login returned 500. `SOURCES` now counts with `size([(s)-[:RECORDS]->(d) | d])`, which needs no grouping. Also worth reporting upstream.

**Weak backup rule:** the only remaining knower has one KNOWS link and took no part in a source that RECORDS the item (Kavya: one commit to `ci.yml`). This keeps Neha's ADR on D2 as real coverage. For Priya alone it also flags Arjun on `rotate_secrets.sh` and `api-deploy.yaml`, which is the combination risk showing early.

- [ ] Embeddings + vector index on Chunk; extraction scored against the answer key.
- [ ] Upload ingest for md/pdf docs and Claude Code JSONL (reuse `chunk_rows`).
- [ ] LLM-reads-everything baseline vs the graph.

## SaaS layer (Oct 16): companies, admin and member dashboards

| Item | Status | Notes |
|---|---|---|
| Accounts (`backend/accounts.py`) | ✅ | Companies, users and tokens live in the `kt_system` graph. Passwords are scrypt-hashed; a session cookie `kt` keeps you signed in. Offboarded users can't sign in |
| Demo company | ✅ | Seeded on first start: `ws_tiffinbox` = copy of `tiffinbox_template`, admin + 6 employees, Arjun and Priya offboarded with Meera as successor. All demo passwords are `demo123`, printed on the login page |
| Admin dashboard (`#/admin`) | ✅ | Overview (only-one-person items), Employees (add, simulate leaving on a `GRAPH.COPY`, offboard with a successor), Knowledge graph, Handovers (agenda learned / total), Sources (GitHub repo + every upload), Settings (AI provider, GitHub token) |
| Member dashboard (`#/me`) | ✅ | My brain (own graph only), one page per person you succeeded (their agenda, "Mark learned", their decisions with why-traces, their graph), Add sources (upload, CLI token), Ask (search scoped to what you may see) |
| Uploads (`ingest/uploads.py`) | ✅ | .md .txt .pdf → Doc; Claude Code .jsonl → AgentSession. Secrets redacted before storing. New KNOWS rule: running an AI session that edited a file (weight 0.8). Answer key unchanged (62 KNOWS) |
| GitHub (`ingest/github.py`) | ✅ | Public repo → commits with files, PRs, reviews. 25 commits / 10 PRs without a token (fits the 60/h limit), 100 / 40 with one. Unmatched authors become "GitHub contributor" people |
| AI provider (`extract.py`) | ✅ | Any OpenAI-compatible `/chat/completions` (OpenRouter, Groq, Google AI Studio, Ollama, custom). Decisions whose evidence quote isn't in the text are dropped. Runs in the background; status shows per source. `test_extract.py` checks it with a canned reply |
| Daily GitHub sync | ✅ | Sources page: "Sync every day at" (default 19:00, after a 9–6 day), stored as UTC on the Company. A loop in `lifespan` re-reads the repo once a day and re-runs `derive`, so scores keep decaying. Only *when to sync* is a setting; KT Brain never filters work by the hour it happened |
| CLI (`cli/ktbrain.py`) | ✅ | `python cli/ktbrain.py sync --server … --token … --repo .` Stdlib only; slims + redacts on the laptop. Dry run finds this repo's 12 real sessions |

**Not tested live:** a real AI provider call (no key yet) and a real GitHub repo sync (network). Both paths are covered by the code's error handling: failures show on the source or the repo status line.
