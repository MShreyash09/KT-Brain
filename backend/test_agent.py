"""The agent without a real AI provider: canned model replies go through the same citation check, and the radar watch
runs on a real graph built from the TiffinBox fixtures.

Run from backend/:  uv run python test_agent.py   (needs FalkorDB; builds, then deletes, graph _test_agent)
"""
import agent
import extract
from graph import radar
from ingest.fixtures import build

LLM = {"base": "", "key": "", "model": ""}
reply = {"text": ""}
extract.chat = lambda *a: reply["text"]

# a line keeps only real ids, a line with none is dropped, "[a, b]" lists are split
text, used = agent.cited("Retries are 7 [D1, D99].\nNo source for this.\nPR 124 set it [pr:124]", {"D1", "pr:124"})
assert text == "Retries are 7 [D1].\nPR 124 set it [pr:124]", text
assert used == ["D1", "pr:124"], used

NAME = "_test_agent"
g = build(NAME, "2026-09-21")
try:
    # ask: the search hits lead to D1 through the graph, the made-up id is dropped
    reply["text"] = "Payments retry 7 times [D1]. Arjun still knows it [D1] [made-up:1].\nIt was always 7."
    out = agent.ask(g, "why do payment retries happen 7 times", LLM)
    assert out["answer"] == "Payments retry 7 times [D1]. Arjun still knows it [D1].", out["answer"]
    assert [c["id"] for c in out["cited"]] == ["D1"], out["cited"]
    assert agent.ask(g, "is it?", LLM)["note"] == "Nothing in the graph mentions that."  # no search words

    # no provider: no answer, but the evidence it would have used
    out = agent.ask(g, "payment retries", None)
    assert out["answer"] is None and "D1" in [c["id"] for c in out["cited"]], out

    # watch: one alert per radar item, with a brief that only cites the knower's evidence; nothing new the second time
    reply["text"] = "- Retries cover the gateway pause [D1] [pr:124]\n- Ask Arjun about the cap [nope]"
    items = {r["item"] for r in radar(g)}
    assert agent.watch(g, None) == len(items) == 12  # no provider: alerts with evidence, no brief
    d1 = next(a for a in agent.alerts(g) if a["item"] == "D1")
    assert "brief" not in d1 and "pr:124" in d1["refs"] and d1["person"] == "arjun", d1
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
