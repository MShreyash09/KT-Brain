"""Decision extraction without a real AI provider: a canned model reply goes through the same parsing and linking.

Run from backend/:  uv run python test_extract.py   (needs FalkorDB; builds, then deletes, graph _test_extract)
"""
import json

import extract
from graph import graph
from ingest.uploads import add_doc, extract_into

DOC = "# Cache design\n\nWe decided to cache menu responses in Redis for 5 minutes because the menu API is slow.\n"
REPLY = "Sure! " + json.dumps({"decisions": [
    {"what": "Cache menu responses in Redis for 5 minutes", "why": "The menu API is slow",
     "evidence": "cache menu responses in Redis for 5 minutes", "about": ["api/menu.py", "not/a/real/file.py"]},
    {"what": "Use Postgres for sessions", "why": "made up", "evidence": "we picked Postgres for sessions", "about": []},
]})
extract.chat = lambda *a: REPLY

g = graph("_test_extract")
g.query("CREATE (:Person {id: 'dev', name: 'Dev', active: true}), (:File {path: 'api/menu.py'})")
try:
    found = extract.decisions({"base": "", "key": "", "model": ""}, DOC)
    assert [d["what"] for d in found] == ["Cache menu responses in Redis for 5 minutes"], found  # made-up quote dropped

    ref = add_doc(g, "dev", "cache.md", DOC)
    extract_into(g, {"base": "", "key": "", "model": ""}, ref)
    rows = g.ro_query("""MATCH (s:Source {ref: $ref})-[:RECORDS]->(d:Decision)-[:ABOUT]->(f:File)
        RETURN d.id, f.path, s.extract""", {"ref": ref}).result_set
    assert rows == [["D1", "api/menu.py", "done: 1 decisions"]], rows
    knows = g.ro_query("MATCH (:Person {id: 'dev'})-[:KNOWS]->(d:Decision) RETURN d.id").result_set
    assert knows == [["D1"]], knows  # the uploader now KNOWS the decision their doc records

    extract_into(g, None, ref)  # no provider: marked off, nothing removed
    assert g.ro_query("MATCH (s:Source {ref: $ref}) RETURN s.extract", {"ref": ref}).result_set == [["off"]]
    print("PASS  test_extract")
finally:
    g.delete()
