#!/usr/bin/env python3
"""ktbrain: push your AI coding sessions for one repo to KT Brain, and let your coding agent ask it. One file,
stdlib only.

    python ktbrain.py sync --server http://localhost:8000 --token <CLI token from your KT Brain dashboard> [--repo .]
    python ktbrain.py sync ... --path ~/.codex/sessions --tool codex     # any other agent's logs (repeatable)
    claude mcp add ktbrain -- python ktbrain.py mcp --server http://localhost:8000 --token <CLI token>

sync reads, for --repo:
  - Claude Code: ~/.claude/projects/*/*.jsonl (sessions whose working directory is inside --repo)
  - Antigravity: ~/.gemini/antigravity/brain/<id>/ (step log and plans of conversations that touched a file in --repo)
  - anything you pass with --path: JSON, JSONL, Markdown or text logs from any agent, read by a generic reader
    (records with a role and a text field, timestamps, and file paths).

mcp serves the KT Brain agent's tools (search, why, who_knows; for admins also if_leaves and radar) over MCP, so
Claude Code can ask why a file is the way it is, or who to ask about it, before it changes the file.

Each session is slimmed to the prompts, the assistant's text and the repo files it touched. Secrets are redacted here,
on your laptop; the raw logs never leave it. Add --dry-run to see what would be sent.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

SECRETS = [
    r"sk-[A-Za-z0-9_\-]{16,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{30,}",
    r"github_pat_[A-Za-z0-9_]{20,}",  # fine-grained GitHub token
    r"gsk_[A-Za-z0-9]{20,}", r"xox[abpr]-[A-Za-z0-9\-]{10,}", r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}",  # Stripe
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",  # JWT
    r"(?i)(?<=bearer )[A-Za-z0-9._~+/\-]{16,}=*", r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)",  # Bearer header, user:pass@ in URLs
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
]
ASSIGNED_SECRET = r"(?i)((?:password|passwd|secret|token|api_key|apikey)[\"']?\s*[:=]\s*[\"']?)[^\s\"']{6,}"


def redact(text):
    for pattern in SECRETS:
        text = re.sub(pattern, "[redacted]", text)
    return re.sub(ASSIGNED_SECRET, r"\1[redacted]", text)


def norm(path):
    return str(path).replace("\\", "/").rstrip("/").lower()


def slim(lines, repo):
    """The same slimming the server applies to an uploaded .jsonl (backend/ingest/uploads.py)."""
    turns = [l for l in lines if l.get("type") in ("user", "assistant") and isinstance(l.get("message"), dict)]
    if not turns:
        return None
    cwd = (turns[0].get("cwd") or "").replace("\\", "/").rstrip("/")
    if not (norm(cwd) + "/").startswith(norm(repo) + "/"):
        return None
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
                if norm(path).startswith(norm(repo) + "/"):
                    files.add(path[len(repo.rstrip("/\\")) + 1:].replace("\\", "/"))
    return {"id": turns[0]["sessionId"], "title": next((l["aiTitle"] for l in lines if l.get("type") == "ai-title"), ""),
            "branch": turns[0].get("gitBranch"), "started": turns[0]["timestamp"], "ended": turns[-1]["timestamp"],
            "files": sorted(files), "text": redact("\n".join(text))}


def claude(repo):
    for path in sorted((Path.home() / ".claude" / "projects").glob("*/*.jsonl")):
        s = slim(read_log(path), repo)
        if s:
            yield {**s, "tool": "claude-code"}


# ── Any other agent: one generic reader instead of a parser per tool ──────────────────────────────────────────────
# Agents log differently, but the logs share a shape: records with a role-like key and a text field, ISO timestamps,
# and the paths of files the agent touched (tool-call arguments, file:/// links). The server runs the same reader on
# web uploads (backend/ingest/uploads.py, parse_any_log).
ROLE_KEYS = ("role", "type", "source", "author", "speaker", "sender")
TEXT_KEYS = ("content", "text", "message", "prompt", "response", "output")
PATH = re.compile(r"(?:file://)?/?[A-Za-z]:[\\/][^\s\"'<>|*?`)\]]+|(?:file://)?/(?:Users|home|mnt|workspaces?|src|opt)/[^\s\"'<>|*?`)\]]+")
ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?")
LOG_EXT = (".jsonl", ".json", ".md", ".markdown", ".txt", ".log")


def walk(x):
    """Every dict and string inside a JSON value, in order."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)
    elif isinstance(x, str):
        yield x


def read_log(path):
    """A log as JSON records: one per JSONL line, the whole file for JSON, one text record for Markdown or text."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if raw.lstrip().startswith(("{", "[")):
        try:
            return [json.loads(raw)]
        except json.JSONDecodeError:
            records = []
            for line in raw.splitlines():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if records:
                return records
    return [{"type": "log", "content": raw}]


def iso_mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def any_log(records, repo, sid, tool, when, need_repo=True):
    """One session from any agent's records. None when it holds no text, or (need_repo) never touches a file in repo,
    so personal chats in the same tool are never sent."""
    root = norm(repo) + "/"
    text, files, times, touched = [], set(), [], False
    for x in walk(records):
        if isinstance(x, dict):
            role = next((x[k] for k in ROLE_KEYS if isinstance(x.get(k), str)), None)
            body = next((x[k] for k in TEXT_KEYS if isinstance(x.get(k), str) and x[k].strip()), None)
            if role and body:
                text.append(f"{role.lower()}: {body.strip()}")
            continue
        if ISO.fullmatch(x):
            times.append(x)
        for p in PATH.findall(x):
            p = re.sub(r"\\+", "/", unquote(p.removeprefix("file://"))).rstrip(".,;:")
            p = p[1:] if re.match(r"/[A-Za-z]:/", p) else p
            if norm(p).startswith(root):
                touched = True
                if "." in p.rsplit("/", 1)[-1]:  # a file, not a folder
                    files.add(p[len(root):])
    if not text or (need_repo and not touched):
        return None
    first = next((t.split(": ", 1)[1] for t in text if "user" in t.split(": ", 1)[0]), text[0].split(": ", 1)[-1])
    title = re.sub(r"<[^>]+>|^\s*(?:#+|[-*](?:\s*\[.\])?)\s*", "", first).strip().split("\n")[0][:100]
    return {"id": f"{tool}:{sid}", "tool": tool, "title": title, "branch": None, "started": min(times, default=when),
            "ended": max(times, default=when), "files": sorted(files), "text": redact("\n".join(text))}


def antigravity(repo):
    """Antigravity keeps each conversation's step log and its plans in ~/.gemini/antigravity/brain/<id>/. The full
    conversation (conversations/<id>.pb) is binary, so only these readable parts are used."""
    for d in sorted(p for p in (Path.home() / ".gemini" / "antigravity" / "brain").glob("*") if p.is_dir()):
        log = d / ".system_generated" / "logs" / "overview.txt"
        records = read_log(log) if log.is_file() else []
        records += [{"type": "plan", "content": (d / md).read_text(encoding="utf-8", errors="replace")}
                    for md in ("task.md", "implementation_plan.md", "walkthrough.md") if (d / md).is_file()]
        s = any_log(records, repo, d.name, "antigravity", iso_mtime(d))
        if s:
            yield s


def given(paths, repo, tool):
    """Logs of any other agent, from files or folders you name: you picked them, so they're sent without the repo check."""
    for p in map(Path, paths):
        logs = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.suffix.lower() in LOG_EXT)
        for f in logs:
            sid = f"{f.stem}-{hashlib.sha1(str(f.resolve()).encode()).hexdigest()[:8]}"
            s = any_log(read_log(f), repo, sid, tool, iso_mtime(f), need_repo=False)
            if s:
                yield s


def api(args, path, body=None):
    req = urllib.request.Request(args.server.rstrip("/") + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {args.token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"KT Brain said {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def sync(args):
    repo = str(Path(args.repo).resolve())
    found = list(claude(repo)) + list(antigravity(repo)) + list(given(args.path, repo, args.tool))
    counts = {}
    for s in found:
        counts[s["tool"]] = counts.get(s["tool"], 0) + 1
    print(f"{len(found)} sessions for {repo}: " + (", ".join(f"{n} {t}" for t, n in counts.items()) or "none"))
    for s in found:
        print(f"  {s['started'][:10]}  [{s['tool']}] {s['title'] or s['id']}  ({len(s['files'])} files)")
    if args.dry_run or not found:
        return
    for i in range(0, len(found), 20):  # small batches keep each request well under the upload limit
        try:
            print(f"sent {len(api(args, '/api/cli/sessions', {'sessions': found[i:i + 20]})['refs'])}")
        except RuntimeError as e:
            sys.exit(str(e))


def mcp(args):
    """An MCP server on stdin/stdout (JSON-RPC, one message per line). The coding agent picks the tools and does the
    reasoning; the server runs them on your graph, with the same view you have on the Ask page."""
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") is None:  # a notification, such as notifications/initialized: no reply
            continue
        method, params, reply = msg.get("method"), msg.get("params") or {}, {"jsonrpc": "2.0", "id": msg["id"]}
        try:
            if method == "initialize":
                reply["result"] = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                                   "capabilities": {"tools": {}}, "serverInfo": {"name": "ktbrain", "version": "0.1"}}
            elif method == "tools/list":
                reply["result"] = {"tools": [{"name": t["function"]["name"], "description": t["function"]["description"],
                                              "inputSchema": t["function"]["parameters"]} for t in api(args, "/api/cli/tools")]}
            elif method == "tools/call":
                out = api(args, "/api/cli/tool", {"name": params.get("name"), "args": params.get("arguments") or {}})
                reply["result"] = {"content": [{"type": "text", "text": out["text"]}], "isError": out["error"]}
            elif method == "ping":
                reply["result"] = {}
            else:
                reply["error"] = {"code": -32601, "message": f"Unknown method {method}"}
        except (RuntimeError, OSError) as e:  # KT Brain refused, or is unreachable
            reply["error"] = {"code": -32000, "message": str(e)}
        print(json.dumps(reply), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sync", "mcp"])
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--token", default=os.getenv("KTBRAIN_TOKEN"), help="or set KTBRAIN_TOKEN")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", action="append", default=[],
                    help="a log file or folder from any other coding agent (repeatable); sent as you name it")
    ap.add_argument("--tool", default="ai-agent", help="label for the --path logs, e.g. codex, cursor, opencode")
    args = ap.parse_args()
    if not args.token:
        ap.error("--token (or KTBRAIN_TOKEN) is required")
    sync(args) if args.command == "sync" else mcp(args)


if __name__ == "__main__":
    main()
