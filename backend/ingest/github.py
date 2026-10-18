"""A public GitHub repo -> a company graph: commits (with files), PRs and reviews. Stdlib only.

Without a token GitHub allows 60 requests an hour, so the default pull is small (25 commits, 10 PRs, about 46 calls).
With a token from the company settings it pulls 100 commits and 40 PRs. Authors are matched to employees by
`Person.github`; anyone unmatched becomes a "GitHub contributor" person the admin can invite later.
"""
import json
import re
import urllib.error
import urllib.request

from graph import LINKS, derive, load
from ingest.uploads import ts

API = "https://api.github.com"
TRIVIAL_BOTS = ("[bot]",)


class NotFound(RuntimeError):
    pass


def get(path: str, token: str | None):
    req = urllib.request.Request(path if path.startswith("http") else API + path, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "kt-brain",
        **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NotFound(f"GitHub 404 for {path} (is the repo public and spelled right?)") from None
        hint = " (rate limit: add a GitHub token in Settings)" if e.code in (403, 429) else ""
        raise RuntimeError(f"GitHub {e.code} for {path}{hint}") from None


def repo_name(url: str) -> str:
    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$", url.strip()) or \
        re.fullmatch(r"([\w.-]+)/([\w.-]+)", url.strip())
    if not m:
        raise ValueError("Use a GitHub URL like https://github.com/owner/repo")
    return f"{m.group(1)}/{m.group(2)}"


def ingest(g, url: str, token: str | None, status) -> str:
    repo = repo_name(url)
    n_commits, n_prs = (100, 40) if token else (25, 10)
    known = dict(g.ro_query("MATCH (p:Person) WHERE p.github IS NOT NULL RETURN p.github, p.id").result_set)
    taken = {r[0] for r in g.ro_query("MATCH (p:Person) RETURN p.id").result_set}
    people = {}

    def person(login: str, at: str) -> str:
        if login not in known:
            # a new id, so an unmatched login never merges into (and reactivates) an existing employee
            pid = base = re.sub(r"[^a-z0-9]+", "-", login.lower()).strip("-") or "contributor"
            n = 1
            while pid in taken:
                n += 1
                pid = f"{base}-{n}"
            taken.add(pid)
            known[login] = pid
            people[login] = {"id": known[login], "props": {"name": login, "role": "GitHub contributor",
                                                           "github": login, "active": True, "joined_at": at[:10]}}
        elif login in people and at[:10] < people[login]["props"]["joined_at"]:
            people[login]["props"]["joined_at"] = at[:10]
        return known[login]

    status(f"reading {repo}: commits")
    commits = []
    for i, c in enumerate(get(f"/repos/{repo}/commits?per_page={n_commits}", token)):
        login = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
        if login.endswith(TRIVIAL_BOTS):
            continue
        status(f"reading {repo}: commit {i + 1}/{n_commits}")
        files = get(c["url"], token).get("files", [])
        at = c["commit"]["author"]["date"]
        commits.append({"sha": c["sha"], "author": person(login, at), "props": {
            "message": c["commit"]["message"].split("\n")[0], "at": at, "ts": ts(at)},
            "files": [{"path": f["filename"], "additions": f["additions"], "deletions": f["deletions"]} for f in files]})

    status(f"reading {repo}: pull requests")
    prs, reviews = [], []
    try:
        pulls = get(f"/repos/{repo}/pulls?state=all&per_page={n_prs}", token)
    except NotFound:  # the repo has pull requests turned off (torvalds/linux takes patches by email): commits only
        pulls = None
    for p in pulls or []:
        if p["user"]["login"].endswith(TRIVIAL_BOTS):
            continue
        prs.append({"id": p["number"], "author": person(p["user"]["login"], p["created_at"]),
                    "commits": [c["sha"] for c in get(p["commits_url"], token)],
                    "props": {"title": p["title"], "body": (p["body"] or "")[:2000], "branch": p["head"]["ref"],
                              "merged_at": p["merged_at"], "at": p["created_at"], "ts": ts(p["created_at"])}})
        reviews += [{"id": r["id"], "by": person(r["user"]["login"], r["submitted_at"]), "pr": p["number"],
                     "props": {"state": r["state"], "body": (r["body"] or "")[:1000], "at": r["submitted_at"],
                               "ts": ts(r["submitted_at"])}}
                    for r in get(f"{p['url']}/reviews", token) if r.get("user") and r.get("submitted_at")]

    paths = sorted({f["path"] for c in commits for f in c["files"]})
    service = lambda path: path.split("/")[0] if "/" in path else "(root)"
    load(g, "person", list(people.values()))
    load(g, "service", [{"id": s} for s in sorted({service(p) for p in paths})])
    load(g, "file", [{"path": p, "service": service(p)} for p in paths])
    for name, rows in (("commit", commits), ("pr", prs), ("review", reviews)):
        load(g, name, rows)
    for q in LINKS:
        g.query(q)
    derive(g)
    no_prs = " (pull requests are turned off on this repo)" if pulls is None else ""
    return f"done: {len(commits)} commits, {len(prs)} PRs{no_prs}, {len(reviews)} reviews, {len(people)} new contributors"
