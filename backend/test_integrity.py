"""Uploads and syncs must not be able to poison the graph. Calls the endpoint functions directly, no HTTP.

Run from backend/:  uv run python test_integrity.py   (needs FalkorDB; builds, then deletes, graph _test_integrity)
"""
import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException

import app
import extract
from graph import graph
from ingest import github
from ingest.uploads import add_doc, add_sessions, extract_into

NAME = "_test_integrity"
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
DAY = 86400
now = int(time.time())
g = graph(NAME)
u = lambda person, role="member": {"graph": NAME, "person": person, "role": role, "company": "_none"}


def session(sid, files, text, at):
    return {"id": sid, "files": files, "text": text, "started": at, "ended": at, "title": "t", "branch": "main"}


def chunks(ref):
    return [r[0] for r in g.ro_query("MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) RETURN c.text", {"ref": ref}).result_set]


def knows(person, item):
    return g.ro_query("MATCH (:Person {id: $p})-[e:KNOWS]->(k) WHERE coalesce(k.id, k.path) = $i RETURN e.score",
                      {"p": person, "i": item}).result_set


def raises(status, fn, *args):
    try:
        fn(*args)
    except HTTPException as e:
        assert e.status_code == status, e
        return
    raise AssertionError(f"expected HTTP {status}")


def test_future_session_does_not_age_others():
    add_sessions(g, "eve", [session("s-future", ["x/other.py"], "eve: hi", "2036-01-01T00:00:00Z")])
    assert g.ro_query("MATCH (s:AgentSession) RETURN max(s.ts)").result_set[0][0] <= int(time.time())
    assert knows("ann", "pay/retry.py")[0][0] > 0.9  # ann's commit from yesterday still counts in full


def test_session_id_is_per_uploader():
    add_sessions(g, "ann", [session("same-id", [], "ann: original", iso(now - DAY))])
    add_sessions(g, "eve", [session("same-id", [], "eve: overwritten", iso(now))])
    assert chunks("session:ann:same-id") == ["ann: original"], chunks("session:ann:same-id")


def test_session_only_file_is_not_knowledge():
    add_sessions(g, "eve", [session("s-fake", ["pay/retry.py"], "eve: edited", iso(now))])
    assert not knows("eve", "pay/retry.py")  # claimed edit, no commit behind it


def test_mark_learned_only_on_inherited_items():
    raises(403, app.learned, app.Learned(item="pay/retry.py"), u("eve"))
    app.learned(app.Learned(item="pay/retry.py"), u("bob"))  # bob succeeded ann, who knows retry.py
    assert g.ro_query("MATCH (:Person {id: 'bob'})-[:LEARNED]->(:File {path: 'pay/retry.py'}) RETURN 1").result_set


def test_successor_chain():
    assert set(app.own_ids(u("cy"))) == {"cy", "bob", "ann"}, app.own_ids(u("cy"))


def test_offboard_needs_real_active_people():
    raises(400, app.offboard, app.Offboard(person="eve", successor="nobody"), u("x", "admin"))
    raises(400, app.offboard, app.Offboard(person="eve", successor="ann"), u("x", "admin"))  # ann already left
    assert g.ro_query("MATCH (p:Person {id: 'eve'}) RETURN p.active").result_set == [[True]]


def test_uploaded_decisions_are_proposed_until_corroborated():
    doc = "# Plan\n\nWe decided to retry payments three times with backoff.\n"
    extract.chat = lambda *a: json.dumps({"decisions": [{"what": "Retry payments three times", "why": "flaky gateway",
                                                         "evidence": "retry payments three times with backoff"}]})
    llm = {"base": "", "key": "", "model": ""}
    ref = add_doc(g, "eve", "plan.md", doc)
    extract_into(g, llm, ref)
    status = lambda: g.ro_query("MATCH (d:Decision {what: 'Retry payments three times'}) RETURN d.status").result_set
    assert status() == [["proposed"]], status()
    extract_into(g, llm, add_doc(g, "cy", "plan.md", doc))
    assert status() == [["active"]], status()  # a second person recorded it


def test_remove_source():
    extract.chat = lambda *a: json.dumps({"decisions": [{"what": "Made up", "why": "", "evidence": "never happened"}]})
    ref = add_doc(g, "eve", "fake.md", "# Fake\n\nThis never happened.\n")
    extract_into(g, {"base": "", "key": "", "model": ""}, ref)
    app.remove_source(ref, u("x", "admin"))
    assert not chunks(ref)
    assert not g.ro_query("MATCH (d:Decision {what: 'Made up'}) RETURN d").result_set


def test_github_login_does_not_overwrite_employee():
    fake = {"/repos/o/r/commits?per_page=25": [{"sha": "gh1", "url": "c/gh1", "author": {"login": "eve"},
                                                "commit": {"message": "x", "author": {"name": "eve", "date": iso(now)}}}],
            "c/gh1": {"files": [{"filename": "pay/retry.py", "additions": 1, "deletions": 0}]},
            "/repos/o/r/pulls?state=all&per_page=10": []}
    github.get = lambda path, token: fake[path]
    github.ingest(g, "o/r", None, lambda msg: None)
    assert g.ro_query("MATCH (p:Person {id: 'eve'}) RETURN p.name, p.github").result_set == [["Eve", None]]
    assert g.ro_query("MATCH (p:Person {github: 'eve'}) RETURN p.id").result_set == [["eve-2"]]


if __name__ == "__main__":
    failed = 0
    try:
        # ann left (succeeded by bob, who left too, succeeded by cy) and committed retry.py yesterday; eve has no github
        g.query("""CREATE (ann:Person {id: 'ann', name: 'Ann', active: false}), (bob:Person {id: 'bob', name: 'Bob', active: false}),
            (cy:Person {id: 'cy', name: 'Cy', active: true}), (:Person {id: 'eve', name: 'Eve', active: true}),
            (ann)-[:SUCCEEDED_BY]->(bob), (bob)-[:SUCCEEDED_BY]->(cy),
            (f:File {path: 'pay/retry.py'}), (ann)-[:AUTHORED]->(:Commit {sha: 'c1', message: 'retry', ts: $t})-[:CHANGED]->(f)""",
                {"t": now - DAY})
        app.derive(g)
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print(f"PASS  {name}")
                except AssertionError as e:
                    failed += 1
                    print(f"FAIL  {name}: {e}")
    finally:
        g.delete()
    raise SystemExit(failed > 0)
