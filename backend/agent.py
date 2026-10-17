"""The KT Brain agent: answers questions from the graph, and watches the radar on its own.

ask()    a tool-calling loop. The model never writes Cypher: it picks tools from a fixed catalogue (TOOLS) of queries we
         wrote, and every name it passes is resolved against the graph first, so an unknown or misspelt name is reported
         instead of reasoned about. Each piece of evidence a tool returns carries its id and the graph path it came by.
         The answer may only cite ids it was shown: a line with no valid citation is dropped and a made-up id is
         removed (the same rule as extraction's exact-quote check).
call()   one tool on its own, for a coding agent over MCP (cli/ktbrain.py mcp), which does its own reasoning.
watch()  runs every minute for every company, with no human input. Each item that only one person knows gets an
         Alert with a KT brief written from that person's own evidence (what it is, what to ask them before they
         go). The alert closes as 'resolved' once a second person knows the item, or 'lost' if the knower left first.

Without an AI provider both still work: ask() returns what a search finds, watch() alerts without a brief.
"""
import difflib
import json
import re
import time
from uuid import uuid4

import extract
from graph import (ALERTS, ASK_DECISIONS, ASK_FILES, BRIEF_COMMITS, BRIEF_SOURCES, CLOSE_ALERT, CREATE_ALERT, DECISIONS,
                   FILE_COMMITS, FILE_DECISIONS, ITEM_KNOWERS, ITEM_STATE, ITEMS, LOCK, OPEN_ALERTS, PEOPLE, SEARCH,
                   SEARCH_MINE, SET_BRIEF, dry_run, radar, rows, text, trace)

CITE = re.compile(r"\[([^\[\]]+)\]")
SOURCE_CHARS = 1500  # of each source's text shown to the model in a brief
CHUNK_CHARS = 1200  # of each search hit: the evidence is sent again every round, and free tiers cap tokens a minute
BRIEFS_PER_RUN = 10  # model calls per watch run (one a minute), so a first run on a big radar fits free-tier limits
MAX_ROUNDS = 4  # model calls that may run tools, per question; one more call then has to answer
MAX_CALLS = 8  # tool calls per question

# name: (what it does, for the model; its arguments). ADMIN_TOOLS are company-wide views: admins and the public story.
TOOLS = {
    "search": ("Full-text search over the company's docs, PRs, tickets, chat threads and AI sessions, plus the decisions "
               "those sources record and who still knows them. Start here for how and why questions.",
               {"query": "the words to search for"}),
    "why": ("Everything behind one decision or file. For a decision (an id like D1): the sources that record it, the "
            "decision it replaced and the incidents that one caused, and the research behind it. For a file (a path like "
            "api/payments/retry.py): the decisions about it and its latest commits.",
            {"item": "a decision id or a file path"}),
    "who_knows": ("Who knows a decision or file, how strongly (a score from their work on it that halves every year) and "
                  "when they last touched it, who learned it in a KT session, and who knew it but has left.",
                  {"item": "a decision id or a file path"}),
    "if_leaves": ("What the company loses if these people leave: what nobody else would know (their KT agenda), what is "
                  "only lost if they leave together, and what is left with a weak backup. Runs on a copy of the graph.",
                  {"people": "names or ids, comma separated"}),
    "radar": ("Everything only one person knows, biggest blast radius first (PageRank of its service over DEPENDS_ON).",
              {}),
}
ADMIN_TOOLS = {"if_leaves", "radar"}

SYSTEM = """You answer questions about how a software company works, from its knowledge graph. You only see the graph
through the tools: call them until the evidence answers the question, then answer. Never guess.
- How or why something works: search, then why or who_knows on the decision ids and file paths the evidence names.
- Who knows something, or who to ask: who_knows.{admin}
- Each piece of evidence starts with its id in square brackets. End every sentence or bullet of your answer with the
  ids it relies on, exactly as written: [pr:124] [D8]
- Say who still knows it when the evidence says so, and if a decision was replaced, say by what.
- If a tool says a name is unknown, do not guess another name: reply NOT IN GRAPH.
- Evidence that only shares a word with the question (payment retries, for a question about refunds) does not answer it.
- If the evidence answers part of the question, answer that part, then end with a line: NOT IN GRAPH: <the part it does
  not answer>. If it answers none of it, reply only: NOT IN GRAPH: <what was asked, in a few words>
- Under 150 words. No preamble, no headings."""
ADMIN_HINT = "\n- What happens if someone leaves: if_leaves. Where the company is most at risk: radar."

# For providers without tool calls only: one search, one answer.
ANSWER_PROMPT = """You answer questions about how a software company works, using ONLY the evidence below, taken from
its knowledge graph. Each piece of evidence starts with its id in square brackets.
- End every sentence or bullet with the ids it relies on, in square brackets, exactly as written: [pr:124] [D8]
- Say who still knows it when the evidence says so, and if a decision was replaced, say by what.
- Evidence that only shares a word with the question (payment retries, for a question about refunds) does not answer it.
- If the evidence answers part of the question, answer that part, then end with a line: NOT IN GRAPH: <the part it does
  not answer>. If it answers none of it, reply only: NOT IN GRAPH: <what was asked, in a few words>
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
        good = [i.split("†")[0].strip() for i in re.split(r"[,;]", m.group(1)) if i.split("†")[0].strip() in ids]
        found.extend(good)
        return " ".join(f"[{i}]" for i in good)

    # gpt-oss sometimes cites in its native style, 【D1】 or 【D1†L3】
    for line in reply.translate(str.maketrans("【】［］", "[][]")).splitlines():
        found = []
        line = re.sub(r"\s+([.,;])(?=\s|$)", r"\1", CITE.sub(swap, line)).rstrip()  # "it [x]." with x dropped, not ".github"
        if found:
            keep.append(line)
            used += found
    return "\n".join(keep), list(dict.fromkeys(used))


def evidence_text(blocks: dict) -> str:
    return "\n\n".join(f"[{i}] {b['body']}" + "".join(f"\n  via {p}" for p in b.get("paths", [])[:2])
                       for i, b in blocks.items())


# ── Tools ────────────────────────────────────────────────────────────────────
# A run is one question: the graph, what the asker may see (people: None for an admin; allowed: the decision ids and
# file paths in a member's view), and the evidence found so far, id -> {kind, title, body, paths}.
def new_run(g, people: list | None, allowed: set | None) -> dict:
    return {"g": g, "people": people, "allowed": allowed, "blocks": {}, "steps": [], "hits": [], "new": []}


def add(run, bid: str, kind: str, title: str, body: str, path: str | None = None):
    """Add evidence, or more of it to a piece already found (the same decision reached by two tools)."""
    b = run["blocks"].setdefault(bid, {"kind": kind, "title": title, "body": "", "paths": []})
    if body and body not in b["body"]:
        b["body"] = f"{b['body']}\n{body}".strip()
    if path and path not in b["paths"]:
        b["paths"].append(path)
    if bid not in run["new"]:
        run["new"].append(bid)


def day(ts) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else "unknown"


def decision_body(d: dict) -> str:
    body = f"Decision ({d['status']}): {d['what'].rstrip('.')}. Why: {(d['why'] or '').rstrip('.')}."
    if "knowers" in d:
        body += f" Still known by: {', '.join(d['knowers'])}." if d["knowers"] else " Nobody still working here knows it."
    if d.get("superseded_by"):
        body += f" Replaced by {', '.join(d['superseded_by'])}."
    return body


def resolve(run, name: str) -> tuple[str | None, str | None]:
    """(the decision id or file path `name` means, None), or (None, why it can't be resolved). A bare file name is
    enough when only one path ends with it, and a near miss gets suggestions."""
    items = [i for (i,) in run["g"].ro_query(ITEMS).result_set if run["allowed"] is None or i in run["allowed"]]
    n = name.strip().strip("`'\"").lower()
    exact = [i for i in items if i.lower() == n]
    tail = exact or [i for i in items if i.lower().endswith("/" + n)]
    if len(tail) == 1:
        return tail[0], None
    if tail:
        return None, f"'{name}' could be {', '.join(tail[:5])}: call again with the full path."
    names = {i.lower(): i for i in items} | {i.rsplit("/", 1)[-1].lower(): i for i in items}
    close = list(dict.fromkeys(names[c] for c in difflib.get_close_matches(n, names, 3, 0.6)))
    return None, f"Unknown item '{name}': no decision or file in the graph has that name." + (
        f" Did you mean {', '.join(close)}?" if close else "")


def resolve_people(run, names: str) -> tuple[list, str | None]:
    """Person ids for a list of names, ids, first names, emails or GitHub logins, or why one can't be resolved."""
    keys = {}
    for p in rows(run["g"], PEOPLE):
        for k in (p["id"], p["name"], (p["name"] or "").split(" ")[0], p["email"], p["github"]):
            if k:
                keys.setdefault(k.lower(), set()).add(p["id"])
    ids = []
    for n in filter(None, (x.strip().lower() for x in re.split(r",|;|\band\b", names))):
        found = keys.get(n, set())
        if len(found) > 1:
            return [], f"'{n}' could be {', '.join(sorted(found))}: call again with one of these ids."
        if not found:
            close = difflib.get_close_matches(n, keys, 3, 0.6)
            return [], f"Unknown person '{n}'." + (f" Did you mean {', '.join(close)}?" if close else "")
        ids += found
    return list(dict.fromkeys(ids)), None if ids else "Name at least one person."


def t_search(run, query: str):
    words = search_words(query)
    if not words:
        return "Nothing to search for: use words of 3 letters or more."
    g, people, allowed = run["g"], run["people"], run["allowed"]
    hits = rows(g, SEARCH, {"q": words}) if people is None else rows(g, SEARCH_MINE, {"q": words, "people": people})
    run["hits"] += hits
    refs = list(dict.fromkeys(h["ref"] for h in hits))
    mentioned_in = {f: h["ref"] for h in hits for f in h["files"]}
    for h in hits:  # a source's matching chunks become one piece of evidence
        title = h["title"] or h["text"].split("\n")[0][:80]
        add(run, h["ref"], h["kind"], title, f"{h['kind']} \"{title}\":", f"(chunk {h['seq'] + 1})-[:PART_OF]->({h['ref']})")
        add(run, h["ref"], h["kind"], title, h["text"][:CHUNK_CHARS])
    for d in rows(g, ASK_DECISIONS, {"refs": refs, "files": sorted(mentioned_in)}):
        if allowed is not None and d["id"] not in allowed:
            continue
        paths = [f"({r})-[:RECORDS]->({d['id']})" for r in d["recorded_in"] if r in refs] or [
            f"({mentioned_in[f]})-[:MENTIONS]->({f})<-[:ABOUT]-({d['id']})" for f in d["about"] if f in mentioned_in]
        for p in paths[:2] or [None]:
            add(run, d["id"], "Decision", d["what"], decision_body(d), p)
    for f in rows(g, ASK_FILES, {"files": sorted(mentioned_in)}):
        who = ", ".join(f["knowers"]) or "nobody still working here"
        add(run, f["path"], "File", f["path"], f"File. Known by: {who}.",
            f"({mentioned_in[f['path']]})-[:MENTIONS]->({f['path']})")


def t_why(run, item: str):
    item, err = resolve(run, item)
    if err:
        return err
    g, allowed = run["g"], run["allowed"]
    decisions = {d["id"]: d for d in rows(g, DECISIONS)}
    if item not in decisions:  # a file
        for d in rows(g, FILE_DECISIONS, {"path": item}):
            if allowed is None or d["id"] in allowed:
                add(run, d["id"], "Decision", d["what"], decision_body(d), f"({d['id']})-[:ABOUT]->({item})")
        for c in rows(g, FILE_COMMITS, {"path": item}):
            cid = f"commit:{c['sha'][:7]}"
            add(run, cid, "Commit", c["message"],
                f"Commit by {c['author']} on {c['at']}{' in ' + c['pr'] if c['pr'] else ''}: {c['message']}",
                f"({c['author']})-[:AUTHORED]->({cid})-[:CHANGED]->({item})")
        return None if run["new"] else f"{item} is in the graph, but no decision is about it and no commit changed it."
    d, t = decisions[item], trace(g, item)
    body = decision_body(d) + (f" Quote: \"{d['evidence']}\"" if d.get("evidence") else "")
    if t["patterns"]:
        body += f" Applies: {', '.join(t['patterns'])}."
    add(run, item, "Decision", d["what"], body)
    for s in t["sources"]:
        add(run, s["ref"], s["kind"], s["title"],
            f"{s['kind']} \"{s['title']}\" ({s['at']}), with {', '.join(s['people']) or 'nobody on record'}. It records {item}.",
            f"({s['ref']})-[:RECORDS]->({item})")
    for o in t["supersedes"]:
        body = f"Decision (replaced by {item}): {o['what']}."
        for i in o["incidents"]:
            body += f" Incident {i['id']} \"{i['title']}\" ({i['at']}, {i['severity']}) was caused by it."
        add(run, o["id"], "Decision", o["what"], body, f"({item})-[:SUPERSEDES]->({o['id']})")
    for r in t["research"]:
        cites = "; ".join(f"{c['title']} ({c['publisher']}, {c['date']})" for c in r["cites"])
        add(run, r["id"], "Research", r["title"], f"Research \"{r['title']}\" in {r['doc']}" + (
            f", citing {cites}." if cites else "."), f"({item})-[:INFORMED_BY]->({r['id']})")
    for i in t["insights"]:
        add(run, i["id"], "Insight", i["text"][:80], f"Insight from \"{i['research']}\": {i['text']}",
            f"({i['id']})-[:JUSTIFIES]->({item})")


def t_who_knows(run, item: str):
    item, err = resolve(run, item)
    if err:
        return err
    g = run["g"]
    decision = next((d for d in rows(g, DECISIONS) if d["id"] == item), None)
    kind, title = ("Decision", decision["what"]) if decision else ("File", item)
    who, paths = [], []
    for r in rows(g, ITEM_KNOWERS, {"item": item}):
        if r["how"] == "LEARNED":
            who.append(f"{r['name']} learned it in a KT session" + (f" from {r['taught_by']}" if r["taught_by"] else ""))
        else:
            who.append(f"{r['name']} (score {r['score']:.1f} from {r['links']} links, last touched {day(r['last'])})"
                       + ("" if r["active"] else ", has left the company"))
        paths.append(f"({r['name']})-[:{r['how']}]->({item})")
    body = ("Known by: " + "; ".join(who) + ".") if who else "Nobody knows it: nobody has worked on it recently enough."
    add(run, item, kind, title, (f"Decision: {title}. " if decision else "File. ") + body)
    for p in paths[:3]:
        add(run, item, kind, title, "", p)


def t_if_leaves(run, people: str):
    ids, err = resolve_people(run, people)
    if err:
        return err
    names = {p["id"]: p["name"] for p in rows(run["g"], PEOPLE)}
    what = {d["id"]: d["what"] for d in rows(run["g"], DECISIONS)}
    label = lambda i: f"{i} ({what[i]})" if i in what else i  # noqa: E731
    out = dry_run(run["g"].name, ids)
    who = " and ".join(names[i] for i in ids)
    body = (f"Dry run on a copy of the graph with {who} gone. Nobody else would know {len(out['agenda'])} items: "
            f"{'; '.join(map(label, out['agenda'])) or 'none'}.")
    if out["combination_risk"]:
        body += (" Of those, these are only lost because they leave together (two or more of them know each): "
                 f"{'; '.join(map(label, out['combination_risk']))}.")
    if out["weak_backup"]:
        body += (" Not in that count, but left with a weak backup (someone who changed it once in code and took no "
                 "part in the discussion): ") + "; ".join(
            f"{label(i)} by {names.get(b, b)}" for i, b in out["weak_backup"].items()) + "."
    add(run, "if_leaves:" + "+".join(ids), "DryRun", f"If {who} {'leave' if len(ids) > 1 else 'leaves'}", body,
        f"({who})-[:KNOWS]->({len(out['agenda'])} items no one else KNOWS)")


def t_radar(run):
    names = {p["id"]: p["name"] for p in rows(run["g"], PEOPLE)}
    what = {d["id"]: d["what"] for d in rows(run["g"], DECISIONS)}
    items = sorted(radar(run["g"]), key=lambda r: (-r["blast"], -r["score"]))
    top = "; ".join(f"{r['item']}{' (' + what[r['item']] + ')' if r['item'] in what else ''}: only "
                    f"{names[r['only_knower']]} knows it, blast radius {r['blast']}" for r in items[:12])
    add(run, "radar", "Radar", "Bus-factor radar",
        f"{len(items)} items only one person knows. Biggest blast radius first: {top or 'none'}.",
        "CALL algo.pageRank('Service', 'DEPENDS_ON')")


FUNCS = {"search": t_search, "why": t_why, "who_knows": t_who_knows, "if_leaves": t_if_leaves, "radar": t_radar}


def specs(admin: bool) -> list:
    """The catalogue in the OpenAI tools format."""
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": {
        "type": "object", "properties": {k: {"type": "string", "description": v} for k, v in args.items()},
        "required": list(args)}}} for n, (d, args) in TOOLS.items() if admin or n not in ADMIN_TOOLS]


def tool(run, name: str, args) -> str:
    """Run one tool and record it as a step. Returns what it found as text for the model: the evidence it added, or
    why it found nothing. `args` comes from the model (a JSON string), so only the tool's own arguments are kept."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            args = {}
    params = TOOLS[name][1] if name in TOOLS else {}
    args = {k: str((args if isinstance(args, dict) else {}).get(k) or "")[:200] for k in params}
    run["new"] = []
    if name not in FUNCS or (name in ADMIN_TOOLS and run["people"] is not None):
        err = f"There is no tool called {name}."
    elif len(run["steps"]) >= MAX_CALLS:
        err = "No more tool calls: answer from the evidence you have."
    else:
        err = FUNCS[name](run, **args)
    run["steps"].append({"tool": name, "args": args, "found": list(run["new"]), "error": err})
    return err or evidence_text({i: run["blocks"][i] for i in run["new"]}) or \
        "Nothing in the graph matches: it may not be recorded yet."


def think(run, q: str, llm: dict) -> str:
    """The tool-calling loop: the model's final reply, once it stops calling tools (or runs out of rounds)."""
    admin = run["people"] is None
    msgs = [{"role": "system", "content": SYSTEM.format(admin=ADMIN_HINT if admin else "")},
            {"role": "user", "content": q}]
    for _ in range(MAX_ROUNDS):
        m = extract.complete(llm, msgs, specs(admin))
        if not m.get("tool_calls"):
            return m.get("content") or ""
        msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": m["tool_calls"]})
        for c in m["tool_calls"]:
            msgs.append({"role": "tool", "tool_call_id": c["id"],
                         "content": tool(run, c["function"]["name"], c["function"].get("arguments"))})
    msgs.append({"role": "user", "content": "Answer now, from the evidence above."})
    return extract.complete(llm, msgs)["content"] or ""


def failed(e: Exception) -> str:
    return f"The AI provider failed ({str(e)[:120]}), so here is the evidence the agent found."


def refuse(run, gap: str, errors: list) -> str:
    """A soft refusal: what the graph lacks, and why that may be, instead of an answer made up around it."""
    if errors:  # a name the graph does not have, with suggestions
        return " ".join(dict.fromkeys(errors))
    note = f"The graph has nothing on {gap}." if gap else "The graph has nothing that answers this."
    if run["blocks"]:
        note += " The closest evidence it found is below: it shares words with the question but does not answer it."
    return note + " It may not be written down anywhere KT Brain reads yet" + (
        ", or it is outside what you can see." if run["people"] is not None else ".")


def ask(g, q: str, llm: dict | None, people: list | None = None, allowed: set | None = None) -> dict:
    """Answer `q` from the graph. `people` limits what a member may read (graph.VISIBLE) and `allowed` the decisions
    and files in their view; None for both means an admin, or the public story."""
    run, reply, note = new_run(g, people, allowed), None, None
    if not llm:
        note = "No AI provider is set up, so here is what a search of the graph finds."
    else:
        try:
            reply = think(run, q, llm)
        except Exception as e:  # down or out of quota; a 400 before any tool ran usually means no tool calls
            note = failed(e)
            if not run["steps"] and str(e)[:3] in ("400", "422"):  # so: one search, one answer
                tool(run, "search", {"query": q})
                try:
                    reply = extract.chat(llm["base"], llm["key"], llm["model"],
                                         ANSWER_PROMPT.format(q=q, evidence=evidence_text(run["blocks"])))
                except Exception as e2:
                    note = failed(e2)
    if not run["steps"]:
        tool(run, "search", {"query": q})
    blocks = run["blocks"]
    said = [l.strip() for l in (reply or "").splitlines() if l.strip()]
    missing = [l for l in said if l.upper().startswith("NOT IN GRAPH")]
    gap = "; ".join(filter(None, (l[12:].strip(" :.") for l in missing)))[:150]  # ponytail: the model's words, capped
    answer, used = cited("\n".join(l for l in said if l not in missing), set(blocks))
    errors = [s["error"] for s in run["steps"] if s["error"]]
    if answer:  # what the graph answers, and a word on what it left out
        dropped = len(said) - len(missing) - len(answer.splitlines())
        note = " ".join(filter(None, [
            gap and f"Not in the graph: {gap}.",
            dropped and f"Left out {dropped} sentence{'s' if dropped > 1 else ''} that cited nothing in the graph."])) or None
    elif reply is not None:
        note = refuse(run, gap, errors)
    elif not blocks:
        note = "Nothing in the graph mentions that."
    return {"answer": answer or None, "note": note, "hits": run["hits"], "steps": run["steps"],
            "cited": [{"id": i, "kind": blocks[i]["kind"], "title": blocks[i]["title"], "paths": blocks[i]["paths"]}
                      for i in used or blocks]}


def call(g, name: str, args: dict, people: list | None = None, allowed: set | None = None) -> dict:
    """One tool on its own (the MCP server): the evidence as text, and whether it failed."""
    run = new_run(g, people, allowed)
    out = tool(run, name, args)
    return {"text": out, "error": bool(run["steps"][-1]["error"])}


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
