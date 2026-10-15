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
| Data | ⚠ mock | `frontend/src/data/tiffinbox.json` is exported from the real graph. The export asserts radar, all 3 dry runs and the 12 → 6 handover against the answer key. Ask searches the exported chunks in the browser. Replace with `/api/*` calls next |
| Checked | ✅ | `vite build` clean; screenshots of every step in light and dark, and at 390 px phone width (no sideways scroll) |

Run: `cd frontend && npm install && npm run dev` → http://localhost:5173

**Next for the UI:** FastAPI endpoints with the same JSON shapes (`/api/team`, `/api/radar`, `/api/dryrun?leavers=`, `/api/why/{id}`, `/api/handover`, `/api/search?q=`). Then the dry run runs live on a `GRAPH.COPY`, Ask uses the FalkorDB full-text index, and FastAPI serves `frontend/dist`.

## Day 2, Fri Oct 16: thesis + generic ingest (next)

- [ ] Dry run on `GRAPH.COPY` → KT agenda. Tests: `dry_runs` in the answer key (D8 only when both leave, no D2, no D13).
- [ ] Orphaned items (known by no active person) + handover counter 12 → 6 using LEARNED.
- [ ] Why-trace (D1, D6, D15 paths in the answer key) + mentor query (Kavya).
- [ ] Embeddings + vector index on Chunk; extraction scored against the answer key.
- [ ] Upload ingest for md/pdf docs and Claude Code JSONL (reuse `chunk_rows`).
- [ ] LLM-reads-everything baseline vs the graph.
