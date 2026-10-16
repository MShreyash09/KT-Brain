#!/usr/bin/env python3
"""ktbrain: push your Claude Code sessions for one repo to KT Brain. One file, stdlib only.

    python ktbrain.py sync --server http://localhost:8000 --token <CLI token from your KT Brain dashboard> [--repo .]

Reads ~/.claude/projects/*/*.jsonl, keeps only sessions whose working directory is inside --repo, and slims each one
to your prompts, the assistant's text and the files it edited. Secrets are redacted here, on your laptop; the raw
logs never leave it. Add --dry-run to see what would be sent.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SECRETS = [
    r"sk-[A-Za-z0-9_\-]{16,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{30,}",
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["sync"])
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = str(Path(args.repo).resolve())
    found = list(sessions(repo))
    print(f"{len(found)} Claude Code sessions for {repo}")
    for s in found:
        print(f"  {s['started'][:10]}  {s['title'] or s['id']}  ({len(s['files'])} files)")
    if args.dry_run or not found:
        return
    for i in range(0, len(found), 20):  # small batches keep each request well under the upload limit
        req = urllib.request.Request(args.server.rstrip("/") + "/api/cli/sessions",
                                     data=json.dumps({"sessions": found[i:i + 20]}).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {args.token}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                print(f"sent {len(json.load(r)['refs'])}")
        except urllib.error.HTTPError as e:
            sys.exit(f"KT Brain said {e.code}: {e.read().decode(errors='replace')}")


if __name__ == "__main__":
    main()
