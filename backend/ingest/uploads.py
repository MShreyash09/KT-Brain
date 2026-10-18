"""Uploaded docs and AI coding sessions -> a company graph, for one person.

Docs (.md .txt .pdf) become a Doc source, Claude Code logs (.jsonl) an AgentSession. Text is stored only as Chunk
nodes. Secrets are redacted before anything is stored. Decisions are extracted afterwards if the company has an AI
provider set (extract.py), and every new decision points back to the source that RECORDS it.
"""
import io
import json
import re
import time
from datetime import datetime, timezone

import extract
from graph import LINKS, chunk_rows, derive, load

SECRETS = [
    r"sk-[A-Za-z0-9_\-]{16,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{30,}",
    r"github_pat_[A-Za-z0-9_]{20,}",  # fine-grained GitHub token
    r"gsk_[A-Za-z0-9]{20,}", r"xox[abpr]-[A-Za-z0-9\-]{10,}", r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}",  # Stripe
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",  # JWT
    r"(?i)(?<=bearer )[A-Za-z0-9._~+/\-]{16,}=*", r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)",  # Bearer header, user:pass@ in URLs
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
]
ASSIGNED_SECRET = r"(?i)((?:password|passwd|secret|token|api_key|apikey)[\"']?\s*[:=]\s*[\"']?)[^\s\"']{6,}"


def redact(text: str) -> str:
    for pattern in SECRETS:
        text = re.sub(pattern, "[redacted]", text)
    return re.sub(ASSIGNED_SECRET, r"\1[redacted]", text)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts(iso: str) -> int:
    """Epoch seconds, never in the future (an uploaded log can claim any date)."""
    return min(int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()), int(time.time()))


def parse_claude_session(lines: list) -> dict | None:
    """One Claude Code .jsonl log, slimmed: prompts, assistant text and the files its Edit/Write calls touched."""
    turns = [l for l in lines if l.get("type") in ("user", "assistant") and isinstance(l.get("message"), dict)]
    if not turns:
        return None
    cwd = (turns[0].get("cwd") or "").replace("\\", "/")
    text, files = [], set()
    for l in turns:
        content = l["message"]["content"]
        if isinstance(content, str):
            text.append(f"user: {content}")
            continue
        for c in content:
            if c.get("type") == "text":
                text.append(f"{l['type']}: {c['text']}")
            elif c.get("type") == "tool_use" and c.get("name") in ("Edit", "Write", "MultiEdit"):
                path = c["input"].get("file_path", "").replace("\\", "/")
                if cwd and path.startswith(cwd + "/"):
                    files.add(path.removeprefix(cwd + "/"))
    return {"id": turns[0]["sessionId"], "title": next((l["aiTitle"] for l in lines if l.get("type") == "ai-title"), ""),
            "branch": turns[0].get("gitBranch"), "cwd": cwd, "started": turns[0]["timestamp"],
            "ended": turns[-1]["timestamp"], "files": sorted(files), "text": "\n".join(text)}


def pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)


def _finish(g):
    for q in LINKS:
        g.query(q)
    derive(g)


def _reset_chunks(g, ref: str):
    g.query("MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) DETACH DELETE c", {"ref": ref})


def add_doc(g, person: str, name: str, text: str) -> str:
    did, at = f"uploads/{person}/{name}", now_iso()
    text = redact(text).strip()
    title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.strip()), name)[:120]
    _reset_chunks(g, f"doc:{did}")
    load(g, "doc", [{"id": did, "author": person, "props": {"title": title, "kind": "upload", "at": at, "ts": ts(at),
                                                           "extract": "pending"}}])
    load(g, "chunk", chunk_rows(f"doc:{did}", text))
    _finish(g)
    return f"doc:{did}"


def add_sessions(g, person: str, sessions: list) -> list:
    refs = []
    for s in sessions:
        sid = f"{person}:{s['id']}"  # per uploader, so nobody can overwrite another person's session by reusing its id
        g.query("UNWIND $paths AS p MERGE (:File {path: p})", {"paths": s["files"]})
        tool = re.sub(r"[^a-z0-9-]", "", str(s.get("tool") or "claude-code").lower())[:30] or "ai-agent"
        load(g, "session", [{"id": sid, "person": person, "files": s["files"], "props": {
            "tool": tool, "branch": s.get("branch"), "title": s.get("title") or "AI coding session",
            "at": s["started"], "ts": ts(s["started"]), "ended_at": s.get("ended"), "extract": "pending"}}])
        ref = f"session:{sid}"
        _reset_chunks(g, ref)
        load(g, "chunk", chunk_rows(ref, redact(s["text"])))
        refs.append(ref)
    _finish(g)
    return refs


# Any other agent's log: the generic reader cli/ktbrain.py uses (records with a role-like key and a text field, plus
# ISO timestamps). A web upload has no repo to anchor paths to, so it stores the text without file links.
ROLE_KEYS = ("role", "type", "source", "author", "speaker", "sender")
TEXT_KEYS = ("content", "text", "message", "prompt", "response", "output")
ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?")


def _walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)
    elif isinstance(x, str):
        yield x


def parse_any_log(name: str, records: list) -> dict | None:
    text, times = [], []
    for x in _walk(records):
        if isinstance(x, dict):
            role = next((x[k] for k in ROLE_KEYS if isinstance(x.get(k), str)), None)
            body = next((x[k] for k in TEXT_KEYS if isinstance(x.get(k), str) and x[k].strip()), None)
            if role and body:
                text.append(f"{role.lower()}: {body.strip()}")
        elif ISO.fullmatch(x):
            times.append(x)
    if not text:
        return None
    first = next((t.split(": ", 1)[1] for t in text if "user" in t.split(": ", 1)[0]), text[0].split(": ", 1)[-1])
    when = now_iso()
    return {"id": f"upload:{re.sub(r'[^A-Za-z0-9._-]', '-', name)[:80]}", "tool": "ai-agent", "branch": None,
            "title": re.sub(r"<[^>]+>", "", first).strip().split("\n")[0][:100], "files": [],
            "started": min(times, default=when), "ended": max(times, default=when), "text": "\n".join(text)}


def parse_upload(name: str, raw: bytes) -> tuple[str, object]:
    """('sessions', [...]) for an AI coding agent's log (Claude Code's own format, else the generic reader),
    ('doc', text) for anything else we can read."""
    low = name.lower()
    if low.endswith((".jsonl", ".json")):
        body = raw.decode("utf-8", errors="replace")
        try:
            records = [json.loads(body)]
        except json.JSONDecodeError:
            records = [json.loads(l) for l in body.splitlines() if l.strip() and l.lstrip().startswith(("{", "["))]
        lines = [r for r in records if isinstance(r, dict)]
        by_id = {}
        for l in lines:
            by_id.setdefault(l.get("sessionId"), []).append(l)
        sessions = [s for s in (parse_claude_session(ls) for ls in by_id.values()) if s]
        if not sessions:
            sessions = [s for s in [parse_any_log(name, records)] if s]
        if not sessions:
            raise ValueError("No conversation found in this log (expected records with a role and a text field)")
        return "sessions", sessions
    if low.endswith(".pdf"):
        return "doc", pdf_text(raw)
    if low.endswith((".md", ".txt", ".markdown", ".rst")):
        return "doc", raw.decode("utf-8", errors="replace")
    raise ValueError("Upload .md, .txt, .pdf, or an AI coding agent's .jsonl / .json log")


# A proposed decision becomes active once sources from two different people record it.
CORROBORATE = """
MATCH (p:Person)-[:AUTHORED|RAN]->(:Source)-[:RECORDS]->(d:Decision {status: 'proposed'})
WITH d, count(DISTINCT p) AS people WHERE people > 1
SET d.status = 'active'"""


WAITING = "waiting: AI rate limit, retrying"
STATE = "MATCH (s:Source {ref: $ref}) RETURN s.extract"
# older builds stored a rate limit as 'failed: 429 …'; those are retried too
WAITING_SOURCES = """MATCH (s:Source) WHERE s.extract = $w OR s.extract STARTS WITH 'failed: 429'
RETURN s.ref, coalesce(s.trusted, false) ORDER BY s.at LIMIT $n"""


def extract_all(g, llm: dict | None, refs: list, trusted: bool = False):
    """extract_into for one upload's sources in turn. After the first rate limit the rest are marked waiting without
    calling the provider, so a 30-session CLI sync is one 429, not 30."""
    limited = False
    for ref in refs:
        if limited:
            g.query("MATCH (s:Source {ref: $ref}) SET s.extract = $m, s.trusted = $t", {"ref": ref, "m": WAITING, "t": trusted})
            continue
        extract_into(g, llm, ref, trusted)
        limited = g.ro_query(STATE, {"ref": ref}).result_set[0][0] == WAITING


def retry_waiting(g, llm: dict | None, n: int = 2) -> int:
    """Run up to `n` extractions a rate limit held back (called every minute); stop at the next rate limit."""
    if not llm:
        return 0
    done = 0
    for ref, trusted in g.ro_query(WAITING_SOURCES, {"w": WAITING, "n": n}).result_set:
        extract_into(g, llm, ref, trusted)
        if g.ro_query(STATE, {"ref": ref}).result_set[0][0] == WAITING:
            break
        done += 1
    return done


def extract_into(g, llm: dict | None, ref: str, trusted: bool = False):
    """Background step: ask the company's AI provider for decisions in one source and link them.
    New decisions are 'proposed' (kept out of the radar and handovers) unless the uploader is `trusted` (an admin)."""
    if not llm:
        g.query("MATCH (s:Source {ref: $ref}) SET s.extract = 'off'", {"ref": ref})
        return
    text = "\n".join(r[0] for r in g.ro_query(
        "MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) RETURN c.text ORDER BY c.seq", {"ref": ref}).result_set)
    try:
        found = extract.decisions(llm, text)
    except Exception as e:  # provider down, bad key, bad JSON: say so on the source instead of failing the upload
        # a rate limit is only a delay: retry_waiting picks the source up again from the minute loop
        m = WAITING if str(e)[:3] == "429" else f"failed: {e}"[:300]
        g.query("MATCH (s:Source {ref: $ref}) SET s.extract = $m, s.trusted = $t", {"ref": ref, "m": m, "t": trusted})
        return
    existing = {what: did for did, what in g.ro_query("MATCH (d:Decision) RETURN d.id, d.what").result_set}
    n = max([int(i[1:]) for i in existing.values() if re.fullmatch(r"D\d+", i)] or [0])
    files = {r[0] for r in g.ro_query("MATCH (f:File) RETURN f.path").result_set}
    at = g.ro_query("MATCH (s:Source {ref: $ref}) RETURN s.at", {"ref": ref}).result_set[0][0]
    for d in found:
        did = existing.get(d["what"])
        if not did:
            n += 1
            did = existing[d["what"]] = f"D{n}"
            load(g, "decision", [{"id": did, "status": "active" if trusted else "proposed", "props": {
                "what": d["what"], "why": d.get("why", ""), "evidence": d["evidence"], "at": at, "ts": ts(at)}}])
        load(g, "records_decision", [{"ref": ref, "target": did}])
        load(g, "about", [{"decision": did, "path": p} for p in d.get("about") or [] if p in files])
    g.query(CORROBORATE)
    g.query("MATCH (s:Source {ref: $ref}) SET s.extract = $m", {"ref": ref, "m": f"done: {len(found)} decisions"})
    derive(g)
