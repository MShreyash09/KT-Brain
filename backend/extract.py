"""Pull decisions out of a doc or AI session with any OpenAI-compatible chat API.

OpenRouter, Groq, Google AI Studio, Ollama and most other providers speak the same /chat/completions format, so one
setting (base URL, key, model) per company covers all of them. Stdlib only.
"""
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

PRESETS = {
    # providers retire models often: these were checked against their model lists on 2026-10-17
    "openrouter": {"base": "https://openrouter.ai/api/v1", "model": "google/gemma-4-31b-it:free"},
    "groq": {"base": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "google": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "ollama": {"base": "http://localhost:11434/v1", "model": "llama3.1"},
}



def env_llm() -> dict | None:
    """The server's own provider (LLM_KEY, plus LLM_BASE and LLM_MODEL, default Groq), for the public story and any
    company without its own key."""
    key = os.getenv("LLM_KEY")
    return {"base": os.getenv("LLM_BASE", PRESETS["groq"]["base"]), "key": key,
            "model": os.getenv("LLM_MODEL", PRESETS["groq"]["model"])} if key else None


PROMPT = """You read engineering documents and AI coding sessions and list the technical or product DECISIONS in them.
A decision is a choice the team made (a value, a design, a process), not a task or a question.
Return JSON only, no prose: {"decisions": [{"what": "...", "why": "...", "evidence": "...", "about": ["path/to/file"]}]}
- what: the decision in under 15 words.
- why: the reason in under 25 words.
- evidence: a SHORT quote (5-20 words) copied EXACTLY from the text.
- about: file paths from the text this decision applies to (may be empty).
Return {"decisions": []} if there are none.

TEXT:
"""
MAX_CHARS = 15000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):  # a public URL could redirect the request to an internal address
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def check_base(base: str):
    """Any company admin sets this URL, so only public https hosts are allowed: otherwise the server could be pointed at
    its own network (SSRF). ALLOW_LOCAL_LLM=1 lifts this, for local dev with Ollama."""
    u = urlparse(base)
    local = os.getenv("ALLOW_LOCAL_LLM") == "1"
    if u.scheme not in (("http", "https") if local else ("https",)) or not u.hostname:
        raise ValueError("The base URL must be an https:// address")
    if local:
        return
    try:
        addrs = {a[4][0].split("%")[0] for a in socket.getaddrinfo(u.hostname, u.port or 443)}
    except socket.gaierror:
        raise ValueError(f"Can't find the host {u.hostname}") from None
    # ponytail: checked before connecting, so DNS that changes in between (rebinding) slips through; pin the IP if that matters
    if not all(ipaddress.ip_address(a).is_global for a in addrs):
        raise ValueError(f"{u.hostname} is a private address. Set ALLOW_LOCAL_LLM=1 on the server to use a local model")


def complete(llm: dict, messages: list, tools: list | None = None) -> dict:
    """One chat completion: the reply message, with `tool_calls` when the model asked to run tools."""
    check_base(llm["base"])
    body = {"model": llm["model"], "temperature": 0, "messages": messages}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        llm["base"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        # Cloudflare in front of Groq and OpenRouter rejects Python's default User-Agent (403, error code 1010)
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {llm['key']}",
                 "User-Agent": "kt-brain/0.1"})
    try:
        with _open(req, timeout=90) as r:
            return json.load(r)["choices"][0]["message"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} from {llm['base']}: {e.read().decode(errors='replace')[:300]}") from None


def chat(base: str, key: str, model: str, prompt: str) -> str:
    return complete({"base": base, "key": key, "model": model}, [{"role": "user", "content": prompt}])["content"] or ""


def decisions(llm: dict, text: str) -> list:
    """Decisions whose evidence quote really is in the text (anything else is treated as made up and dropped)."""
    text = text[:MAX_CHARS]
    reply = chat(llm["base"], llm["key"], llm["model"], PROMPT + text)
    found = re.search(r"\{.*\}", reply, re.S)
    out = json.loads(found.group(0)).get("decisions", []) if found else []
    flat = " ".join(text.split())
    return [d for d in out if d.get("what") and d.get("evidence") and " ".join(d["evidence"].split()) in flat]
