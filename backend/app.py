"""KT Brain API. Run from backend/:  uv run uvicorn app:app --reload

Public:  the TiffinBox story (/api/workspace, /api/dryrun, /api/search) and sign-in.
Admin:   /api/admin/*   every employee's graph, offboarding with a successor, sources, AI provider settings.
Member:  /api/brain/*   your own graph, uploads, CLI token, and the brain of anyone you succeeded.
CLI:     /api/cli/*     `ktbrain sync` pushes AI sessions with a per-user token.
"""
import base64
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

import accounts
import extract
from graph import (COVERED, DECISIONS, EDGE_COUNTS, INHERITED, KNOWS, MARK_LEARNED, MENTOR, NODE_COUNTS, OFFBOARD,
                   ORPHANED, PEOPLE, RADAR, RECORDED_BY, SEARCH, SEARCH_MINE, SOURCES, SUCCESSORS, db, dry_run, graph,
                   rows, trace)
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
    yield


app = FastAPI(title="KT Brain", lifespan=lifespan)


def day(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "person"


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
    return {"ok": True, "graphs": db.list_graphs()}


@app.get("/api/workspace")
def workspace():
    """Everything the six story screens show, read live from the graphs."""
    g, end = graph(DAY_GRAPH), graph(END_GRAPH)
    people = [{k: v for k, v in p.items() if k != "active"} for p in rows(end, PEOPLE)]  # the story is set on Sep 21
    leavers = [p["id"] for p in people if p["last_day"]]
    cases = [[p] for p in leavers] + ([leavers] if len(leavers) > 1 else [])
    runs = {"+".join(c): dry_run(DAY_GRAPH, c) for c in cases}
    decisions = {d["id"]: d for d in rows(g, DECISIONS)}
    counts = dict(end.ro_query(NODE_COUNTS).result_set)
    counts["edges"] = sum(n for _, n in end.ro_query(EDGE_COUNTS).result_set)
    return {
        "workspace": {"name": "TiffinBox", "synthetic": True, "story": f"2026-04-01 to {END}", "snapshot": DAY,
                      "counts": counts},
        "people": people,
        "decisions": decisions,
        "knows": [{**k, "score": round(k["score"], 2), "last": day(k["last"])} for k in rows(g, KNOWS)],
        "radar": [{"item": r["item"], "kind": r["kind"], "person": r["only_knower"], "score": round(r["score"], 2)}
                  for r in rows(g, RADAR)],
        "dry_runs": runs,
        "traces": {d: trace(g, d) for d, v in decisions.items() if v["status"] == "active"},
        "handover": handover(runs["+".join(leavers)]["agenda"]),
    }


@app.get("/api/dryrun")
def dryrun(leavers: str):
    """Simulate any set of TiffinBox people leaving, e.g. ?leavers=arjun,priya"""
    return dry_run(DAY_GRAPH, leavers.split(","))


def search_words(q: str) -> str:
    """Any query word may match (RediSearch OR syntax)."""
    return "|".join(w for w in re.findall(r"[a-z0-9_]+", q.lower()) if len(w) > 2)


@app.get("/api/search")
def search(q: str):
    words = search_words(q)
    return rows(graph(DAY_GRAPH), SEARCH, {"q": words}) if words else []


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
    """The user's own person and everyone they succeeded."""
    preds = [r[0] for r in graph(u["graph"]).ro_query(SUCCESSORS).result_set if r[1] == u["person"]]
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
            "radar": [{"item": r["item"], "kind": r["kind"], "person": r["only_knower"], "score": round(r["score"], 2)}
                      for r in rows(g, RADAR)],
            "successors": successors, "sources": rows(g, SOURCES, {"people": None}),
            "users": accounts.users(u["company"]),
            "settings": {"provider": c.get("llm_provider") or "", "base": c.get("llm_base") or "",
                         "model": c.get("llm_model") or "", "key": masked(c.get("llm_key")),
                         "github_token": masked(c.get("github_token"))},
            "repo": {"url": c.get("repo") or "", "status": c.get("repo_status") or ""},
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
    graph(u["graph"]).query(OFFBOARD, {"person": body.person, "successor": body.successor,
                                       "day": date.today().isoformat()})
    accounts.disable_person(u["company"], body.person)
    return {"ok": True}


@app.put("/api/admin/settings")
def save_settings(body: Settings, u: dict = Depends(admin)):
    props = {"llm_provider": body.provider, "llm_base": body.base.strip(), "llm_model": body.model.strip()}
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


def ingest_repo(cid: str, graph_name: str, url: str):
    status = lambda msg: accounts.update_company(cid, repo_status=msg)
    try:
        status(github.ingest(graph(graph_name), url, accounts.company(cid).get("github_token"), status))
    except Exception as e:
        status(f"failed: {e}")


@app.post("/api/admin/github")
def connect_github(body: Repo, tasks: BackgroundTasks, u: dict = Depends(admin)):
    try:
        github.repo_name(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    accounts.update_company(u["company"], repo=body.url.strip(), repo_status="queued")
    tasks.add_task(ingest_repo, u["company"], u["graph"], body.url)
    return {"ok": True}


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
    return view


def queue_extraction(tasks: BackgroundTasks, u: dict, refs: list):
    llm = accounts.llm(u["company"])
    for ref in refs:
        tasks.add_task(uploads.extract_into, graph(u["graph"]), llm, ref)


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
    now = uploads.now_iso()
    graph(u["graph"]).query(MARK_LEARNED, {"person": u["person"], "item": body.item, "at": now, "ts": uploads.ts(now)})
    return {"ok": True}


@app.post("/api/brain/cli-token")
def cli_token(u: dict = Depends(member)):
    return {"token": accounts.new_token(u["email"], "cli")}


@app.post("/api/cli/sessions")
def cli_sessions(body: CliSessions, request: Request, tasks: BackgroundTasks):
    u = accounts.user(request.headers.get("authorization", "").removeprefix("Bearer ").strip(), kind="cli")
    if not u or not u["person"]:
        raise HTTPException(401, "Bad or revoked CLI token")
    refs = uploads.add_sessions(graph(u["graph"]), u["person"], body.sessions)
    queue_extraction(tasks, u, refs)
    return {"refs": refs}
