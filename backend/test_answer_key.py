"""Day 1 gate: the graph built from the TiffinBox fixtures must agree with data/tiffinbox/answer_key.json.

Run from backend/:  uv run python test_answer_key.py   (needs FalkorDB; builds, then deletes, graph _test_answer_key)
"""
import json
import sys

from graph import COVERED, MENTOR, ORPHANED, RADAR, SEARCH, WHO_KNOWS, db, dry_run, text, trace
from ingest.fixtures import DATA, build

KEY = json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))
NAME = "_test_answer_key"
g = build(NAME, "2026-09-21")  # the dry-run day: after the resignations, before Meera
end = build(NAME + "_end", "2026-09-30")  # end of the story: Arjun and Priya gone, Meera's KT done
known = {item: set(people) for item, people in g.ro_query(WHO_KNOWS).result_set}


def test_decision_knowers():
    for d, want in KEY["decision_knowers"].items():
        assert known.get(d, set()) == set(want), f"{d}: {sorted(known.get(d, []))} != {sorted(want)}"


def test_file_knowers():
    for f, want in KEY["file_knowers"].items():
        assert known.get(f, set()) == set(want), f"{f}: {sorted(known.get(f, []))} != {sorted(want)}"


def test_trivia_traps():
    for f, why in KEY["trivia_traps"].items():
        assert why.split(":")[0] not in known.get(f, set()), why


def test_radar():
    got = sorted(r[0] for r in g.ro_query(RADAR).result_set)
    assert got == sorted(KEY["radar_single_knower"]), got


def test_docs_rebuild_from_chunks():
    ids = [r[0] for r in g.ro_query("MATCH (d:Doc) RETURN d.id").result_set]
    assert len(ids) >= 15, ids
    for did in ids:
        body = (DATA / did).read_text(encoding="utf-8").split("---\n", 2)[2].strip()
        assert text(g, f"doc:{did}") == body, f"{did} does not rebuild from its chunks"


def test_fulltext_search():
    hits = g.ro_query(SEARCH, {"q": "taste quiz"}).result_set
    assert hits and hits[0][0] == "doc:docs/research/recs-cold-start.md", hits


def test_dry_runs():
    for case, want in KEY["dry_runs"].items():
        got = dry_run(NAME, case.split("+"))
        assert sorted(got["agenda"]) == sorted(want["agenda"]), f"{case}: {got['agenda']}"
        assert sorted(got["combination_risk"]) == sorted(want.get("combination_risk", [])), f"{case}: {got}"
        assert not set(got["agenda"]) & set(want["must_not_contain"]), f"{case}: {got['agenda']}"
        for item, who in want.get("weak_backup", {}).items():
            assert got["weak_backup"].get(item) == who, f"{case}: weak backup {item}: {got['weak_backup']}"
    assert NAME in db.list_graphs()  # the copies are gone, the original stays
    assert not [n for n in db.list_graphs() if n.startswith("dryrun_")]


def test_handover():
    remaining = [r[0] for r in end.ro_query(ORPHANED).result_set]
    assert sorted(remaining) == sorted(KEY["after_meera"]["remaining"]), remaining
    agenda = KEY["dry_runs"]["arjun+priya"]["agenda"]
    covered = {r[0] for r in end.ro_query(COVERED, {"learner": "meera", "items": agenda}).result_set}
    assert covered == set(agenda) - set(remaining), covered  # 12 -> 6
    mentor = end.ro_query(MENTOR, {"learner": "meera", "items": remaining}).result_set
    assert mentor[0][0] == KEY["after_meera"]["suggested_mentor"].split()[0], mentor


def test_why_traces():
    d1 = trace(g, "D1")
    refs = {s["ref"] for s in d1["sources"]}
    assert {"pr:124", "ticket:PAY-88"} <= refs and any(r.startswith("thread:spaces/payments/") for r in refs), refs
    assert any(s["kind"] == "AgentSession" and s["title"] == "Retry policy for gateway deploy gaps" for s in d1["sources"])
    assert [o["id"] for o in d1["supersedes"]] == ["D13"] and d1["patterns"], d1
    d6 = trace(g, "D6")
    assert d6["supersedes"][0]["id"] == "D16" and d6["supersedes"][0]["incidents"][0]["id"] == "INC-1", d6
    assert "cloudflare.com" in d6["research"][0]["cites"][0]["url"], d6
    d15 = trace(g, "D15")
    assert [i["id"] for i in d15["insights"]] == ["I1", "I2", "I3"] and d15["features"], d15


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
    g.delete()
    end.delete()
    sys.exit(failed > 0)
