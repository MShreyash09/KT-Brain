"""Day 1 gate: the graph built from the TiffinBox fixtures must agree with data/tiffinbox/answer_key.json.

Run from backend/:  uv run python test_answer_key.py   (needs FalkorDB; builds, then deletes, graph _test_answer_key)
"""
import json
import sys

from graph import RADAR, SEARCH, WHO_KNOWS, text
from ingest.fixtures import DATA, build

KEY = json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))
NAME = "_test_answer_key"
g = build(NAME, "2026-09-21")  # the dry-run day: after the resignations, before Meera
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
    sys.exit(failed > 0)
