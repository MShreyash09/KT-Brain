"""Load the TiffinBox fixtures (data/tiffinbox/) into a FalkorDB graph.

Run from backend/:
  uv run python -m ingest.fixtures                      # whole story -> graph tiffinbox_template
  uv run python -m ingest.fixtures --until 2026-09-21   # state before Meera joins (the answer-key day)

The graph is rebuilt from scratch on every run. Events after --until (UTC, inclusive) are skipped.
"""
import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from graph import EDGE_COUNTS, INDEXES, LINKS, NODE_COUNTS, RADAR, chunk_rows, db, derive, graph, load
from ingest.uploads import parse_claude_session

DATA = Path(__file__).resolve().parents[2] / "data" / "tiffinbox"
ORDER = ["person", "service", "depends_on", "file", "commit", "pr", "review", "ticket", "thread", "posted_in",
         "session", "doc", "chunk", "decision", "about", "supersedes", "records_decision", "pattern", "implements",
         "incident", "records_incident", "research", "cites", "found", "informed_by", "justifies", "feature",
         "decision_feature", "learned"]


def read(path):
    return json.loads((DATA / path).read_text(encoding="utf-8"))


def ts(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def event(at, **props):
    return {**props, "at": at, "ts": ts(at)}


def build_rows(until):
    ok = lambda at: at <= until  # ISO-8601 UTC strings sort by time
    rows = defaultdict(list)
    people = read("people.json")
    by_email = {p["email"]: p["id"] for p in people}
    by_login = {p["github"]: p["id"] for p in people}
    by_chat = {p["chat_user"]: p["id"] for p in people}

    for p in people:
        if p["joined_at"] <= until[:10]:
            rows["person"].append({"id": p["id"], "props": {
                "name": p["name"], "role": p["role"], "email": p["email"], "github": p["github"], "joined_at": p["joined_at"],
                "resigned_at": p["resigned_at"], "last_day": p["last_day"],
                "active": p["last_day"] is None or p["last_day"] > until[:10]}})

    files = read("files.json")
    rows["service"] = [{"id": s} for s in sorted({f["service"] for f in files["files"]})]
    rows["depends_on"] = [{"a": d["service"], "b": d["depends_on"]} for d in files["service_depends_on"]]
    rows["file"] = files["files"]

    for c in read("github/commits.json"):
        at = c["commit"]["author"]["date"]
        if ok(at):
            rows["commit"].append({"sha": c["sha"], "author": by_login[c["author"]["login"]],
                                   "props": event(at, message=c["commit"]["message"]),
                                   "files": [{"path": f["filename"], "additions": f["additions"],
                                              "deletions": f["deletions"]} for f in c["files"]]})
    for p in read("github/pulls.json"):
        if ok(p["created_at"]):
            rows["pr"].append({"id": p["number"], "author": by_login[p["user"]["login"]], "commits": p["commits"],
                               "props": event(p["created_at"], title=p["title"], body=p["body"],
                                              branch=p["head"]["ref"], merged_at=p["merged_at"])})
            rows["review"] += [{"id": r["id"], "by": by_login[r["user"]["login"]], "pr": p["number"],
                                "props": event(r["submitted_at"], state=r["state"], body=r["body"])}
                               for r in p["reviews"] if ok(r["submitted_at"])]

    for t in read("tickets.json"):
        f = t["fields"]
        if ok(f["created"]):
            rows["ticket"].append({"id": t["key"], "assignee": by_email[f["assignee"]["emailAddress"]],
                                   "prs": t["links"]["pull_requests"],
                                   "props": event(f["created"], title=f["summary"], description=f["description"],
                                                  status=f["status"]["name"], resolved_at=f["resolutiondate"],
                                                  reporter=by_email[f["reporter"]["emailAddress"]])})

    # Google Chat, company only: SPACEs without external users; people listed in people.json
    spaces = {s["name"]: s for s in read("google_chat/spaces.json")}
    threads = defaultdict(list)
    for m in read("google_chat/messages.json"):
        s = spaces[m["space"]["name"]]
        if s["spaceType"] == "SPACE" and not s["externalUserAllowed"] and ok(m["createTime"]):
            threads[m["thread"]["name"]].append(m)
    for tid, msgs in threads.items():
        rows["thread"].append({"id": tid, "props": event(
            msgs[0]["createTime"], space=spaces[msgs[0]["space"]["name"]]["displayName"])})
        rows["chunk"] += chunk_rows(f"thread:{tid}", "\n".join(f"{m['sender']['displayName']}: {m['text']}" for m in msgs))
        posters = defaultdict(list)
        for m in msgs:
            if m["sender"]["type"] == "HUMAN" and m["sender"]["name"] in by_chat:
                posters[by_chat[m["sender"]["name"]]].append(m["createTime"])
        rows["posted_in"] += [{"person": p, "thread": tid, "props": event(times[0], messages=len(times))}
                              for p, times in posters.items()]

    # Claude Code logs, slimmed: prompts + assistant text + edited file paths
    for path in sorted((DATA / "sessions").glob("*.jsonl")):
        sess = parse_claude_session([json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()])
        if not ok(sess["started"]):
            continue
        rows["session"].append({
            "id": sess["id"], "files": sess["files"],
            "person": re.search(r"/home/([^/]+)/", sess["cwd"]).group(1),  # fixture convention; uploads use the uploader
            "props": event(sess["started"], tool="claude-code", branch=sess["branch"], ended_at=sess["ended"],
                           title=sess["title"])})
        rows["chunk"] += chunk_rows(f"session:{sess['id']}", sess["text"])

    for path in sorted((DATA / "docs").rglob("*.md")):
        _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
        meta = dict(line.split(": ", 1) for line in front.strip().splitlines())
        if ok(meta["date"]):
            did = path.relative_to(DATA).as_posix()
            rows["doc"].append({"id": did, "author": by_email[meta["author"]],
                                "props": event(meta["date"], title=meta["title"], kind=meta["kind"])})
            rows["chunk"] += chunk_rows(f"doc:{did}", body.strip())

    # cached extraction
    x = read("extractions.json")
    decisions = [d for d in x["decisions"] if ok(d["at"])]
    for d in decisions:
        rows["decision"].append({"id": d["id"], "props": event(d["at"], what=d["what"], why=d["why"], evidence=d["evidence"])})
        rows["about"] += [{"decision": d["id"], "path": p} for p in d["about"]]
        rows["records_decision"] += [{"ref": r, "target": d["id"]} for r in d["recorded_in"]]
        rows["informed_by"] += [{"decision": d["id"], "research": r} for r in d["informed_by"]]
        rows["justifies"] += [{"insight": i, "decision": d["id"]} for i in d["justified_by"]]
        if d["supersedes"]:
            rows["supersedes"].append({"new": d["id"], "old": d["supersedes"]})
    patterns = {p["id"]: p for p in x["patterns"]}
    for d in decisions:
        rows["pattern"] += [{"decision": d["id"], "id": p, "name": patterns[p]["name"]} for p in d["applies"]]
    rows["implements"] = [{"pattern": p["id"], "path": f} for p in x["patterns"] for f in p["implemented_in"]]
    for i in x["incidents"]:
        if ok(i["at"]):
            rows["incident"].append({"id": i["id"], "caused_by": i["caused_by"],
                                     "props": event(i["at"], title=i["title"], severity=i["severity"])})
            rows["records_incident"] += [{"ref": r, "target": i["id"]} for r in i["recorded_in"]]
    sources = {s["id"]: s for s in x["external_sources"]}
    insights = {i["id"]: i for i in x["insights"]}
    for r in x["research"]:
        rows["research"].append({"id": r["id"], "title": r["title"], "doc": r["doc"]})
        rows["cites"] += [{"research": r["id"], "id": s, "props": {k: v for k, v in sources[s].items() if k != "id"}}
                          for s in r["cites"]]
        rows["found"] += [{"research": r["id"], "id": i, "text": insights[i]["text"]} for i in r["found"]]
    for f in x["features"]:
        rows["feature"] += [{"pr": int(ref.split(":")[1]), "id": f["id"], "name": f["name"]} for ref in f["implemented_by"]]
        rows["decision_feature"] += [{"decision": d, "feature": f["id"]} for d in f["decisions"]]

    for kt in read("kt_sessions.json"):
        if ok(kt["at"]):
            rows["learned"] += [{"person": kt["learner"], "item": item,
                                 "props": event(kt["at"], via=kt["via"], source=kt["id"], taught_by=kt["leaver"])}
                                for item in kt["covered"]]
    return rows


def build(name, until):
    """Rebuild graph `name` from the fixtures up to `until` (YYYY-MM-DD), then derive KNOWS."""
    if name in db.list_graphs():
        graph(name).delete()
    g = graph(name)
    for q in INDEXES:
        g.query(q)
    rows = build_rows(until + "T23:59:59Z")
    for n in ORDER:
        load(g, n, rows[n])
    for q in LINKS:
        g.query(q)
    derive(g)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="tiffinbox_template")
    ap.add_argument("--until", default="2026-09-30", help="YYYY-MM-DD; skip events after this day")
    args = ap.parse_args()

    g = build(args.graph, args.until)
    print(f"graph {args.graph} (until {args.until})")
    print("nodes:", ", ".join(f"{label} {n}" for label, n in g.ro_query(NODE_COUNTS).result_set))
    print("edges:", ", ".join(f"{t} {n}" for t, n in g.ro_query(EDGE_COUNTS).result_set))
    print("radar (only one active person knows):")
    for item, kind, who, score in g.ro_query(RADAR).result_set:
        print(f"  {who:6} {kind:8} {item}  (score {score:.2f})")


if __name__ == "__main__":
    main()
