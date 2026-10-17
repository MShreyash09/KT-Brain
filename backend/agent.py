"""The KT Brain agent: answers questions from the graph, and watches the radar on its own.

ask()    full-text search, then a walk from the hits to the decisions behind them and who still knows them. The LLM
         writes the answer from that evidence and may only cite ids it was shown: a line with no valid citation is
         dropped and a made-up id is removed (the same rule as extraction's exact-quote check).
watch()  runs every minute for every company, with no human input. Each item that only one person knows gets an
         Alert with a KT brief written from that person's own evidence (what it is, what to ask them before they
         go). The alert closes as 'resolved' once a second person knows the item, or 'lost' if the knower left first.

Without an AI provider both still work: ask() returns the evidence without an answer, watch() alerts without a brief.
"""
import re
import time
from uuid import uuid4

import extract
from graph import (ALERTS, ASK_DECISIONS, ASK_FILES, BRIEF_COMMITS, BRIEF_SOURCES, CLOSE_ALERT, CREATE_ALERT, DECISIONS,
                   ITEM_STATE, LOCK, OPEN_ALERTS, PEOPLE, SEARCH, SEARCH_MINE, SET_BRIEF, radar, rows, text)

CITE = re.compile(r"\[([^\[\]]+)\]")
SOURCE_CHARS = 1500  # of each source's text shown to the model in a brief
BRIEFS_PER_RUN = 10  # model calls per watch run (one a minute), so a first run on a big radar fits free-tier limits

ANSWER_PROMPT = """You answer questions about how a software company works, using ONLY the evidence below, taken from
its knowledge graph. Each piece of evidence starts with its id in square brackets.
- End every sentence or bullet with the ids it relies on, in square brackets, exactly as written: [pr:124] [D8]
- Say who still knows it when the evidence says so, and if a decision was replaced, say by what.
- If the evidence does not answer the question, reply exactly: NOT IN GRAPH
- Under 120 words. No preamble, no headings.

QUESTION: {q}

EVIDENCE:
{evidence}"""

BRIEF_PROMPT = """{name} is the only person at the company who knows {label}. If {first} leaves, it leaves with them.
Using ONLY the evidence below (each piece starts with its id in square brackets), write a short knowledge-transfer
brief as 5 bullets starting with "- ":
- 2 bullets: what this is and why it matters.
- 3 bullets: questions to ask {first} now, which the evidence raises but does not answer.
End every bullet with the ids it relies on, in square brackets, exactly as written: [pr:124]
No preamble, no headings.

EVIDENCE:
{evidence}"""


def search_words(q: str) -> str:
    """Any query word may match (RediSearch OR syntax)."""
    return "|".join(w for w in re.findall(r"[a-z0-9_]+", q.lower()) if len(w) > 2)


def cited(reply: str, ids: set) -> tuple[str, list]:
    """Only the lines of `reply` that cite at least one id in `ids`, with made-up ids removed; plus the ids used."""
    keep, used = [], []

    def swap(m):
        good = [i.strip() for i in re.split(r"[,;]", m.group(1)) if i.strip() in ids]
        found.extend(good)
        return " ".join(f"[{i}]" for i in good)

    for line in reply.splitlines():
        found = []
        line = re.sub(r"\s+([.,;])", r"\1", CITE.sub(swap, line)).rstrip()
        if found:
            keep.append(line)
            used += found
    return "\n".join(keep), list(dict.fromkeys(used))


def evidence_text(blocks: dict) -> str:
    return "\n\n".join(f"[{i}] {b['body']}" for i, b in blocks.items())


def write(llm: dict | None, prompt: str, blocks: dict) -> tuple[str | None, list, str | None]:
    """(answer, cited ids, note): the model's reply cut down to lines it can back up, or why there is none."""
    if not llm:
        return None, [], "No AI provider is set up, so here is the evidence the agent would have used."
    try:
        reply = extract.chat(llm["base"], llm["key"], llm["model"], prompt)
    except Exception as e:  # provider down or out of quota: still show the evidence
        return None, [], f"The AI provider failed ({str(e)[:120]}), so here is the evidence the agent would have used."
    answer, used = cited(reply, set(blocks))
    if not answer:
        return None, [], "The graph has no evidence that answers this."
    return answer, used, None


def ask(g, q: str, llm: dict | None, people: list | None = None, allowed: set | None = None) -> dict:
    """Answer `q` from the graph. `people` limits the search to what a member may read (graph.VISIBLE) and `allowed`
    to the decisions in their view; None for both means an admin, or the public story."""
    words = search_words(q)
    hits = (rows(g, SEARCH, {"q": words}) if people is None else rows(g, SEARCH_MINE, {"q": words, "people": people})
            ) if words else []
    refs = list(dict.fromkeys(h["ref"] for h in hits))
    files = sorted({f for h in hits for f in h["files"]})
    decisions = [d for d in rows(g, ASK_DECISIONS, {"refs": refs, "files": files}) if allowed is None or d["id"] in allowed]

    blocks = {}
    for h in hits:  # a source's matching chunks become one piece of evidence
        b = blocks.setdefault(h["ref"], {"kind": h["kind"], "title": h["title"] or h["text"].split("\n")[0][:80],
                                         "body": f"{h['kind']} \"{h['title'] or ''}\":"})
        b["body"] += "\n" + h["text"]
    for d in decisions:
        body = f"Decision ({d['status']}): {d['what']}. Why: {d['why']}."
        body += f" Still known by: {', '.join(d['knowers'])}." if d["knowers"] else " Nobody still working here knows it."
        if d["superseded_by"]:
            body += f" Replaced by {', '.join(d['superseded_by'])}."
        blocks[d["id"]] = {"kind": "Decision", "title": d["what"], "body": body}
    for f in rows(g, ASK_FILES, {"files": files}):
        who = ", ".join(f["knowers"]) or "nobody still working here"
        blocks[f["path"]] = {"kind": "File", "title": f["path"], "body": f"File. Known by: {who}."}

    if not blocks:
        return {"answer": None, "cited": [], "note": "Nothing in the graph mentions that.", "hits": []}
    answer, used, note = write(llm, ANSWER_PROMPT.format(q=q, evidence=evidence_text(blocks)), blocks)
    return {"answer": answer, "note": note, "hits": hits,
            "cited": [{"id": i, "kind": blocks[i]["kind"], "title": blocks[i]["title"]} for i in used or blocks]}


def brief(g, r: dict, llm: dict | None) -> tuple[str | None, list]:
    """A KT brief for one radar item, from the only knower's own sources and commits; and the ids it cites."""
    person = next(p for p in rows(g, PEOPLE) if p["id"] == r["only_knower"])
    decision = next((d for d in rows(g, DECISIONS) if d["id"] == r["item"]), None)
    p = {"person": person["id"], "item": r["item"]}
    blocks = {}
    if decision:
        blocks[decision["id"]] = {"body": f"Decision: {decision['what']}. Why: {decision['why']}."}
    for s in rows(g, BRIEF_SOURCES, p):
        blocks[s["ref"]] = {"body": f"{s['kind']} \"{s['title'] or ''}\":\n{text(g, s['ref'])[:SOURCE_CHARS]}"}
    for c in rows(g, BRIEF_COMMITS, p):
        blocks[f"commit:{c['sha'][:7]}"] = {"body": f"Commit on {c['at']}: {c['message']}"}
    label = f"{decision['id']} ({decision['what']})" if decision else r["item"]
    if not llm:
        return None, list(blocks)
    prompt = BRIEF_PROMPT.format(name=person["name"], first=person["name"].split()[0], label=label,
                                 evidence=evidence_text(blocks))
    answer, used = cited(extract.chat(llm["base"], llm["key"], llm["model"], prompt), set(blocks))  # raises if it fails
    return answer or None, used or list(blocks)


def watch(g, llm: dict | None) -> int:
    """Open an alert for every new radar item, close the ones that left the radar, then write the briefs still
    missing (new alerts, alerts opened before there was an AI provider, or after it failed). Returns how many it opened."""
    with LOCK:  # never read the radar while derive is halfway through rebuilding KNOWS
        now_on = {r["item"]: r for r in radar(g)}
        now = int(time.time())
        open_ = {item: (aid, done) for aid, item, done in g.ro_query(OPEN_ALERTS, {"since": now - 86400}).result_set}
        for item, (aid, _) in open_.items():
            if item not in now_on:
                state = g.ro_query(ITEM_STATE, {"item": item}).result_set
                lost = bool(state) and state[0][0] and state[0][1] == 0
                g.query(CLOSE_ALERT, {"id": aid, "status": "lost" if lost else "resolved", "now": now})
        new = [r for item, r in now_on.items() if item not in open_]
        fresh = set()
        for r in new:
            aid = uuid4().hex[:12]
            open_[r["item"]] = (aid, False)
            fresh.add(aid)
            g.query(CREATE_ALERT, {"a": {"id": aid, "item": r["item"], "kind": r["kind"], "person": r["only_knower"],
                                         "blast": r["blast"], "status": "open", "created": now}})
    # the model is called outside the lock: it is slow, and derive must not wait for it. Without a provider, only the
    # new alerts get their evidence recorded; the briefs are written once there is one.
    todo = sorted(((aid, now_on[item]) for item, (aid, done) in open_.items()
                   if item in now_on and not done and (llm or aid in fresh)), key=lambda t: -t[1]["blast"])
    for aid, r in todo[:BRIEFS_PER_RUN] if llm else todo:
        try:
            body, refs = brief(g, r, llm)
        except Exception as e:  # provider down or rate-limited (free tiers allow a few calls a minute): next run retries
            print(f"agent: brief for {r['item']} failed, retrying next run: {str(e)[:200]}")
            break
        g.query(SET_BRIEF, {"id": aid, "brief": body, "refs": refs, "tried": int(time.time()) if llm else None})
    return len(new)


def alerts(g, person: str | None = None) -> list:
    out = [r["a"] for r in rows(g, ALERTS)]
    return [a for a in out if a["person"] == person and a["status"] == "open"] if person else out
