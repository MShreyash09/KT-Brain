"""KT Brain API. Run from backend/:  uv run uvicorn app:app --reload"""
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from graph import (COVERED, EDGE_COUNTS, MENTOR, NODE_COUNTS, ORPHANED, RADAR, SEARCH, db, dry_run, graph, rows,
                   trace)
from ingest.fixtures import build

# TiffinBox is shown at two moments: the dry-run day (after the resignations, before Meera joins) and the end of the
# story (Arjun and Priya gone, Meera's KT done). Each is its own graph built from the fixtures.
DAY, END = "2026-09-21", "2026-09-30"
DAY_GRAPH, END_GRAPH = "tiffinbox_sep21", "tiffinbox_template"


@asynccontextmanager
async def lifespan(_):
    have = db.list_graphs()
    for name, until in ((DAY_GRAPH, DAY), (END_GRAPH, END)):
        if name not in have:
            build(name, until)
    yield


app = FastAPI(title="KT Brain", lifespan=lifespan)

PEOPLE = "MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.role AS role, p.joined_at AS joined, p.last_day AS last_day ORDER BY p.joined_at"
DECISIONS = """
MATCH (d:Decision) OPTIONAL MATCH (d)-[:ABOUT]->(f:File)
RETURN d.id AS id, d.what AS what, d.why AS why, d.evidence AS evidence, d.status AS status,
       substring(d.at, 0, 10) AS at, collect(f.path) AS about ORDER BY d.ts"""
KNOWS = """
MATCH (p:Person)-[e:KNOWS]->(k)
RETURN p.id AS person, coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, e.score AS score, e.links AS links,
       e.last_touched AS last ORDER BY person, score DESC"""


def day(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def handover(agenda: list) -> dict:
    """How much of the all-leavers agenda is covered, and what is still orphaned, at the end of the story."""
    end = graph(END_GRAPH)
    learner = next(p["id"] for p in rows(end, PEOPLE) if p["joined"] > DAY)
    covered = {}
    for r in rows(end, COVERED, {"learner": learner, "items": agenda}):
        if r["item"] not in covered:  # LEARNED sorts first
            how = f"KT session with {r['taught_by'].split()[0]}" if r["how"] == "LEARNED" else "own commits"
            covered[r["item"]] = {"via": how, "at": day(r["ts"])}
    remaining = [i for (i,) in end.ro_query(ORPHANED).result_set]
    mentor = rows(end, MENTOR, {"learner": learner, "items": remaining})
    return {"learner": learner, "before": len(agenda), "covered": covered, "remaining": remaining,
            "mentor": mentor and {"person": mentor[0]["person"], "reason": f"knows {' and '.join(mentor[0]['knows'])}"}}


@app.get("/api/health")
def health():
    return {"ok": True, "graphs": db.list_graphs()}


@app.get("/api/workspace")
def workspace():
    """Everything the six screens show, read live from the graphs (same shape the UI was built against)."""
    g, end = graph(DAY_GRAPH), graph(END_GRAPH)
    people = rows(end, PEOPLE)
    leavers = [p["id"] for p in people if p["last_day"]]
    cases = [[p] for p in leavers] + ([leavers] if len(leavers) > 1 else [])
    runs = {"+".join(c): dry_run(DAY_GRAPH, c) for c in cases}
    decisions = {d["id"]: d for d in rows(g, DECISIONS)}
    counts = dict(end.ro_query(NODE_COUNTS).result_set)
    counts["edges"] = sum(n for _, n in end.ro_query(EDGE_COUNTS).result_set)
    return {
        "workspace": {"name": "TiffinBox", "synthetic": True, "story": f"2026-04-01 to {END}", "snapshot": DAY,
                      "counts": counts},
        "people": people,
        "decisions": decisions,
        "knows": [{**k, "score": round(k["score"], 2), "last": day(k["last"])} for k in rows(g, KNOWS)],
        "radar": [{"item": r["item"], "kind": r["kind"], "person": r["only_knower"], "score": round(r["score"], 2)}
                  for r in rows(g, RADAR)],
        "dry_runs": runs,
        "traces": {d: trace(g, d) for d, v in decisions.items() if v["status"] == "active"},
        "handover": handover(runs["+".join(leavers)]["agenda"]),
    }


@app.get("/api/dryrun")
def dryrun(leavers: str):
    """Simulate any set of people leaving, e.g. ?leavers=arjun,priya"""
    return dry_run(DAY_GRAPH, leavers.split(","))


@app.get("/api/search")
def search(q: str):
    """Full-text search over Chunk nodes. Any query word may match (RediSearch OR syntax)."""
    words = [w for w in re.findall(r"[a-z0-9_]+", q.lower()) if len(w) > 2]
    if not words:
        return []
    return rows(graph(DAY_GRAPH), SEARCH, {"q": "|".join(words)})
