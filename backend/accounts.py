"""Companies, users and tokens, stored in the `kt_system` graph (FalkorDB is the only database).

(:Company {id, name, graph, llm_base, llm_key, llm_model, github_token, repo, repo_status, sync_at, synced_on})
(:User {email, name, role: 'admin'|'member', person, salt, pw, disabled})-[:MEMBER_OF]->(:Company)
(:Token {value: sha256 of the token, kind: 'web'|'cli', created})-[:FOR]->(:User)
"""
import hashlib
import hmac
import os
import re
import secrets
import time

from graph import INDEXES, graph

SYS = graph("kt_system")
WEB_TOKEN_DAYS = 30  # same as the cookie; CLI tokens don't expire


def _digest(token: str) -> str:
    """Only the hash is stored, so reading the database doesn't let anyone sign in as its users."""
    return hashlib.sha256(token.encode()).hexdigest()


def _hash(pw: str, salt: bytes) -> str:
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def _one(query: str, params: dict = None):
    rows = SYS.query(query, params).result_set
    return rows[0] if rows else None


def init():
    for q in ("CREATE INDEX FOR (u:User) ON (u.email)", "CREATE INDEX FOR (t:Token) ON (t.value)",
              "CREATE INDEX FOR (c:Company) ON (c.id)"):
        try:
            SYS.query(q)
        except Exception:  # index already exists
            pass


def company(cid: str) -> dict | None:
    row = _one("MATCH (c:Company {id: $id}) RETURN properties(c)", {"id": cid})
    return row[0] if row else None


def create_company(name: str, cid: str = None, graph_name: str = None) -> dict:
    cid = cid or f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:24]}-{secrets.token_hex(2)}"
    graph_name = graph_name or f"ws_{cid.replace('-', '_')}"
    g = graph(graph_name)
    for q in INDEXES:
        try:
            g.query(q)
        except Exception:  # the demo graph already has them
            pass
    SYS.query("MERGE (c:Company {id: $id}) SET c.name = $name, c.graph = $graph, c.created = $now",
              {"id": cid, "name": name, "graph": graph_name, "now": int(time.time())})
    return company(cid)


def add_user(cid: str, name: str, email: str, pw: str, role: str, person: str | None, disabled=False):
    email = email.strip().lower()
    if _one("MATCH (u:User {email: $e}) RETURN u.email", {"e": email}):
        raise ValueError(f"{email} is already registered")
    salt = os.urandom(16)
    SYS.query("""MATCH (c:Company {id: $cid})
        CREATE (u:User {email: $e, name: $name, role: $role, person: $person, salt: $salt, pw: $pw, disabled: $off})
        CREATE (u)-[:MEMBER_OF]->(c)""",
              {"cid": cid, "e": email, "name": name, "role": role, "person": person, "salt": salt.hex(),
               "pw": _hash(pw, salt), "off": disabled})


def new_token(email: str, kind: str = "web") -> str:
    token = secrets.token_urlsafe(24)
    SYS.query("MATCH (u:User {email: $e}) CREATE (:Token {value: $t, kind: $k, created: $now})-[:FOR]->(u)",
              {"e": email, "t": _digest(token), "k": kind, "now": int(time.time())})
    return token


def login(email: str, pw: str) -> str:
    row = _one("MATCH (u:User {email: $e}) RETURN u.salt, u.pw, u.disabled", {"e": email.strip().lower()})
    if not row or not hmac.compare_digest(_hash(pw, bytes.fromhex(row[0])), row[1]):
        raise PermissionError("Wrong email or password")
    if row[2]:
        raise PermissionError("This account was offboarded. Ask your admin.")
    return new_token(email.strip().lower())


def logout(token: str):
    SYS.query("MATCH (t:Token {value: $t, kind: 'web'}) DELETE t", {"t": _digest(token)})


def user(token: str | None, kind: str = "web") -> dict | None:
    if not token:
        return None
    row = _one("""MATCH (t:Token {value: $t, kind: $k})-[:FOR]->(u:User)-[:MEMBER_OF]->(c:Company)
        WHERE NOT u.disabled AND (t.kind = 'cli' OR t.created > $since)
        RETURN u.email, u.name, u.role, u.person, c.id, c.name, c.graph""",
               {"t": _digest(token), "k": kind, "since": int(time.time()) - WEB_TOKEN_DAYS * 86400})
    if not row:
        return None
    return dict(zip(["email", "name", "role", "person", "company", "company_name", "graph"], row))


def disable_person(cid: str, person: str):
    SYS.query("MATCH (u:User {person: $p})-[:MEMBER_OF]->(:Company {id: $cid}) SET u.disabled = true",
              {"p": person, "cid": cid})


def users(cid: str) -> list:
    rows = SYS.query("""MATCH (u:User)-[:MEMBER_OF]->(:Company {id: $cid})
        RETURN u.email, u.name, u.role, u.person, u.disabled ORDER BY u.role, u.name""", {"cid": cid}).result_set
    return [dict(zip(["email", "name", "role", "person", "disabled"], r)) for r in rows]


S3_FIELDS = ("endpoint", "region", "bucket", "prefix", "key_id", "secret")


def s3(cid: str) -> dict | None:
    """The company's own document bucket (ingest/s3.py), or None when it hasn't connected one."""
    c = company(cid) or {}
    cfg = {f: c.get(f"s3_{f}") or "" for f in S3_FIELDS}
    return cfg if cfg["bucket"] and cfg["key_id"] and cfg["secret"] else None


def update_company(cid: str, **props):
    SYS.query("MATCH (c:Company {id: $id}) SET c += $p", {"id": cid, "p": props})


def due_syncs(now: str, today: str) -> list:
    """Companies whose daily GitHub sync time (UTC "HH:MM") has passed today and that haven't synced yet today."""
    return SYS.query("""MATCH (c:Company) WHERE c.repo <> '' AND c.sync_at <> '' AND c.sync_at <= $now
        AND coalesce(c.synced_on, '') <> $today RETURN c.id, c.graph, c.repo, c.repo_status""",
                     {"now": now, "today": today}).result_set


def companies() -> list:
    return SYS.query("MATCH (c:Company) RETURN c.id, c.graph").result_set


def llm(cid: str) -> dict | None:
    c = company(cid)
    return {"base": c["llm_base"], "key": c["llm_key"], "model": c["llm_model"]} if c and c.get("llm_key") else None
