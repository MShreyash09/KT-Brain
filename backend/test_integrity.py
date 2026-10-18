"""Uploads and syncs must not be able to poison the graph. Calls the endpoint functions directly, no HTTP.

Run from backend/:  uv run python test_integrity.py   (needs FalkorDB; builds, then deletes, graph _test_integrity)
"""
import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException

import app
import extract
from graph import graph
from ingest import github
from ingest.uploads import add_doc, add_sessions, extract_into

NAME = "_test_integrity"
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
DAY = 86400
now = int(time.time())
g = graph(NAME)
u = lambda person, role="member": {"graph": NAME, "person": person, "role": role, "company": "_none"}


def session(sid, files, text, at):
    return {"id": sid, "files": files, "text": text, "started": at, "ended": at, "title": "t", "branch": "main"}


def chunks(ref):
    return [r[0] for r in g.ro_query("MATCH (c:Chunk)-[:PART_OF]->(:Source {ref: $ref}) RETURN c.text", {"ref": ref}).result_set]


def knows(person, item):
    return g.ro_query("MATCH (:Person {id: $p})-[e:KNOWS]->(k) WHERE coalesce(k.id, k.path) = $i RETURN e.score",
                      {"p": person, "i": item}).result_set


def raises(status, fn, *args):
    try:
        fn(*args)
    except HTTPException as e:
        assert e.status_code == status, e
        return
    raise AssertionError(f"expected HTTP {status}")


def test_future_session_does_not_age_others():
    add_sessions(g, "eve", [session("s-future", ["x/other.py"], "eve: hi", "2036-01-01T00:00:00Z")])
    assert g.ro_query("MATCH (s:AgentSession) RETURN max(s.ts)").result_set[0][0] <= int(time.time())
    assert knows("ann", "pay/retry.py")[0][0] > 0.9  # ann's commit from yesterday still counts in full


def test_session_id_is_per_uploader():
    add_sessions(g, "ann", [session("same-id", [], "ann: original", iso(now - DAY))])
    add_sessions(g, "eve", [session("same-id", [], "eve: overwritten", iso(now))])
    assert chunks("session:ann:same-id") == ["ann: original"], chunks("session:ann:same-id")


def test_session_only_file_is_not_knowledge():
    add_sessions(g, "eve", [session("s-fake", ["pay/retry.py"], "eve: edited", iso(now))])
    assert not knows("eve", "pay/retry.py")  # claimed edit, no commit behind it


def test_mark_learned_only_on_inherited_items():
    raises(403, app.learned, app.Learned(item="pay/retry.py"), u("eve"))
    app.learned(app.Learned(item="pay/retry.py"), u("bob"))  # bob succeeded ann, who knows retry.py
    assert g.ro_query("MATCH (:Person {id: 'bob'})-[:LEARNED]->(:File {path: 'pay/retry.py'}) RETURN 1").result_set


def test_successor_chain():
    assert set(app.own_ids(u("cy"))) == {"cy", "bob", "ann"}, app.own_ids(u("cy"))


def test_offboard_needs_real_active_people():
    raises(400, app.offboard, app.Offboard(person="eve", successor="nobody"), u("x", "admin"))
    raises(400, app.offboard, app.Offboard(person="eve", successor="ann"), u("x", "admin"))  # ann already left
    assert g.ro_query("MATCH (p:Person {id: 'eve'}) RETURN p.active").result_set == [[True]]


def test_uploaded_decisions_are_proposed_until_corroborated():
    doc = "# Plan\n\nWe decided to retry payments three times with backoff.\n"
    extract.chat = lambda *a: json.dumps({"decisions": [{"what": "Retry payments three times", "why": "flaky gateway",
                                                         "evidence": "retry payments three times with backoff"}]})
    llm = {"base": "", "key": "", "model": ""}
    ref = add_doc(g, "eve", "plan.md", doc)
    extract_into(g, llm, ref)
    status = lambda: g.ro_query("MATCH (d:Decision {what: 'Retry payments three times'}) RETURN d.status").result_set
    assert status() == [["proposed"]], status()
    extract_into(g, llm, add_doc(g, "cy", "plan.md", doc))
    assert status() == [["active"]], status()  # a second person recorded it


def test_rate_limited_uploads_wait_and_retry():
    from ingest import uploads
    calls = []

    def limited(*a):
        calls.append(1)
        raise RuntimeError("429 from https://api.groq.com: rate limit")
    extract.chat = limited
    refs = [add_doc(g, "eve", f"burst{i}.md", f"# Burst {i}\n\nNotes number {i}.\n") for i in range(3)]
    state = lambda ref: g.ro_query(uploads.STATE, {"ref": ref}).result_set[0][0]
    uploads.extract_all(g, {"base": "", "key": "", "model": ""}, refs)
    assert len(calls) == 1, "after the first 429 the rest must not call the provider"
    assert all(state(r) == uploads.WAITING for r in refs), [state(r) for r in refs]
    extract.chat = lambda *a: json.dumps({"decisions": []})
    assert uploads.retry_waiting(g, {"base": "", "key": "", "model": ""}, n=2) == 2
    assert uploads.retry_waiting(g, {"base": "", "key": "", "model": ""}, n=2) == 1
    assert all(state(r).startswith("done") for r in refs), [state(r) for r in refs]


def test_any_agent_log():
    import importlib.util
    from ingest import uploads
    spec = importlib.util.spec_from_file_location("ktbrain", __file__.replace("backend", "cli").replace("test_integrity.py", "ktbrain.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    repo = "C:\\work\\shop"
    # Antigravity-shaped step log: a role key, a text field, a timestamp, and file paths in tool-call arguments
    steps = [{"source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-05-01T08:00:00Z",
              "content": "<USER_REQUEST>\nWhy does checkout retry?\n</USER_REQUEST>"},
             {"source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-05-01T08:05:00Z", "content": "Reading it.",
              "tool_calls": [{"args": {"path": "c:\\\\work\\\\shop\\\\api\\\\retry.py"}}, {"args": {"uri": "file:///c:/work/other/x.py"}}]},
             {"type": "plan", "content": "See [cart](file:///c:/work/shop/web/cart%20page.tsx) and token=hunter2secret"}]
    s = cli.any_log(steps, repo, "conv1", "antigravity", "2026-01-01T00:00:00Z")
    assert s["files"] == ["api/retry.py", "web/cart page.tsx"], s["files"]  # paths outside the repo are dropped
    assert s["title"] == "Why does checkout retry?", s["title"]
    assert (s["started"], s["ended"]) == ("2026-05-01T08:00:00Z", "2026-05-01T08:05:00Z")
    assert "hunter2" not in s["text"]
    personal = [{"role": "user", "content": "plan my internship applications"}]
    assert cli.any_log(personal, repo, "c2", "antigravity", "2026-01-01T00:00:00Z") is None  # never touched the repo
    assert cli.any_log(personal, repo, "c2", "ai-agent", "2026-01-01T00:00:00Z", need_repo=False)  # --path: you chose it
    # web upload: any agent's JSONL or JSON goes through the same reader; Claude Code's own format still wins
    jsonl = b'{"role": "user", "content": "add a retry", "timestamp": "2026-05-02T10:00:00Z"}\n{"role": "assistant", "content": "done"}\n'
    kind, parsed = uploads.parse_upload("codex-rollout.jsonl", jsonl)
    assert kind == "sessions" and parsed[0]["text"] == "user: add a retry\nassistant: done" and parsed[0]["tool"] == "ai-agent"
    kind, parsed = uploads.parse_upload("chat.json", b'{"messages": [{"author": "user", "text": "why 7?"}]}')
    assert parsed[0]["title"] == "why 7?", parsed
    ref = uploads.add_sessions(g, "eve", parsed)[0]
    assert g.ro_query("MATCH (s:AgentSession) WHERE s.ref = $r RETURN s.tool", {"r": ref}).result_set == [["ai-agent"]]


def test_s3_bucket_docs():
    import boto3
    from moto import mock_aws
    from ingest import s3
    cfg = {"endpoint": "", "region": "us-east-1", "bucket": "acme-docs", "prefix": "kt", "key_id": "AKIATEST", "secret": "x"}
    with mock_aws():
        b = boto3.client("s3", region_name="us-east-1", aws_access_key_id="AKIATEST", aws_secret_access_key="x")
        b.create_bucket(Bucket="acme-docs")
        b.put_object(Bucket="acme-docs", Key="kt/adr/retries.md", Body=b"# Retries\n\nWe retry **7** times. password=hunter2secret\n")
        b.put_object(Bucket="acme-docs", Key="kt/notes.txt", Body=b"plain notes")
        b.put_object(Bucket="acme-docs", Key="other/outside.md", Body=b"# outside the prefix")
        b.put_object(Bucket="acme-docs", Key="kt/logo.png", Body=b"\x89PNG")
        s3.check(cfg)
        refs, summary = s3.import_docs(g, cfg, "eve", lambda m: None)
        assert summary == "done: 2 documents read, 0 unchanged", summary  # only docs, only under the prefix
        ref = "doc:s3/kt/adr/retries.md"
        assert ref in refs and "hunter2" not in chunks(ref)[0], chunks(ref)  # the graph keeps redacted text only
        assert app.read_source(ref, u("eve"))["original"] is True
        refs, summary = s3.import_docs(g, cfg, "eve", lambda m: None)
        assert refs == [] and summary == "done: 0 documents read, 2 unchanged", summary
        url = s3.link(cfg, "kt/adr/retries.md")
        assert "kt/adr/retries.md" in url and "X-Amz-Signature" in url and "X-Amz-Expires=300" in url, url
    raises(404, app.read_original, ref, u("eve"))  # this test company has no bucket connected
    try:
        s3.client({**cfg, "endpoint": "http://localhost:9000"})
        raise AssertionError("a private endpoint was accepted")
    except ValueError:
        pass


def test_remove_source():
    extract.chat = lambda *a: json.dumps({"decisions": [{"what": "Made up", "why": "", "evidence": "never happened"}]})
    ref = add_doc(g, "eve", "fake.md", "# Fake\n\nThis never happened.\n")
    extract_into(g, {"base": "", "key": "", "model": ""}, ref)
    app.remove_source(ref, u("x", "admin"))
    assert not chunks(ref)
    assert not g.ro_query("MATCH (d:Decision {what: 'Made up'}) RETURN d").result_set


def test_shared_docs_and_private_sessions():
    doc = add_doc(g, "ann", "adr.md", "# ADR\n\nUse idempotency keys. token=hunter2secret sk_live_abcdefghijklmnop1234\n")
    assert "hunter2" not in chunks(doc)[0] and "sk_live" not in chunks(doc)[0], chunks(doc)
    add_sessions(g, "ann", [session("priv", [], "ann: private notes", iso(now))])
    sess = "session:ann:priv"
    assert app.read_source(doc, u("eve"))["title"] == "ADR"  # docs reach the whole company
    raises(404, app.read_source, sess, u("eve"))  # sessions don't
    assert app.read_source(sess, u("cy"))["text"]  # cy succeeded (bob, who succeeded) ann
    raises(404, app.share_source, app.Share(ref=doc, shared=False), u("eve"))  # not the author
    raises(404, app.share_source, app.Share(ref=sess, shared=True), u("ann"))  # sessions can't be shared
    app.share_source(app.Share(ref=doc, shared=False), u("ann"))
    raises(404, app.read_source, doc, u("eve"))
    assert app.read_source(doc, u("x", "admin"))


def test_github_login_does_not_overwrite_employee():
    fake = {"/repos/o/r/commits?per_page=25": [{"sha": "gh1", "url": "c/gh1", "author": {"login": "eve"},
                                                "commit": {"message": "x", "author": {"name": "eve", "date": iso(now)}}}],
            "c/gh1": {"files": [{"filename": "pay/retry.py", "additions": 1, "deletions": 0}]},
            "/repos/o/r/pulls?state=all&per_page=10": []}
    github.get = lambda path, token: fake[path]
    github.ingest(g, "o/r", None, lambda msg: None)
    assert g.ro_query("MATCH (p:Person {id: 'eve'}) RETURN p.name, p.github").result_set == [["Eve", None]]
    assert g.ro_query("MATCH (p:Person {github: 'eve'}) RETURN p.id").result_set == [["eve-2"]]


def test_github_repo_without_pull_requests():
    # torvalds/linux has pull requests turned off: GitHub answers /pulls with 404, the commits must still load
    fake = {"/repos/o/nopr/commits?per_page=25": [{"sha": "np1", "url": "c/np1", "author": None,
                                                   "commit": {"message": "y", "author": {"name": "Linus", "date": iso(now)}}}],
            "c/np1": {"files": [{"filename": "kernel/fork.c", "additions": 2, "deletions": 1}]}}

    def get(path, token):
        if "/pulls" in path:
            raise github.NotFound(path)
        return fake[path]
    github.get = get
    result = github.ingest(g, "o/nopr", None, lambda msg: None)
    assert result.startswith("done: 1 commits, 0 PRs (pull requests are turned off"), result
    assert g.ro_query("MATCH (:Commit {sha: 'np1'})-[:CHANGED]->(f:File) RETURN f.path").result_set == [["kernel/fork.c"]]


def test_daily_sync_runs_once_after_its_time():
    cid, today = "_test_sync", datetime.now(timezone.utc).date().isoformat()
    app.accounts.SYS.query("CREATE (:Company {id: $id, graph: $g, repo: 'o/r'})", {"id": cid, "g": NAME})
    due = lambda now, day="2026-10-16": any(r[0] == cid for r in app.accounts.due_syncs(now, day))
    boss = {**u(None, "admin"), "company": cid}
    try:
        assert not due("23:59"), "no time set: never due"
        app.accounts.update_company(cid, sync_at="13:30")
        assert not due("13:29") and due("13:30") and due("23:00"), "due from its time until midnight UTC"
        app.accounts.update_company(cid, synced_on="2026-10-16")
        assert not due("23:00") and due("13:30", "2026-10-17"), "once a day"
        app.set_autosync(app.AutoSync(at="00:00"), boss)
        assert not due("23:59", today), "a time already past today starts tomorrow"
        app.set_autosync(app.AutoSync(at=""), boss)
        assert not due("23:59", "2099-01-01"), "turned off"
        raises(400, app.set_autosync, app.AutoSync(at="7pm"), boss)
    finally:
        app.accounts.SYS.query("MATCH (c:Company {id: $id}) DELETE c", {"id": cid})


if __name__ == "__main__":
    failed = 0
    try:
        # ann left (succeeded by bob, who left too, succeeded by cy) and committed retry.py yesterday; eve has no github
        g.query("""CREATE (ann:Person {id: 'ann', name: 'Ann', active: false}), (bob:Person {id: 'bob', name: 'Bob', active: false}),
            (cy:Person {id: 'cy', name: 'Cy', active: true}), (:Person {id: 'eve', name: 'Eve', active: true}),
            (ann)-[:SUCCEEDED_BY]->(bob), (bob)-[:SUCCEEDED_BY]->(cy),
            (f:File {path: 'pay/retry.py'}), (ann)-[:AUTHORED]->(:Commit {sha: 'c1', message: 'retry', ts: $t})-[:CHANGED]->(f)""",
                {"t": now - DAY})
        app.derive(g)
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print(f"PASS  {name}")
                except AssertionError as e:
                    failed += 1
                    print(f"FAIL  {name}: {e}")
    finally:
        g.delete()
    raise SystemExit(failed > 0)
