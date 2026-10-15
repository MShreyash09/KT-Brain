"""Day 1 check: does this FalkorDB build support every feature KT Brain relies on?

Run: uv run python check_db.py   (needs FalkorDB on FALKORDB_URL, default localhost:6379)
"""
import sys

from graph import db, graph

SRC, COPY = "_capcheck", "_capcheck_copy"
NEEDED_PROCS = ["algo.pageRank", "algo.betweenness", "algo.BFS", "algo.SPpaths", "algo.WCC"]
results = {}


def check(name, fn):
    try:
        fn()
        results[name] = "PASS"
    except Exception as e:  # report every failure, don't stop at the first
        results[name] = f"FAIL: {e}"


def cleanup():
    for name in (SRC, COPY):
        if name in db.list_graphs():
            graph(name).delete()


def graph_copy():
    g = graph(SRC)
    g.query("CREATE (:Person {id:'arjun', active:true})-[:KNOWS]->(:Decision {id:'D1'})")
    copy = g.copy(COPY)
    copy.query("MATCH (p:Person {id:'arjun'}) SET p.active = false")
    assert g.ro_query("MATCH (p:Person {id:'arjun'}) RETURN p.active").result_set == [[True]], "source changed"
    assert copy.ro_query("MATCH (p:Person {id:'arjun'}) RETURN p.active").result_set == [[False]]


def procedures():
    names = {r[0] for r in graph(SRC).ro_query("CALL dbms.procedures() YIELD name RETURN name").result_set}
    missing = [p for p in NEEDED_PROCS if p not in names]
    print("  algo procedures available:", sorted(n for n in names if n.startswith("algo.")))
    assert not missing, f"missing {missing}"


def vector_index():
    g = graph(SRC)
    g.query("CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding) OPTIONS {dimension:3, similarityFunction:'cosine'}")
    g.query("CREATE (:Chunk {id:'a', embedding: vecf32([1.0, 0.0, 0.0])}), (:Chunk {id:'b', embedding: vecf32([0.0, 1.0, 0.0])})")
    rows = g.ro_query(
        "CALL db.idx.vector.queryNodes('Chunk', 'embedding', 1, vecf32([0.9, 0.1, 0.0])) YIELD node RETURN node.id"
    ).result_set
    assert rows == [["a"]], rows


def fulltext_index():
    g = graph(SRC)
    g.query("CREATE FULLTEXT INDEX FOR (d:Doc) ON (d.text)")
    g.query("CREATE (:Doc {id:'pay', text:'payment retries set to seven'}), (:Doc {id:'lunch', text:'lunch menu'})")
    rows = g.ro_query("CALL db.idx.fulltext.queryNodes('Doc', 'retries') YIELD node RETURN node.id").result_set
    assert rows == [["pay"]], rows


if __name__ == "__main__":
    print("modules:", db.connection.execute_command("MODULE", "LIST"))
    cleanup()
    check("GRAPH.COPY (copy is independent)", graph_copy)
    check("algo procedures", procedures)
    check("vector index + query", vector_index)
    check("full-text index + query", fulltext_index)
    cleanup()
    for name, r in results.items():
        print(f"{r[:4]}  {name}{r[4:]}")
    sys.exit(any(r != "PASS" for r in results.values()))
