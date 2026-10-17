"""KT Brain API. Run from backend/:  uv run uvicorn app:app --reload

Public:  the TiffinBox story (/api/workspace, /api/dryrun, /api/search, /api/ask) and sign-in.
Admin:   /api/admin/*   every employee's graph, offboarding with a successor, sources, AI provider settings.
Member:  /api/brain/*   your own graph, uploads, CLI token, and the brain of anyone you succeeded.
CLI:     /api/cli/*     `ktbrain sync` pushes AI sessions with a per-user token.
"""
import asyncio
import base64
import collections
import functools
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

import accounts
import agent
import extract
from agent import search_words
from graph import (COVERED, DECISIONS, DELETE_SOURCE, EDGE_COUNTS, INHERITED, KNOWS, MARK_LEARNED, MENTOR, NODE_COUNTS,
                   OFFBOARD, ORPHANED, PEOPLE, PREDECESSORS, READABLE, RECORDED_BY, SEARCH, SEARCH_MINE, SHARE,
                   SOURCE_DECISIONS, SOURCES, SUCCESSORS, db, derive, dry_run, graph, radar, rows, text, trace)
from ingest import github, uploads
from ingest.fixtures import build

# The public story shows TiffinBox at two moments: the dry-run day (after the resignations, before Meera joins) and
# the end of the story (Arjun and Priya gone, Meera's KT done). The demo company starts from the end of the story.
DAY, END = "2026-09-21", "2026-09-30"
DAY_GRAPH, END_GRAPH = "tiffinbox_sep21", "tiffinbox_template"
DEMO = {"company": "tiffinbox", "graph": "ws_tiffinbox", "password": "demo123", "admin": "admin@tiffinbox.example"}


def seed_demo():
    """TiffinBox as a company you can sign in to: an admin, its employees, and Meera as Arjun's and Priya's successor."""
    if accounts.company(DEMO["company"]):
        return
    if DEMO["graph"] not in db.list_graphs():
        graph(END_GRAPH).copy(DEMO["graph"])
    g = graph(DEMO["graph"])
    g.query("MATCH (l:Person), (m:Person {id: 'meera'}) WHERE l.id IN ['arjun', 'priya'] MERGE (l)-[:SUCCEEDED_BY]->(m)")
    accounts.create_company("TiffinBox (demo)", DEMO["company"], DEMO["graph"])
    accounts.add_user(DEMO["company"], "TiffinBox admin", DEMO["admin"], DEMO["password"], "admin", None)
    for p in rows(g, PEOPLE):
        accounts.add_user(DEMO["company"], p["name"], p["email"], DEMO["password"], "member", p["id"],
                          disabled=not p["active"])


@asynccontextmanager
async def lifespan(_):
    have = db.list_graphs()
    for name, until in ((DAY_GRAPH, DAY), (END_GRAPH, END)):
        if name not in have:
            build(name, until)
    accounts.init()
    seed_demo()
    task = asyncio.create_task(auto_sync())
    yield
    task.cancel()


app = FastAPI(title="KT Brain", lifespan=lifespan)


def day(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "person"


def radar_view(g) -> list:
    return [{"item": r["item"], "kind": r["kind"], "person": r["only_knower"], "score": round(r["score"], 2),
             "blast": r["blast"]} for r in radar(g)]


def company_llm(cid: str, background: bool = False) -> dict | None:
    """The company's own AI provider, else the server's (LLM_KEY in the environment). The radar watch writes briefs in
    the background for every company, so on the server's key it runs for the demo company only, which leaves the
    shared quota for what people ask and upload."""
    return accounts.llm(cid) or (extract.env_llm() if not background or cid == DEMO["company"] else None)


# ── Public: the TiffinBox story ──────────────────────────────────────────────
def handover(agenda: list) -> dict:
    """How much of the all-leavers agenda is covered, and what is still orphaned, at the end of the story."""
    end = graph(END_GRAPH)
    learner = next(p["id"] for p in rows(end, PEOPLE) if p["joined"] > DAY)
    covered = {}
    for r in rows(end, COVERED, {"learner": learner, "items": agenda}):
        if r["item"] not in covered:  # LEARNED sorts first
            how = f"KT session with {r['taught_by'].split()[0]}" if r["how"] == "LEARNED" else "own commits"
            covered[r["item"]] = {"via": how, "at": day(r["ts"])}
    remaining = [i for (i,) in end.ro_query(ORPHANED).result_set]
    mentor = rows(end, MENTOR, {"learner": learner, "items": remaining})
    return {"learner": learner, "before": len(agenda), "covered": covered, "remaining": remaining,
            "mentor": mentor and {"person": mentor[0]["person"], "reason": f"knows {' and '.join(mentor[0]['knows'])}"}}


@app.get("/api/health")
def health():
    return {"ok": True}  # not the graph list: it names every company


# ponytail: the story graphs never change while the server runs, so the public story is computed once (each dry run
# is a GRAPH.COPY, too costly to repeat for anyone who calls a public URL); restart after rebuilding the fixtures
@app.get("/api/workspace")
@functools.cache
def workspace():
    """Everything the six story screens show, read live from the graphs."""
    g, end = graph(DAY_GRAPH), graph(END_GRAPH)
    people = [{k: v for k, v in p.items() if k != "active"} for p in rows(end, PEOPLE)]  # the story is set on Sep 21
    leavers = [p["id"] for p in people if p["last_day"]]
    cases = [[p] for p in leavers] + ([leavers] if len(leavers) > 1 else [])
    runs = {"+".join(c): story_dry_run(tuple(sorted(c))) for c in cases}
    decisions = {d["id"]: d for d in rows(g, DECISIONS)}
    counts = dict(end.ro_query(NODE_COUNTS).result_set)
    counts["edges"] = sum(n for _, n in end.ro_query(EDGE_COUNTS).result_set)
    return {
        "workspace": {"name": "TiffinBox", "synthetic": True, "story": f"2026-04-01 to {END}", "snapshot": DAY,
                      "counts": counts},
        "people": people,
        "decisions": decisions,
        "knows": [{**k, "score": round(k["score"], 2), "last": day(k["last"])} for k in rows(g, KNOWS)],
        "radar": radar_view(g),
        "dry_runs": runs,
        "traces": {d: trace(g, d) for d, v in decisions.items() if v["status"] == "active"},
        "handover": handover(runs["+".join(leavers)]["agenda"]),
    }


@app.get("/api/dryrun")
def dryrun(leavers: str):
    """Simulate any set of TiffinBox people leaving, e.g. ?leavers=arjun,priya"""
    people = {p["id"] for p in rows(graph(DAY_GRAPH), PEOPLE)}
    return story_dry_run(tuple(sorted(set(leavers.split(",")) & people)))  # unknown ids would only bust the cache


@functools.cache
def story_dry_run(leavers: tuple) -> dict:
    return dry_run(DAY_GRAPH, list(leavers))


@app.get("/api/search")
def search(q: str):
    words = search_words(q)
    return rows(graph(DAY_GRAPH), SEARCH, {"q": words}) if words else []


# Public answers run on the server's own AI key, so they are cached (the story graph never changes) and capped.
# ponytail: one in-process cap shared by every visitor; a per-IP limit if one visitor can use it all up
PUBLIC_ASKS_PER_MINUTE = 10
_answers, _asked = {}, collections.deque()


@app.get("/api/ask")
def public_ask(q: str):
    """The agent on the TiffinBox story: an answer that cites the graph, or the evidence alone without an AI key."""
    key = " ".join(q.lower().split())[:300]
    if key in _answers:
        return _answers[key]
    now = time.time()
    while _asked and _asked[0] < now - 60:
        _asked.popleft()
    llm = extract.env_llm()
    if llm and len(_asked) >= PUBLIC_ASKS_PER_MINUTE:
        llm = None  # busy: the evidence alone, not cached
    elif llm:
        _asked.append(now)
    out = agent.ask(graph(DAY_GRAPH), q, llm)
    if out["answer"]:
        _answers[key] = out
    return out


# ── Accounts ─────────────────────────────────────────────────────────────────
class Register(BaseModel):
    company: str
    name: str
    email: str
    password: str


class Login(BaseModel):
    email: str
    password: str


def signed_in(request: Request) -> dict:
    u = accounts.user(request.cookies.get("kt"))
    if not u:
        raise HTTPException(401, "Sign in first")
    return u


def admin(u: dict = Depends(signed_in)) -> dict:
    if u["role"] != "admin":
        raise HTTPException(403, "Admins only")
    return u


def member(u: dict = Depends(signed_in)) -> dict:
    if not u["person"]:
        raise HTTPException(403, "This account has no personal graph")
    return u


def start_session(response: Response, email: str) -> dict:
    token = accounts.new_token(email)
    response.set_cookie("kt", token, httponly=True, samesite="lax", max_age=30 * 86400)
    return accounts.user(token)


def add_person(g, name: str, email: str, role: str, github_login: str | None) -> str:
    """A new employee's Person node, or the GitHub contributor already in the graph with that login."""
    if github_login:
        found = g.ro_query("MATCH (p:Person {github: $gh}) RETURN p.id", {"gh": github_login}).result_set
        if found:
            g.query("MATCH (p:Person {id: $id}) SET p.name = $name, p.email = $email, p.role = $role",
                    {"id": found[0][0], "name": name, "email": email, "role": role})
            return found[0][0]
    taken = {r[0] for r in g.ro_query("MATCH (p:Person) RETURN p.id").result_set}
    pid = base = slug(email.split("@")[0])
    n = 1
    while pid in taken:
        n += 1
        pid = f"{base}-{n}"
    g.query("CREATE (:Person {id: $id, name: $name, email: $email, role: $role, github: $gh, active: true, "
            "joined_at: $today})", {"id": pid, "name": name, "email": email, "role": role, "gh": github_login,
                                    "today": date.today().isoformat()})
    return pid


@app.post("/api/auth/register")
def register(body: Register, response: Response):
    if len(body.password) < 6:
        raise HTTPException(400, "Use a password of at least 6 characters")
    c = accounts.create_company(body.company.strip())
    pid = add_person(graph(c["graph"]), body.name, body.email.lower(), "Admin", None)
    try:
        accounts.add_user(c["id"], body.name, body.email, body.password, "admin", pid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return start_session(response, body.email.strip().lower())


@app.post("/api/auth/login")
def login(body: Login, response: Response):
    try:
        token = accounts.login(body.email, body.password)
    except PermissionError as e:
        raise HTTPException(401, str(e))
    response.set_cookie("kt", token, httponly=True, samesite="lax", max_age=30 * 86400)
    return accounts.user(token)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    accounts.logout(request.cookies.get("kt", ""))
    response.delete_cookie("kt")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    return accounts.user(request.cookies.get("kt"))


# ── Shared views ─────────────────────────────────────────────────────────────
def company_view(u: dict, ids: list | None = None) -> dict:
    """People, KNOWS edges and decisions of a company graph, limited to `ids` when given (a member's view)."""
    g = graph(u["graph"])
    people = [p for p in rows(g, PEOPLE) if not ids or p["id"] in ids]
    knows = [{**k, "score": round(k["score"], 2), "last": day(k["last"])}
             for k in rows(g, KNOWS) if not ids or k["person"] in ids]
    visible = {k["item"] for k in knows} | {
        r[0] for r in g.ro_query(RECORDED_BY, {"people": ids or [p["id"] for p in people]}).result_set}
    return {"workspace": {"name": u["company_name"], "snapshot": date.today().isoformat()}, "people": people,
            "knows": knows, "decisions": {d["id"]: d for d in rows(g, DECISIONS) if d["id"] in visible}}


def inherited(g, leaver: str, successor: str) -> list:
    return rows(g, INHERITED, {"leaver": leaver, "successor": successor})


def own_ids(u: dict) -> list:
    """The user's own person and everyone they succeeded, directly or down a chain."""
    preds = [r[0] for r in graph(u["graph"]).ro_query(PREDECESSORS, {"me": u["person"]}).result_set]
    return [u["person"], *preds]


def visible_ids(u: dict) -> list | None:
    """None for an admin (everyone); otherwise the member and everyone they succeeded."""
    return None if u["role"] == "admin" else own_ids(u)


@app.get("/api/why/{decision}")
def why(decision: str, u: dict = Depends(signed_in)):
    ids = visible_ids(u)
    if ids is not None and decision not in company_view(u, ids)["decisions"]:
        raise HTTPException(404, "Not in your graph")
    g = graph(u["graph"])
    d = next((d for d in rows(g, DECISIONS) if d["id"] == decision), None)
    if not d:
        raise HTTPException(404, "No such decision")
    return {"decision": d, "trace": trace(g, decision)}


@app.get("/api/find")
def find(q: str, u: dict = Depends(signed_in)):
    """Full-text search over the chunks this user may see."""
    words, ids = search_words(q), visible_ids(u)
    if not words:
        return []
    g = graph(u["graph"])
    return rows(g, SEARCH, {"q": words}) if ids is None else rows(g, SEARCH_MINE, {"q": words, "people": ids})


@app.get("/api/agent")
def agent_ask(q: str, u: dict = Depends(signed_in)):
    """The agent on the company graph, limited to what this user may read."""
    ids, allowed = view_scope(u)
    return agent.ask(graph(u["graph"]), q, company_llm(u["company"]), ids, allowed)


def view_scope(u: dict) -> tuple[list | None, set | None]:
    """(people, items) the agent may show this user: None for an admin; for a member, the people whose sources they
    may read, and the decisions and files in their view."""
    ids = visible_ids(u)
    if ids is None:
        return None, None
    view = company_view(u, ids)
    return ids, set(view["decisions"]) | {k["item"] for k in view["knows"]}


@app.get("/api/source")
def read_source(ref: str, u: dict = Depends(signed_in)):
    """The full text of a doc, AI session or chat thread this user may see (see graph.VISIBLE)."""
    g = graph(u["graph"])
    found = g.ro_query(READABLE, {"ref": ref, "people": visible_ids(u)}).result_set
    if not found:
        raise HTTPException(404, "Not in your graph")
    return {"ref": ref, "title": found[0][0], "text": text(g, ref)}


class Share(BaseModel):
    ref: str
    shared: bool


@app.post("/api/source/share")
def share_source(body: Share, u: dict = Depends(signed_in)):
    """Share a doc with the whole company, or make it private again. Its author or an admin may."""
    if not graph(u["graph"]).query(SHARE, {"ref": body.ref, "shared": body.shared, "admin": u["role"] == "admin",
                                           "me": u["person"]}).result_set:
        raise HTTPException(404, "Only the author or an admin can share this doc")
    return {"ok": True}


# ── Admin ────────────────────────────────────────────────────────────────────
class Employee(BaseModel):
    name: str
    email: str
    role: str = "Engineer"
    github: str | None = None
    password: str = "welcome123"


class Offboard(BaseModel):
    person: str
    successor: str


class Settings(BaseModel):
    provider: str = "custom"
    base: str = ""
    model: str = ""
    key: str = ""
    github_token: str = ""


class Repo(BaseModel):
    url: str


def masked(secret: str | None) -> str:
    return f"…{secret[-4:]}" if secret else ""


@app.get("/api/admin")
def admin_overview(u: dict = Depends(admin)):
    g, c = graph(u["graph"]), accounts.company(u["company"])
    view = company_view(u)
    successors = rows(g, SUCCESSORS)
    for s in successors:
        items = inherited(g, s["leaver"], s["successor"])
        agenda = [i for i in items if not i["others"]]
        s.update(agenda=len(agenda), learned=sum(i["learned"] for i in agenda))
    return {**view,
            "radar": radar_view(g), "alerts": agent.alerts(g),
            "successors": successors, "sources": rows(g, SOURCES, {"people": None}),
            "users": accounts.users(u["company"]),
            "settings": {"provider": c.get("llm_provider") or "", "base": c.get("llm_base") or "",
                         "model": c.get("llm_model") or "", "key": masked(c.get("llm_key")),
                         "github_token": masked(c.get("github_token"))},
            "repo": {"url": c.get("repo") or "", "status": c.get("repo_status") or "", "sync_at": c.get("sync_at") or ""},
            "presets": extract.PRESETS}


@app.post("/api/admin/employees")
def add_employee(body: Employee, u: dict = Depends(admin)):
    pid = add_person(graph(u["graph"]), body.name, body.email.lower(), body.role, body.github or None)
    try:
        accounts.add_user(u["company"], body.name, body.email, body.password, "member", pid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"person": pid, "email": body.email.lower(), "password": body.password}


@app.get("/api/admin/dryrun")
def admin_dryrun(leavers: str, u: dict = Depends(admin)):
    return dry_run(u["graph"], leavers.split(","))


@app.post("/api/admin/offboard")
def offboard(body: Offboard, u: dict = Depends(admin)):
    if body.person == body.successor:
        raise HTTPException(400, "Pick someone else as the successor")
    active = dict(graph(u["graph"]).ro_query("MATCH (p:Person) WHERE p.id IN $ids RETURN p.id, p.active",
                                             {"ids": [body.person, body.successor]}).result_set)
    if not active.get(body.person) or not active.get(body.successor):
        raise HTTPException(400, "Both people must exist and still be active")
    graph(u["graph"]).query(OFFBOARD, {"person": body.person, "successor": body.successor,
                                       "day": date.today().isoformat()})
    accounts.disable_person(u["company"], body.person)
    return {"ok": True}


@app.put("/api/admin/settings")
def save_settings(body: Settings, u: dict = Depends(admin)):
    props = {"llm_provider": body.provider, "llm_base": body.base.strip(), "llm_model": body.model.strip()}
    if props["llm_base"]:
        try:
            extract.check_base(props["llm_base"])
        except ValueError as e:
            raise HTTPException(400, str(e))
    if body.key.strip():
        props["llm_key"] = body.key.strip()
    if body.github_token.strip():
        props["github_token"] = body.github_token.strip()
    accounts.update_company(u["company"], **props)
    return {"ok": True}


@app.post("/api/admin/settings/test")
def test_settings(u: dict = Depends(admin)):
    llm = accounts.llm(u["company"])
    if not llm:
        raise HTTPException(400, "Save an API key first")
    try:
        return {"reply": extract.chat(llm["base"], llm["key"], llm["model"], "Reply with the single word: ready")[:200]}
    except Exception as e:
        raise HTTPException(502, str(e))


class Review(BaseModel):
    action: str  # "confirm" | "reject"


@app.post("/api/admin/decisions/{decision}")
def review_decision(decision: str, body: Review, u: dict = Depends(admin)):
    """Confirm a proposed decision (it starts counting in the radar and handovers) or reject it (deleted)."""
    if body.action not in ("confirm", "reject"):
        raise HTTPException(400, "Use confirm or reject")
    g = graph(u["graph"])
    if not g.ro_query("MATCH (d:Decision {id: $id, status: 'proposed'}) RETURN d.id", {"id": decision}).result_set:
        raise HTTPException(404, "No proposed decision with that id")
    g.query("MATCH (d:Decision {id: $id}) " + ("SET d.status = 'active'" if body.action == "confirm" else "DETACH DELETE d"),
            {"id": decision})
    return {"ok": True}


@app.delete("/api/admin/sources/{ref:path}")
def remove_source(ref: str, u: dict = Depends(admin)):
    """Remove an uploaded doc or AI session, its chunks and any decision only it recorded, then rescore."""
    g = graph(u["graph"])
    if not g.ro_query("MATCH (s:Source {ref: $ref}) WHERE s:Doc OR s:AgentSession RETURN s.ref", {"ref": ref}).result_set:
        raise HTTPException(404, "No uploaded doc or AI session with that ref")
    ids = [r[0] for r in g.ro_query(SOURCE_DECISIONS, {"ref": ref}).result_set]
    for q in DELETE_SOURCE:
        g.query(q, {"ref": ref, "ids": ids})
    derive(g)
    return {"ok": True}


def ingest_repo(cid: str, graph_name: str, url: str):
    status = lambda msg: accounts.update_company(cid, repo_status=msg)
    try:
        # without a token GitHub allows 60 requests an hour per IP, shared by every company on this server
        token = accounts.company(cid).get("github_token") or os.getenv("GITHUB_TOKEN")
        status(github.ingest(graph(graph_name), url, token, status))
    except Exception as e:
        status(f"failed: {e}")


@app.post("/api/admin/github")
def connect_github(body: Repo, tasks: BackgroundTasks, u: dict = Depends(admin)):
    if u["company"] == DEMO["company"]:  # its admin login is public: a repo here would mix into everyone's demo
        raise HTTPException(400, "The demo company is shared. Register your own company to connect a repo: it gets "
                                 "its own graph.")
    try:
        github.repo_name(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    accounts.update_company(u["company"], repo=body.url.strip(), repo_status="queued")
    tasks.add_task(ingest_repo, u["company"], u["graph"], body.url)
    return {"ok": True}


class AutoSync(BaseModel):
    at: str = ""  # UTC "HH:MM"; empty turns the daily sync off


@app.put("/api/admin/autosync")
def set_autosync(body: AutoSync, u: dict = Depends(admin)):
    if body.at and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", body.at):
        raise HTTPException(400, "Use a time like 19:00")
    now = datetime.now(timezone.utc)
    props = {"sync_at": body.at}
    if body.at and body.at <= now.strftime("%H:%M"):
        props["synced_on"] = now.date().isoformat()  # today's time has passed: start tomorrow, not right now
    accounts.update_company(u["company"], **props)
    return {"ok": True}


def repo_busy(status: str | None) -> bool:
    return bool(status) and not status.startswith(("done", "failed"))


async def auto_sync():
    """Every minute, with nobody clicking anything:
    1. Once a day, at each company's chosen time (after work hours by default), re-read its GitHub repo. That pulls
       new commits and PRs and re-runs `derive` at today's date, so KNOWS scores keep decaying even when nothing new
       was committed. Only the sync time is a setting: every event keeps its own timestamp, whatever hour it happened.
    2. The agent watches every company's radar (agent.watch): a new item only one person knows gets an alert and a KT
       brief, so a new risk from a sync, an upload or a CLI push is flagged within a minute."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            for cid, graph_name, repo, status in accounts.due_syncs(now.strftime("%H:%M"), now.date().isoformat()):
                if repo_busy(status):
                    continue  # a manual sync is running; try again next minute
                accounts.update_company(cid, synced_on=now.date().isoformat(), repo_status="queued (daily sync)")
                await asyncio.to_thread(ingest_repo, cid, graph_name, repo)
            # ponytail: every company every minute (two reads when nothing changed); trigger from derive if this grows
            for cid, graph_name in accounts.companies():
                await asyncio.to_thread(agent.watch, graph(graph_name), company_llm(cid, background=True))
        except Exception as e:  # FalkorDB down for a moment: keep the loop alive
            print(f"auto-sync: {e}")
        await asyncio.sleep(60)


# ── Member ───────────────────────────────────────────────────────────────────
class Upload(BaseModel):
    name: str
    data: str  # base64


class Learned(BaseModel):
    item: str


class CliSessions(BaseModel):
    sessions: list[dict]


MAX_UPLOAD = 8 * 1024 * 1024


@app.get("/api/brain")
def brain(u: dict = Depends(member)):
    g, ids = graph(u["graph"]), own_ids(u)
    view = company_view(u, ids)
    view["me"] = u["person"]
    view["inherited"] = [{"person": p, "items": inherited(g, p, u["person"])} for p in ids[1:]]
    view["sources"] = rows(g, SOURCES, {"people": [u["person"]]})
    view["company_docs"] = [s for s in rows(g, SOURCES, {"people": None}) if s["shared"]]
    view["alerts"] = agent.alerts(g, u["person"])  # briefs are built from the knower's own sources only
    return view


def queue_extraction(tasks: BackgroundTasks, u: dict, refs: list):
    llm = company_llm(u["company"])
    for ref in refs:
        tasks.add_task(uploads.extract_into, graph(u["graph"]), llm, ref, u["role"] == "admin")


@app.post("/api/brain/upload")
def upload(body: Upload, tasks: BackgroundTasks, u: dict = Depends(member)):
    raw = base64.b64decode(body.data)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Files up to 8 MB")
    try:
        kind, parsed = uploads.parse_upload(body.name, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    g = graph(u["graph"])
    refs = uploads.add_sessions(g, u["person"], parsed) if kind == "sessions" else \
        [uploads.add_doc(g, u["person"], body.name, parsed)]
    queue_extraction(tasks, u, refs)
    return {"refs": refs}


@app.post("/api/brain/learned")
def learned(body: Learned, u: dict = Depends(member)):
    g = graph(u["graph"])
    if not any(i["item"] == body.item for p in own_ids(u)[1:] for i in inherited(g, p, u["person"])):
        raise HTTPException(403, "You can only mark items from a brain you inherited")
    now = uploads.now_iso()
    g.query(MARK_LEARNED, {"person": u["person"], "item": body.item, "at": now, "ts": uploads.ts(now)})
    return {"ok": True}


@app.post("/api/brain/cli-token")
def cli_token(u: dict = Depends(member)):
    return {"token": accounts.new_token(u["email"], "cli")}


def cli_user(request: Request) -> dict:
    u = accounts.user(request.headers.get("authorization", "").removeprefix("Bearer ").strip(), kind="cli")
    if not u or not u["person"]:
        raise HTTPException(401, "Bad or revoked CLI token")
    return u


@app.post("/api/cli/sessions")
def cli_sessions(body: CliSessions, tasks: BackgroundTasks, u: dict = Depends(cli_user)):
    refs = uploads.add_sessions(graph(u["graph"]), u["person"], body.sessions)
    queue_extraction(tasks, u, refs)
    return {"refs": refs}


# The agent's tools for a coding agent (cli/ktbrain.py mcp): the same catalogue and the same view as the Ask page.
class ToolCall(BaseModel):
    name: str
    args: dict = {}


@app.get("/api/cli/tools")
def cli_tools(u: dict = Depends(cli_user)):
    return agent.specs(u["role"] == "admin")


@app.post("/api/cli/tool")
def cli_tool(body: ToolCall, u: dict = Depends(cli_user)):
    ids, allowed = view_scope(u)
    return agent.call(graph(u["graph"]), body.name, body.args, ids, allowed)
