#!/usr/bin/env python3
"""ktbrain: push your Claude Code sessions for one repo to KT Brain, and let your coding agent ask it. One file,
stdlib only.

    python ktbrain.py sync --server http://localhost:8000 --token <CLI token from your KT Brain dashboard> [--repo .]
    claude mcp add ktbrain -- python ktbrain.py mcp --server http://localhost:8000 --token <CLI token>

mcp serves the KT Brain agent's tools (search, why, who_knows; for admins also if_leaves and radar) over MCP, so
Claude Code can ask why a file is the way it is, or who to ask about it, before it changes the file.

sync reads ~/.claude/projects/*/*.jsonl, keeps only sessions whose working directory is inside --repo, and slims each one
to your prompts, the assistant's text and the files it edited. Secrets are redacted here, on your laptop; the raw
logs never leave it. Add --dry-run to see what would be sent.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

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


def sessions(repo):
    for path in sorted((Path.home() / ".claude" / "projects").glob("*/*.jsonl")):
        lines = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        s = slim(lines, repo)
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
    found = list(sessions(repo))
    print(f"{len(found)} Claude Code sessions for {repo}")
    for s in found:
        print(f"  {s['started'][:10]}  {s['title'] or s['id']}  ({len(s['files'])} files)")
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
    args = ap.parse_args()
    if not args.token:
        ap.error("--token (or KTBRAIN_TOKEN) is required")
    sync(args) if args.command == "sync" else mcp(args)


if __name__ == "__main__":
    main()
