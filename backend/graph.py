"""Every FalkorDB call in KT Brain goes through this file."""
import os
import time
from uuid import uuid4

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
    # uploaded decisions arrive as 'proposed' until an admin confirms them (or a second person records them)
    "decision": "UNWIND $rows AS r MERGE (d:Decision {id: r.id}) SET d += r.props, d.status = coalesce(r.status, 'active')",
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
RETURN s.ref AS ref, node.seq AS seq, score, collect(f.path) AS files,
       [l IN labels(s) WHERE l <> 'Source'][0] AS kind, s.title AS title, node.text AS text
ORDER BY score DESC LIMIT 6"""


# ── Derive: who KNOWS what ───────────────────────────────────────────────────
# score = sum over evidence links of weight * 0.5 ^ (age / 1 year), age measured from the graph's newest event.
# Weights: authored the commit, PR or doc 1.0; ran the AI session or was the ticket assignee 0.8 (an AI session's
# file edits only 0.25 unless it PRODUCED a commit); committed to a file the decision is ABOUT 0.7; reviewed 0.6;
# posted in the chat thread 0.5; trivial commit 0.05.
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
    # file: ran an AI coding session that edited it. Session file lists are self-reported, so they only count in full
    # when the session PRODUCED a real commit; alone they stay under the threshold (0.25).
    """MATCH (p:Person)-[:RAN]->(s:AgentSession)-[:TOUCHED]->(k:File)
    WITH p, k, CASE WHEN size([(s)-[:PRODUCED]->(c:Commit) | c]) > 0 THEN 0.8 ELSE 0.25 END AS w, s.ts AS ts""",
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
    newest = g.ro_query("MATCH (n) WHERE n.ts IS NOT NULL RETURN max(n.ts)").result_set[0][0]
    now = min(newest, int(time.time()))  # a future-dated source must not age everyone else's knowledge
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


# ── Departure dry run (on a GRAPH.COPY, the workspace graph is never touched) ─
# Agenda items are active decisions and files. An item is on the KT agenda when a leaver KNOWS it and no active
# person does once the leavers are deactivated. It is combination risk when two or more leavers know it: it would not
# be on any single leaver's agenda. A weak backup is an item whose only remaining knower touched it once in code
# (one KNOWS link, and they took no part in a source that RECORDS it), e.g. Kavya and ci.yml.
DEACTIVATE = "MATCH (p:Person) WHERE p.id IN $leavers SET p.active = false"

# ponytail: one MATCH over all knowers, because FalkorDB 6.0.2 returns no rows from an OPTIONAL MATCH that follows a
# WITH ... count() (count(o) is always 0); switch back to OPTIONAL MATCH once that is fixed upstream
AGENDA = """
MATCH (l:Person)-[:KNOWS]->(k) WHERE l.id IN $leavers AND (k:File OR (k:Decision AND k.status = 'active'))
WITH DISTINCT k
MATCH (p:Person)-[:KNOWS]->(k)
WITH k, sum(CASE WHEN p.id IN $leavers THEN 1 ELSE 0 END) AS leavers_knowing,
     sum(CASE WHEN p.active THEN 1 ELSE 0 END) AS backups
WHERE backups = 0
RETURN coalesce(k.id, k.path) AS item, leavers_knowing > 1 AS combination_risk ORDER BY item"""

WEAK_BACKUP = """
MATCH (l:Person)-[:KNOWS]->(k) WHERE l.id IN $leavers AND (k:File OR (k:Decision AND k.status = 'active'))
WITH DISTINCT k
MATCH (o:Person {active: true})-[e:KNOWS]->(k)
WITH k, collect(o) AS backups, max(e.links) AS links WHERE size(backups) = 1 AND links = 1
WITH k, backups[0] AS o
WHERE NOT (o)-[:AUTHORED|REVIEWED|POSTED_IN|ASSIGNED|RAN]->(:Source)-[:RECORDS]->(k)
RETURN coalesce(k.id, k.path) AS item, o.id AS backup ORDER BY item"""


def dry_run(name: str, leavers: list) -> dict:
    copy = graph(f"dryrun_{uuid4().hex[:8]}")
    graph(name).copy(copy.name)
    try:
        copy.query(DEACTIVATE, {"leavers": leavers})
        agenda = copy.ro_query(AGENDA, {"leavers": leavers}).result_set
        weak = copy.ro_query(WEAK_BACKUP, {"leavers": leavers}).result_set
    finally:
        copy.delete()
    return {"agenda": [i for i, _ in agenda], "combination_risk": [i for i, combo in agenda if combo],
            "weak_backup": dict(weak)}


# ── Handover ─────────────────────────────────────────────────────────────────
# After the leavers' last day: items a former member KNOWS that no active person KNOWS or has LEARNED.
ORPHANED = """
MATCH (l:Person {active: false})-[:KNOWS]->(k) WHERE k:File OR (k:Decision AND k.status = 'active')
OPTIONAL MATCH (o:Person {active: true})-[:KNOWS|LEARNED]->(k)
WITH k, count(o) AS backups WHERE backups = 0
RETURN coalesce(k.id, k.path) AS item ORDER BY item"""

# How the learner covered each agenda item: a LEARNED edge (KT session) or a KNOWS edge from their own work.
COVERED = """
MATCH (m:Person {id: $learner})-[e:KNOWS|LEARNED]->(k) WHERE coalesce(k.id, k.path) IN $items
OPTIONAL MATCH (t:Person {id: e.taught_by})
RETURN coalesce(k.id, k.path) AS item, type(e) AS how, t.name AS taught_by, coalesce(e.ts, e.last_touched) AS ts
ORDER BY item, how DESC"""

# Mentor for what is left: the active person (not the learner) with the most KNOWS score in the same services.
MENTOR = """
MATCH (f:File)-[:PART_OF]->(s:Service) WHERE f.path IN $items
WITH collect(DISTINCT s.id) AS services
MATCH (p:Person {active: true})-[e:KNOWS]->(k)-[:ABOUT|PART_OF*1..2]->(s:Service)
WHERE s.id IN services AND p.id <> $learner
WITH p, collect(DISTINCT coalesce(k.id, k.path)) AS knows, sum(e.score) AS score
RETURN p.id AS person, knows ORDER BY score DESC LIMIT 1"""


# ── Why-trace: a decision and every path to its sources ──────────────────────
TRACE_SOURCES = """
MATCH (s:Source)-[:RECORDS]->(:Decision {id: $id})
OPTIONAL MATCH (p:Person)-[:AUTHORED|REVIEWED|POSTED_IN|ASSIGNED|RAN]->(s)
OPTIONAL MATCH (c:Chunk {seq: 0})-[:PART_OF]->(s)
RETURN s.ref AS ref, [l IN labels(s) WHERE l <> 'Source'][0] AS kind, coalesce(s.title, split(c.text, '\n')[0]) AS title,
       substring(s.at, 0, 10) AS at, s.ts AS ts, collect(DISTINCT p.id) AS people
ORDER BY ts"""

TRACE_REPLACED = """
MATCH (:Decision {id: $id})-[:SUPERSEDES]->(o:Decision)
OPTIONAL MATCH (i:Incident)-[:CAUSED_BY]->(o)
RETURN o.id, o.what, i.id, i.title, substring(i.at, 0, 10), i.severity"""

TRACE_RESEARCH = """
MATCH (:Decision {id: $id})-[:INFORMED_BY]->(r:Research)-[:WRITTEN_IN]->(doc:Doc)
OPTIONAL MATCH (r)-[:CITES]->(x:ExternalSource)
RETURN r.id, r.title, doc.id, x.title, x.publisher, x.url, x.date"""

TRACE_INSIGHTS = """
MATCH (r:Research)-[:FOUND]->(i:Insight)-[:JUSTIFIES]->(:Decision {id: $id})
RETURN i.id AS id, i.text AS text, r.title AS research ORDER BY id"""

TRACE_TAGS = """
MATCH (:Decision {id: $id})-[:APPLIES|ABOUT]->(x) WHERE x:Pattern OR x:Feature
RETURN labels(x)[0], x.name"""


def rows(g, query: str, params: dict = None) -> list:
    """Query results as dicts keyed by the RETURN aliases."""
    res = g.ro_query(query, params)
    cols = [c[1] if isinstance(c, (list, tuple)) else c for c in res.header]
    return [dict(zip(cols, r)) for r in res.result_set]


def trace(g, decision: str) -> dict:
    p = {"id": decision}
    replaced, research = {}, {}
    for oid, what, iid, title, at, severity in g.ro_query(TRACE_REPLACED, p).result_set:
        o = replaced.setdefault(oid, {"id": oid, "what": what, "incidents": []})
        if iid:
            o["incidents"].append({"id": iid, "title": title, "at": at, "severity": severity})
    for rid, title, doc, xtitle, publisher, url, date in g.ro_query(TRACE_RESEARCH, p).result_set:
        r = research.setdefault(rid, {"id": rid, "title": title, "doc": doc, "cites": []})
        if url:
            r["cites"].append({"title": xtitle, "publisher": publisher, "url": url, "date": date})
    tags = g.ro_query(TRACE_TAGS, p).result_set
    sources = [{k: sorted(v) if k == "people" else v for k, v in s.items() if k != "ts"}
               for s in rows(g, TRACE_SOURCES, p)]
    return {"sources": sources, "supersedes": list(replaced.values()),
            "research": list(research.values()), "insights": rows(g, TRACE_INSIGHTS, p),
            "patterns": sorted(n for kind, n in tags if kind == "Pattern"),
            "features": sorted(n for kind, n in tags if kind == "Feature")}


# ── Company workspaces (one graph each) ──────────────────────────────────────
PEOPLE = """
MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.role AS role, p.email AS email, p.github AS github,
       p.active AS active, p.joined_at AS joined, p.last_day AS last_day ORDER BY p.joined_at"""

DECISIONS = """
MATCH (d:Decision) OPTIONAL MATCH (d)-[:ABOUT]->(f:File)
RETURN d.id AS id, d.what AS what, d.why AS why, d.evidence AS evidence, d.status AS status,
       substring(d.at, 0, 10) AS at, collect(f.path) AS about ORDER BY d.ts"""

KNOWS = """
MATCH (p:Person)-[e:KNOWS]->(k)
RETURN p.id AS person, coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, e.score AS score, e.links AS links,
       e.last_touched AS last ORDER BY person, score DESC"""

# Decisions recorded in sources these people took part in (their own uploads count even before KNOWS is derived).
RECORDED_BY = """
MATCH (p:Person)-[:AUTHORED|REVIEWED|POSTED_IN|ASSIGNED|RAN]->(:Source)-[:RECORDS]->(d:Decision)
WHERE p.id IN $people RETURN DISTINCT d.id"""

# Uploaded or synced docs and AI sessions, with who added them and the decision-extraction status.
SOURCES = """
MATCH (p:Person)-[:AUTHORED|RAN]->(s:Source) WHERE (s:Doc OR s:AgentSession) AND ($people IS NULL OR p.id IN $people)
OPTIONAL MATCH (s)-[:RECORDS]->(d:Decision)
RETURN s.ref AS ref, [l IN labels(s) WHERE l <> 'Source'][0] AS kind, s.title AS title, substring(s.at, 0, 10) AS at,
       p.id AS person, p.name AS author, s.extract AS extract, s:Doc AND coalesce(s.shared, true) AS shared,
       count(d) AS decisions ORDER BY at DESC"""

SUCCESSORS = "MATCH (a:Person)-[:SUCCEEDED_BY]->(b:Person) RETURN a.id AS leaver, b.id AS successor"

# Everyone whose brain passed to $me, directly or down a chain (A -> B -> me).
PREDECESSORS = "MATCH (a:Person)-[:SUCCEEDED_BY*1..]->(:Person {id: $me}) RETURN DISTINCT a.id"

# Remove an uploaded doc or AI session, its chunks, and the decisions only it recorded.
SOURCE_DECISIONS = "MATCH (:Source {ref: $ref})-[:RECORDS]->(d:Decision) RETURN d.id"
DELETE_SOURCE = [
    "MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) DETACH DELETE c",
    "MATCH (s:Source {ref: $ref}) DETACH DELETE s",
    "MATCH (d:Decision) WHERE d.id IN $ids AND NOT ()-[:RECORDS]->(d) DETACH DELETE d",
]

# What a member may read: docs shared with the company (docs are, unless the author made them private), plus every
# source that they or someone they succeeded took part in. AI sessions and chat are never shared company-wide.
VISIBLE = """((s:Doc AND coalesce(s.shared, true))
    OR any(x IN [(s)<-[:AUTHORED|REVIEWED|POSTED_IN|ASSIGNED|RAN]-(p:Person) | p.id] WHERE x IN $people))"""

READABLE = "MATCH (s:Source {ref: $ref}) WHERE $people IS NULL OR " + VISIBLE + " RETURN s.title"

SHARE = """MATCH (s:Doc {ref: $ref}) WHERE $admin OR $me IN [(p:Person)-[:AUTHORED]->(s) | p.id]
SET s.shared = $shared RETURN s.ref"""

SEARCH_MINE = """
CALL db.idx.fulltext.queryNodes('Chunk', $q) YIELD node, score
MATCH (node)-[:PART_OF]->(s:Source) WHERE """ + VISIBLE + """
WITH DISTINCT node, score, s
OPTIONAL MATCH (node)-[:MENTIONS]->(f:File)
RETURN s.ref AS ref, node.seq AS seq, score, collect(f.path) AS files,
       [l IN labels(s) WHERE l <> 'Source'][0] AS kind, s.title AS title, node.text AS text
ORDER BY score DESC LIMIT 6"""

# A leaver's brain as seen by their successor: everything they KNOW, who else still knows it, and whether the
# successor has picked it up (LEARNED in a KT session or "mark learned", or KNOWS from their own work).
# ponytail: MATCH over all knowers instead of OPTIONAL MATCH, same FalkorDB 6.0.2 bug as AGENDA
INHERITED = """
MATCH (l:Person {id: $leaver})-[e:KNOWS]->(k) WHERE k:File OR (k:Decision AND k.status = 'active')
WITH k, e.score AS score
MATCH (p:Person)-[:KNOWS|LEARNED]->(k)
WITH k, score, collect(DISTINCT CASE WHEN p.active AND p.id <> $successor THEN p.id ELSE null END) AS others,
     sum(CASE WHEN p.id = $successor THEN 1 ELSE 0 END) > 0 AS learned
RETURN coalesce(k.id, k.path) AS item, labels(k)[0] AS kind, score, others, learned ORDER BY score DESC"""

MARK_LEARNED = """
MATCH (m:Person {id: $person}), (k) WHERE (k:Decision AND k.id = $item) OR (k:File AND k.path = $item)
MERGE (m)-[l:LEARNED]->(k) ON CREATE SET l.via = 'self_study', l.at = $at, l.ts = $ts"""

OFFBOARD = """
MATCH (p:Person {id: $person}), (s:Person {id: $successor})
SET p.active = false, p.last_day = $day
MERGE (p)-[:SUCCEEDED_BY]->(s)"""
