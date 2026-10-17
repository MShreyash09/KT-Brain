"""The agent without a real AI provider: canned model replies go through the same citation check, and the radar watch
runs on a real graph built from the TiffinBox fixtures.

Run from backend/:  uv run python test_agent.py   (needs FalkorDB; builds, then deletes, graph _test_agent)
"""
import json

import agent
import extract
from graph import radar
from ingest.fixtures import build

LLM = {"base": "", "key": "", "model": ""}
reply = {"text": ""}
extract.chat = lambda *a: reply["text"]


def model(*turns):
    """A fake provider for ask(): each turn is a list of (tool, args) calls, or the final reply text."""
    script = list(turns)

    def complete(llm, msgs, tools=None):
        turn = script.pop(0)
        if isinstance(turn, str):
            return {"content": turn}
        assert tools, "tools are offered while the model may still call them"
        return {"content": None, "tool_calls": [{"id": f"c{i}", "function": {"name": n, "arguments": json.dumps(a)}}
                                                for i, (n, a) in enumerate(turn)]}
    extract.complete = complete


# a line keeps only real ids, a line with none is dropped, "[a, b]" lists are split
text, used = agent.cited("Retries are 7 [D1, D99].\nNo source for this.\nPR 124 set it [pr:124]", {"D1", "pr:124"})
assert text == "Retries are 7 [D1].\nPR 124 set it [pr:124]", text
assert used == ["D1", "pr:124"], used
assert agent.cited("Seven retries【D1】. Paths stay .github/ci.yml【D1†L3】.", {"D1"})[0] == \
    "Seven retries[D1]. Paths stay .github/ci.yml[D1]."

NAME = "_test_agent"
g = build(NAME, "2026-09-21")
try:
    # ask: search, then who_knows on a bare file name, which resolves to its full path; the made-up id is dropped
    model([("search", {"query": "payment retries"})], [("who_knows", {"item": "retry.py"})],
          "Payments retry 7 times [D1]. Arjun knows the code [api/payments/retry.py] [made-up:1].\nIt was always 7.")
    out = agent.ask(g, "why do payment retries happen 7 times", LLM)
    assert out["answer"] == "Payments retry 7 times [D1]. Arjun knows the code [api/payments/retry.py].", out["answer"]
    assert [s["tool"] for s in out["steps"]] == ["search", "who_knows"], out["steps"]
    cite = {c["id"]: c for c in out["cited"]}
    assert list(cite) == ["D1", "api/payments/retry.py"], cite
    assert any("-[:RECORDS]->(D1)" in p for p in cite["D1"]["paths"]), cite["D1"]  # the hop it was found by
    assert any(p.startswith("(Arjun") and "-[:KNOWS]->" in p for p in cite["api/payments/retry.py"]["paths"])

    # names are resolved against the graph first: a misspelt one runs no query and gets suggestions
    run = agent.new_run(g, None, None)
    assert "Did you mean api/payments/retry.py" in agent.tool(run, "who_knows", '{"item": "retyr.py"}')
    assert agent.tool(run, "why", {"item": "D1"}).startswith("[D1] Decision (active)")
    assert "(D1)-[:SUPERSEDES]->(D13)" in run["blocks"]["D13"]["paths"]
    assert "Unknown person 'arjn'. Did you mean arjun" in agent.tool(run, "if_leaves", {"people": "Arjn"})
    leaving = agent.tool(run, "if_leaves", {"people": "Arjun"})
    assert leaving.startswith("[if_leaves:arjun]") and "D1 (" in leaving, leaving

    # a member gets no company-wide tools, and nothing outside their view resolves
    member = agent.new_run(g, ["kavya"], {"ci.yml"})
    assert "if_leaves" not in {t["function"]["name"] for t in agent.specs(False)}
    assert agent.tool(member, "radar", {}) == "There is no tool called radar."
    assert agent.tool(member, "why", {"item": "D1"}).startswith("Unknown item")

    # the model answers about a name the graph does not have: the note says so
    model([("who_knows", {"item": "billing.go"})], "NOT IN GRAPH")
    out = agent.ask(g, "who knows billing.go", LLM)
    assert out["answer"] is None and out["note"].startswith("Unknown item 'billing.go'"), out

    # part answered: the graph's part stays, the made-up sentence goes, and the note says what is missing
    model([("search", {"query": "payment retries refunds"})],
          "Payments retry 7 times [D1].\nRefunds take 3 days.\nNOT IN GRAPH: how refunds work")
    out = agent.ask(g, "why 7 retries, and how do refunds work", LLM)
    assert out["answer"] == "Payments retry 7 times [D1].", out["answer"]
    assert out["note"] == "Not in the graph: how refunds work. Left out 1 sentence that cited nothing in the graph.", out

    # nothing answers it: a soft refusal that says why, with the closest evidence below it; a member is told it may
    # be outside their view
    model([("search", {"query": "payment refunds"})], "NOT IN GRAPH: how refunds work")
    out = agent.ask(g, "how do refunds work", LLM)
    assert out["answer"] is None and out["cited"], out
    assert out["note"].startswith("The graph has nothing on how refunds work. The closest evidence"), out["note"]
    model([("search", {"query": "kubernetes"})], "NOT IN GRAPH")
    out = agent.ask(g, "how do we run kubernetes", LLM, ["kavya"], {"ci.yml"})
    assert out["note"].endswith("or it is outside what you can see."), out["note"]

    # a free tier's rate limit reads as busy, not as a crash; other failures keep their reason
    assert agent.failed(RuntimeError("429 from https://api.groq.com: rate limit")) == agent.BUSY
    assert agent.failed(RuntimeError("500 from x")).startswith("The AI provider failed (500")

    # no provider: no answer, but what a search finds
    out = agent.ask(g, "payment retries", None)
    assert out["answer"] is None and "D1" in [c["id"] for c in out["cited"]], out

    # watch: one alert per radar item, with a brief that only cites the knower's evidence; nothing new the second time
    reply["text"] = "- Retries cover the gateway pause [D1] [pr:124]\n- Ask Arjun about the cap [nope]"
    items = {r["item"] for r in radar(g)}
    assert agent.watch(g, None) == len(items) == 12  # no provider: alerts with evidence, no brief
    d1 = next(a for a in agent.alerts(g) if a["item"] == "D1")
    assert "brief" not in d1 and "pr:124" in d1["refs"] and d1["person"] == "arjun", d1
    def rate_limited(*a):
        raise RuntimeError("429 rate limit")
    extract.chat = rate_limited
    agent.watch(g, LLM)  # the provider fails: nothing is marked as tried, so the next run retries at once
    assert not any("tried" in a for a in agent.alerts(g))
    extract.chat = lambda *a: reply["text"]
    assert agent.watch(g, LLM) == 0  # a provider now: nothing new, but the missing briefs get written
    d1 = next(a for a in agent.alerts(g) if a["item"] == "D1")
    assert d1["brief"] == "- Retries cover the gateway pause [D1] [pr:124]", d1
    # capped per run, the rest next run; a reply that cites none of an item's evidence leaves no brief, and is not
    # asked again for a day
    assert sum("tried" in a for a in agent.alerts(g)) == agent.BRIEFS_PER_RUN
    agent.watch(g, LLM)
    assert sum("tried" in a for a in agent.alerts(g)) == 12
    reply["text"] = "should not be asked"
    agent.watch(g, LLM)
    assert not any(a.get("brief") == reply["text"] for a in agent.alerts(g))

    # Arjun leaves: his only-knower items are lost, and items he shared with Priya become hers alone (new alerts)
    g.query("MATCH (p:Person {id: 'arjun'}) SET p.active = false")
    opened = agent.watch(g, None)
    states = {a["item"]: a["status"] for a in agent.alerts(g) if a["person"] == "arjun"}
    assert states["D1"] == "lost" and states["api/payments/retry.py"] == "lost", states
    assert opened > 0 and any(a["item"] == "D8" and a["person"] == "priya" and a["status"] == "open"
                              for a in agent.alerts(g)), "D8 should now be Priya's alone"
    print("PASS  test_agent")
finally:
    g.delete()
