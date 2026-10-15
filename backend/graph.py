"""Every FalkorDB call in KT Brain goes through this file."""
import os

from falkordb import FalkorDB

db = FalkorDB.from_url(os.getenv("FALKORDB_URL", "redis://localhost:6379"))


def graph(name: str):
    return db.select_graph(name)


# ── Ingest ───────────────────────────────────────────────────────────────────
# Every statement takes $rows and uses MERGE, so loading twice creates no duplicates.
# Sources (PR, Ticket, Thread, AgentSession, Doc) also get the :Source label and a `ref`
# like "pr:124", which is how extracted decisions point back at where they were recorded.
INDEXES = [
    "CREATE INDEX FOR (n:Person) ON (n.id)",
    "CREATE INDEX FOR (n:Service) ON (n.id)",
    "CREATE INDEX FOR (n:File) ON (n.path)",
    "CREATE INDEX FOR (n:Commit) ON (n.sha)",
    "CREATE INDEX FOR (n:PR) ON (n.id)",
    "CREATE INDEX FOR (n:Ticket) ON (n.id)",
    "CREATE INDEX FOR (n:Thread) ON (n.id)",
    "CREATE INDEX FOR (n:AgentSession) ON (n.id)",
    "CREATE INDEX FOR (n:Doc) ON (n.id)",
    "CREATE INDEX FOR (n:Source) ON (n.ref)",
    "CREATE INDEX FOR (n:Decision) ON (n.id)",
]

LOAD = {
    "person": "UNWIND $rows AS r MERGE (p:Person {id: r.id}) SET p += r.props",
    "service": "UNWIND $rows AS r MERGE (:Service {id: r.id})",
    "depends_on": """UNWIND $rows AS r MATCH (a:Service {id: r.a}), (b:Service {id: r.b})
        MERGE (a)-[:DEPENDS_ON]->(b)""",
    "file": """UNWIND $rows AS r MATCH (s:Service {id: r.service})
        MERGE (f:File {path: r.path}) MERGE (f)-[:PART_OF]->(s)""",
    "commit": """UNWIND $rows AS r MATCH (p:Person {id: r.author})
        MERGE (c:Commit {sha: r.sha}) SET c += r.props
        MERGE (p)-[:AUTHORED]->(c)
        WITH c, r UNWIND r.files AS f
        MATCH (file:File {path: f.path})
        MERGE (c)-[ch:CHANGED]->(file) SET ch.additions = f.additions, ch.deletions = f.deletions""",
    "pr": """UNWIND $rows AS r MATCH (p:Person {id: r.author})
        MERGE (pr:PR {id: r.id}) SET pr += r.props, pr:Source, pr.ref = 'pr:' + toString(r.id)
        MERGE (p)-[:AUTHORED]->(pr)
        WITH pr, r UNWIND r.commits AS sha
        MATCH (c:Commit {sha: sha}) MERGE (pr)-[:CONTAINS]->(c)""",
    "review": """UNWIND $rows AS r MATCH (p:Person {id: r.by}), (pr:PR {id: r.pr})
        MERGE (p)-[v:REVIEWED {id: r.id}]->(pr) SET v += r.props""",
    "ticket": """UNWIND $rows AS r MATCH (p:Person {id: r.assignee})
        MERGE (t:Ticket {id: r.id}) SET t += r.props, t:Source, t.ref = 'ticket:' + r.id
        MERGE (p)-[:ASSIGNED]->(t)
        WITH t, r UNWIND r.prs AS n
        MATCH (pr:PR {id: n}) MERGE (t)-[:FIXED_BY]->(pr)""",
    "thread": """UNWIND $rows AS r
        MERGE (t:Thread {id: r.id}) SET t += r.props, t:Source, t.ref = 'thread:' + r.id""",
    "posted_in": """UNWIND $rows AS r MATCH (p:Person {id: r.person}), (t:Thread {id: r.thread})
        MERGE (p)-[e:POSTED_IN]->(t) SET e += r.props""",
    "session": """UNWIND $rows AS r MATCH (p:Person {id: r.person})
        MERGE (s:AgentSession {id: r.id}) SET s += r.props, s:Source, s.ref = 'session:' + r.id
        MERGE (p)-[:RAN]->(s)
        WITH s, r UNWIND r.files AS path
        MATCH (f:File {path: path}) MERGE (s)-[:TOUCHED]->(f)""",
    "doc": """UNWIND $rows AS r MATCH (p:Person {id: r.author})
        MERGE (d:Doc {id: r.id}) SET d += r.props, d:Source, d.ref = 'doc:' + r.id
        MERGE (p)-[:AUTHORED]->(d)""",
    "decision": "UNWIND $rows AS r MERGE (d:Decision {id: r.id}) SET d += r.props, d.status = 'active'",
    "about": """UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (f:File {path: r.path})
        MERGE (d)-[:ABOUT]->(f)""",
    # an old decision only counts as superseded once its replacement exists (matters for --until)
    "supersedes": """UNWIND $rows AS r MATCH (n:Decision {id: r.new}), (o:Decision {id: r.old})
        MERGE (n)-[:SUPERSEDES]->(o) SET o.status = 'superseded'""",
    "records_decision": """UNWIND $rows AS r MATCH (s:Source {ref: r.ref}), (d:Decision {id: r.target})
        MERGE (s)-[:RECORDS]->(d)""",
    "pattern": """UNWIND $rows AS r MATCH (d:Decision {id: r.decision})
        MERGE (p:Pattern {id: r.id}) SET p.name = r.name MERGE (d)-[:APPLIES]->(p)""",
    "implements": """UNWIND $rows AS r MATCH (p:Pattern {id: r.pattern}), (f:File {path: r.path})
        MERGE (f)-[:IMPLEMENTS]->(p)""",
    "incident": """UNWIND $rows AS r MERGE (i:Incident {id: r.id}) SET i += r.props
        WITH i, r MATCH (d:Decision {id: r.caused_by}) MERGE (i)-[:CAUSED_BY]->(d)""",
    "records_incident": """UNWIND $rows AS r MATCH (s:Source {ref: r.ref}), (i:Incident {id: r.target})
        MERGE (s)-[:RECORDS]->(i)""",
    "research": """UNWIND $rows AS r MATCH (doc:Doc {id: r.doc})
        MERGE (x:Research {id: r.id}) SET x.title = r.title MERGE (x)-[:WRITTEN_IN]->(doc)""",
    "cites": """UNWIND $rows AS r MATCH (x:Research {id: r.research})
        MERGE (s:ExternalSource {id: r.id}) SET s += r.props MERGE (x)-[:CITES]->(s)""",
    "found": """UNWIND $rows AS r MATCH (x:Research {id: r.research})
        MERGE (i:Insight {id: r.id}) SET i.text = r.text MERGE (x)-[:FOUND]->(i)""",
    "informed_by": """UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (x:Research {id: r.research})
        MERGE (d)-[:INFORMED_BY]->(x)""",
    "justifies": """UNWIND $rows AS r MATCH (i:Insight {id: r.insight}), (d:Decision {id: r.decision})
        MERGE (i)-[:JUSTIFIES]->(d)""",
    "feature": """UNWIND $rows AS r MATCH (pr:PR {id: r.pr})
        MERGE (f:Feature {id: r.id}) SET f.name = r.name MERGE (pr)-[:IMPLEMENTS]->(f)""",
    "decision_feature": """UNWIND $rows AS r MATCH (d:Decision {id: r.decision}), (f:Feature {id: r.feature})
        MERGE (d)-[:ABOUT]->(f)""",
    "learned": """UNWIND $rows AS r MATCH (p:Person {id: r.person}), (k)
        WHERE (k:Decision AND k.id = r.item) OR (k:File AND k.path = r.item)
        MERGE (p)-[l:LEARNED]->(k) SET l += r.props""",
}

# A session PRODUCED a commit when the same person committed to a file the session edited
# within 2 days of the session starting.
LINK_SESSIONS = """
MATCH (p:Person)-[:RAN]->(s:AgentSession)-[:TOUCHED]->(:File)<-[:CHANGED]-(c:Commit)<-[:AUTHORED]-(p)
WHERE c.ts >= s.ts AND c.ts <= s.ts + 2 * 86400
MERGE (s)-[:PRODUCED]->(c)"""

NODE_COUNTS = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label"
EDGE_COUNTS = "MATCH ()-[e]->() RETURN type(e) AS type, count(e) AS n ORDER BY type"


def load(g, name: str, rows: list):
    if rows:
        g.query(LOAD[name], {"rows": rows})
