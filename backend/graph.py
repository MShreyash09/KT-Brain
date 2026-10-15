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
    "CREATE INDEX FOR (n:Chunk) ON (n.id)",
    "CREATE FULLTEXT INDEX FOR (n:Chunk) ON (n.text)",
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
    "chunk": """UNWIND $rows AS r MATCH (s:Source {ref: r.ref})
        MERGE (c:Chunk {id: r.ref + '#' + toString(r.seq)}) SET c.seq = r.seq, c.text = r.text
        MERGE (c)-[:PART_OF]->(s)""",
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

# Run once after loading.
LINKS = [
    # A session PRODUCED a commit when the same person committed to a file the session edited
    # within 2 days of the session starting.
    """MATCH (p:Person)-[:RAN]->(s:AgentSession)-[:TOUCHED]->(:File)<-[:CHANGED]-(c:Commit)<-[:AUTHORED]-(p)
    WHERE c.ts >= s.ts AND c.ts <= s.ts + 2 * 86400
    MERGE (s)-[:PRODUCED]->(c)""",
    # Chunks of one source, in order.
    """MATCH (a:Chunk)-[:PART_OF]->(s:Source)<-[:PART_OF]-(b:Chunk) WHERE b.seq = a.seq + 1
    MERGE (a)-[:NEXT]->(b)""",
    # A chunk MENTIONS a file when its text names the file's basename (e.g. "retry.py").
    """MATCH (c:Chunk), (f:File) WHERE c.text CONTAINS split(f.path, '/')[-1]
    MERGE (c)-[:MENTIONS]->(f)""",
]

NODE_COUNTS = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label"
EDGE_COUNTS = "MATCH ()-[e]->() RETURN type(e) AS type, count(e) AS n ORDER BY type"


def load(g, name: str, rows: list):
    if rows:
        g.query(LOAD[name], {"rows": rows})


# ── Text ─────────────────────────────────────────────────────────────────────
# Long text (docs, AI sessions, chat threads) is stored only as Chunk nodes: no second database, no blob store.
CHUNK_WORDS = 300  # about 400 tokens


def chunk_rows(ref: str, text: str) -> list:
    """Rows for LOAD["chunk"]: whole lines packed up to CHUNK_WORDS words (a longer line is its own chunk).
    Joining the chunk texts with newlines in seq order gives back the exact text."""
    chunks, cur, n = [], [], 0
    for line in text.split("\n"):
        words = len(line.split())
        if cur and n + words > CHUNK_WORDS:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += words
    chunks.append("\n".join(cur))
    return [{"ref": ref, "seq": i, "text": t} for i, t in enumerate(chunks)]


def text(g, ref: str) -> str:
    """Rebuild a source's full text from its chunks."""
    rows = g.ro_query("MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) RETURN c.text ORDER BY c.seq",
                      {"ref": ref}).result_set
    return "\n".join(r[0] for r in rows)


SEARCH = """
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(s:Source)
OPTIONAL MATCH (node)-[:MENTIONS]->(f:File)
RETURN s.ref AS source, node.seq AS chunk, score, collect(f.path) AS files
ORDER BY score DESC LIMIT 5"""


# ── Derive: who KNOWS what ───────────────────────────────────────────────────
# score = sum over evidence links of weight * 0.5 ^ (age / 1 year), age measured from the graph's newest event.
# Weights: authored the commit, PR or doc 1.0; ran the AI session or was the ticket assignee 0.8; committed to a
# file the decision is ABOUT 0.7; reviewed 0.6; posted in the chat thread 0.5; trivial commit 0.05.
# A KNOWS edge exists only when score > KNOWS_THRESHOLD. Any single non-trivial link from the last 6 months counts
# (the weakest, a chat post, scores 0.5 * 0.71 = 0.36), a trivial commit never does (at most 0.05), and an old
# single chat post fades out after about 9 months.
TRIVIAL = "(?i)^(fix typo|run formatter|update comment|fix lint|bump ).*"
HALF_LIFE_DAYS = 365
KNOWS_THRESHOLD = 0.3

_KNOWS_LINKS = [
    # file: committed to it
    """MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:CHANGED]->(k:File)
    WITH p, k, CASE WHEN c.message =~ $trivial THEN 0.05 ELSE 1.0 END AS w, c.ts AS ts""",
    # file: reviewed a PR that touched it
    """MATCH (p:Person)-[v:REVIEWED]->(:PR)-[:CONTAINS]->(:Commit)-[:CHANGED]->(k:File)
    WITH DISTINCT p, k, v
    WITH p, k, 0.6 AS w, v.ts AS ts""",
    # decision: took part in a source that RECORDS it
    """MATCH (p:Person)-[r:AUTHORED|REVIEWED|POSTED_IN|ASSIGNED|RAN]->(s:Source)-[:RECORDS]->(k:Decision)
    WITH p, k, CASE type(r) WHEN 'AUTHORED' THEN 1.0 WHEN 'REVIEWED' THEN 0.6 WHEN 'POSTED_IN' THEN 0.5 ELSE 0.8 END AS w,
         coalesce(r.ts, s.ts) AS ts""",
    # decision: non-trivial commit to a file the decision is ABOUT
    """MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:CHANGED]->(:File)<-[:ABOUT]-(k:Decision)
    WHERE NOT c.message =~ $trivial
    WITH DISTINCT p, k, c
    WITH p, k, 0.7 AS w, c.ts AS ts""",
]
_KNOWS_ADD = """
WITH p, k, sum(w * 0.5 ^ (($now - ts) / ($half_life * 86400.0))) AS score, max(ts) AS last, count(*) AS links
MERGE (p)-[e:KNOWS]->(k) ON CREATE SET e.score = 0.0, e.links = 0, e.last_touched = 0
SET e.score = e.score + score, e.links = e.links + links,
    e.last_touched = CASE WHEN last > e.last_touched THEN last ELSE e.last_touched END"""


def derive(g):
    """Recompute every KNOWS edge from the raw edges. Safe to rerun after any ingest."""
    now = g.ro_query("MATCH (n) WHERE n.ts IS NOT NULL RETURN max(n.ts)").result_set[0][0]
    g.query("MATCH ()-[e:KNOWS]->() DELETE e")
    for links in _KNOWS_LINKS:
        g.query(links + _KNOWS_ADD, {"now": now, "half_life": HALF_LIFE_DAYS, "trivial": TRIVIAL})
    g.query("MATCH ()-[e:KNOWS]->() WHERE e.score <= $t DELETE e", {"t": KNOWS_THRESHOLD})


WHO_KNOWS = """
MATCH (p:Person)-[:KNOWS]->(k)
RETURN coalesce(k.id, k.path) AS item, collect(p.id) AS people"""

# Bus-factor radar: active decisions and files that exactly one active person knows.
RADAR = """
MATCH (p:Person {active: true})-[e:KNOWS]->(k)
WHERE k:File OR (k:Decision AND k.status = 'active')
WITH k, collect(p.id) AS knowers, max(e.score) AS score
WHERE size(knowers) = 1
RETURN coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, knowers[0] AS only_knower, score
ORDER BY only_knower, kind, item"""
