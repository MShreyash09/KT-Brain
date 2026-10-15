"""Pull decisions out of a doc or AI session with any OpenAI-compatible chat API.

OpenRouter, Groq, Google AI Studio, Ollama and most other providers speak the same /chat/completions format, so one
setting (base URL, key, model) per company covers all of them. Stdlib only.
"""
import json
import re
import urllib.error
import urllib.request

PRESETS = {
    "openrouter": {"base": "https://openrouter.ai/api/v1", "model": "meta-llama/llama-3.3-70b-instruct:free"},
    "groq": {"base": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "google": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "ollama": {"base": "http://localhost:11434/v1", "model": "llama3.1"},
}

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


def chat(base: str, key: str, model: str, prompt: str) -> str:
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "temperature": 0,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} from {base}: {e.read().decode(errors='replace')[:300]}") from None


def decisions(llm: dict, text: str) -> list:
    """Decisions whose evidence quote really is in the text (anything else is treated as made up and dropped)."""
    text = text[:MAX_CHARS]
    reply = chat(llm["base"], llm["key"], llm["model"], PROMPT + text)
    found = re.search(r"\{.*\}", reply, re.S)
    out = json.loads(found.group(0)).get("decisions", []) if found else []
    flat = " ".join(text.split())
    return [d for d in out if d.get("what") and d.get("evidence") and " ".join(d["evidence"].split()) in flat]
