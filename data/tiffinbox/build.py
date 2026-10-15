"""Builds the synthetic TiffinBox fixtures (Apr 1 - Sep 30, 2026) from the story in this file.

Run:  python data/tiffinbox/build.py
It rewrites every fixture next to this file, then checks the data against answer_key.json and exits 1 on a mismatch.
Everything is SYNTHETIC (people, code, chat, tickets, sessions). The two external postmortems cited are real public pages.
RupeeRail is a fictional payment gateway.

Shapes mimic the real sources so the same connectors work on real data later:
  github/pulls.json, github/commits.json  GitHub REST (pull + its /commits shas + /reviews embedded)
  google_chat/spaces.json, messages.json  Google Chat API (spaces.list, spaces.messages.list)
  tickets.json                            Jira REST issue (key + fields)
  sessions/*.jsonl                        Claude Code session log lines
  docs/**.md                              markdown with front-matter
  extractions.json                        cached LLM extraction (decisions, patterns, incidents, research...)
  kt_sessions.json                        handover events (Meera's KT with Arjun)
"""
import hashlib
import json
import random
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent
IST = timezone(timedelta(hours=5, minutes=30))
DOMAIN = "tiffinbox.example"
rnd = random.Random(7)  # fixed seed: same output every run

# ── people, files, spaces ────────────────────────────────────────────────────
PEOPLE = {  # id: (name, role, joined, resigned, last_day)
    "kavya": ("Kavya Nair", "Frontend", "2025-08-04", None, None),
    "arjun": ("Arjun Mehta", "Backend (payments, orders, auth)", "2025-06-02", "2026-09-15", "2026-09-30"),
    "priya": ("Priya Iyer", "DevOps (CI/CD, Terraform, secrets, backups)", "2025-07-01", "2026-09-15", "2026-09-30"),
    "rohan": ("Rohan Das", "AI/ML (recommendations, ETA)", "2025-09-15", None, None),
    "neha": ("Neha Kapoor", "Product manager", "2025-06-02", None, None),
    "meera": ("Meera Joshi", "Backend", "2026-09-22", None, None),
}
CHAT_ID = {p: f"users/1{i:04d}" for i, p in enumerate(PEOPLE, 1)}

FILES = {
    "web/checkout/CheckoutPage.tsx": "web", "web/menu/MenuGrid.tsx": "web", "web/lib/api.ts": "web",
    "api/payments/retry.py": "api", "api/payments/webhooks.py": "api", "api/orders/service.py": "api",
    "api/auth/tokens.py": "api", "api/subscriptions/billing.py": "api", "api/recommend/endpoint.py": "api",
    "infra/terraform/main.tf": "infra", "infra/k8s/api-deploy.yaml": "infra", "infra/backup/db_backup.yaml": "infra",
    ".github/workflows/deploy.yml": "infra", ".github/workflows/ci.yml": "infra", "infra/scripts/rotate_secrets.sh": "infra",
    "ml/recommend/model.py": "ml", "ml/recommend/features.py": "ml", "ml/eta/predict.py": "ml",
}
SERVICE_DEPENDS_ON = [("web", "api"), ("api", "infra"), ("ml", "api")]

# displayName, spaceType, externalUserAllowed. Ingest keeps only company SPACEs (no DMs, no external spaces).
SPACES = {
    "general": ("general", "SPACE", False), "eng": ("eng", "SPACE", False), "payments": ("payments", "SPACE", False),
    "infra": ("infra", "SPACE", False), "incidents": ("incidents", "SPACE", False), "product": ("product", "SPACE", False),
    "rupeerail-shared": ("TiffinBox x RupeeRail", "SPACE", True),
    "dm-arjun-priya": ("", "DIRECT_MESSAGE", False),
}
BOT = {"name": "users/app", "displayName": "RupeeRail Status", "type": "BOT"}
EXTERNAL = {"name": "users/29001", "displayName": "Vikram (RupeeRail)", "type": "HUMAN"}

# ── decisions (cached extraction; this is the answer key's spine) ────────────
DEC = {}


def decision(id, what, why, about, evidence, status="active", applies=(), supersedes=None,
             informed_by=(), justified_by=(), at=None):
    DEC[id] = dict(id=id, what=what, why=why, status=status, at=at, about=list(about), evidence=evidence,
                   applies=list(applies), supersedes=supersedes, informed_by=list(informed_by),
                   justified_by=list(justified_by), recorded_in=[])


decision("D13", "Payment retries = 3 (30s, 60s, 120s)", "Default from the RupeeRail quickstart",
         ["api/payments/retry.py"], "3 attempts at 30s, 60s and 120s", status="superseded")
decision("D1", "Payment retries = 7 with exponential backoff (about a 13 minute window)",
         "RupeeRail pauses webhook delivery for up to ~5 minutes during its deploys. 3 retries gave up after "
         "3.5 minutes and marked paid orders as failed (PAY-88).",
         ["api/payments/retry.py"], "their webhooks pause ~5 min during deploys",
         applies=["P1"], supersedes="D13")
decision("D2", "Webhooks are idempotent: dedupe on RupeeRail event_id",
         "RupeeRail re-sends webhooks; one order was marked paid twice and refunded twice (PAY-61)",
         ["api/payments/webhooks.py"], "dedupe on event_id", applies=["P2"])
decision("D3", "Orders use optimistic locking on a version column",
         "Double orders during the lunch rush when two requests updated the same cart (ORD-31)",
         ["api/orders/service.py"], "optimistic locking on a version column", applies=["P3"])
decision("D4", "Access token TTL = 15 minutes, with refresh tokens",
         "Security review: 24 h tokens are too long-lived if a phone is stolen",
         ["api/auth/tokens.py"], "Access tokens now expire after 15 minutes")
decision("D5", "Billing charges on day 1 of the cycle and prorates paused days",
         "Predictable revenue, and fair to customers who pause",
         ["api/subscriptions/billing.py"], "charge on day 1 of each cycle; paused days are prorated")
decision("D16", "Deploys roll out to all pods at once", "Simplest pipeline for a small team",
         [".github/workflows/deploy.yml"], "rolls out to all pods at once", status="superseded")
decision("D6", "Deploys are canary: 10% of pods for 30 minutes, auto-rollback if 5xx > 2%",
         "The May 12 checkout outage came from an all-at-once deploy (INC-1). Cloudflare's 2019 outage shows "
         "why staged rollouts matter.",
         [".github/workflows/deploy.yml"], "10% of pods for 30 minutes",
         applies=["P4"], supersedes="D16", informed_by=["R1"])
decision("D7", "Terraform state is remote with a lock; never run apply from a laptop",
         "A laptop apply with stale state tried to destroy the Redis cluster",
         ["infra/terraform/main.tf"], "never run terraform apply from a laptop")
decision("D8", "Rotating the RupeeRail API key also requires updating WEBHOOK_SECRET",
         "RupeeRail issues a new webhook signing secret with each key. With the old secret every signature "
         "check fails and payment confirmations are dropped silently.",
         ["infra/scripts/rotate_secrets.sh"], "rotating the API key also rotates the webhook signing secret")
decision("D17", "Nightly pg_dump with no restore test", "Backups felt like enough",
         ["infra/backup/db_backup.yaml"], "nightly pg_dump at 01:00 UTC", status="superseded")
decision("D9", "DB backups at 3 AM IST with a failure alert; restore tested every quarter",
         "Backups were silently empty for 17 days (INC-2). GitLab's 2017 incident shows untested backups fail.",
         ["infra/backup/db_backup.yaml"], "restore test every quarter",
         supersedes="D17", informed_by=["R2"])
decision("D10", "Recommendations exclude price as a ranking feature",
         "Customers said recommendations pushed expensive meals (REC-9); price dominated the ranking",
         ["ml/recommend/features.py"], "drop price and price_bucket from the ranking features")
decision("D11", "ETA falls back to a static 40 minutes if the model takes over 300 ms",
         "Model timeouts during peak hours left the checkout page without an ETA",
         ["ml/eta/predict.py"], "fall back to a static 40 minutes", applies=["P5"])
decision("D12", "Checkout Pay button disables after the first click", "Double clicks caused double payments (WEB-14)",
         ["web/checkout/CheckoutPage.tsx"], "disable the Pay button after the first click")
decision("D14", "CI cache key includes the lockfile hash", "Stale node_modules cache made builds flaky",
         [".github/workflows/ci.yml"], "cache key includes the hash of package-lock.json")
decision("D15", "Subscription pauses are capped at 14 days",
         "11 of 15 interviewees pause for travel and most trips are under 2 weeks; survey and competitor scan agree",
         ["api/subscriptions/billing.py"], "pauses are capped at 14 days", justified_by=["I1", "I2", "I3"])

PATTERNS = [
    dict(id="P1", name="Retry with exponential backoff", implemented_in=["api/payments/retry.py"]),
    dict(id="P2", name="Idempotency key", implemented_in=["api/payments/webhooks.py"]),
    dict(id="P3", name="Optimistic locking", implemented_in=["api/orders/service.py"]),
    dict(id="P4", name="Canary release", implemented_in=[".github/workflows/deploy.yml"]),
    dict(id="P5", name="Fallback / circuit breaker", implemented_in=["ml/eta/predict.py"]),
]
EXTERNAL_SOURCES = [
    dict(id="X1", title="Details of the Cloudflare outage on July 2, 2019", publisher="Cloudflare", date="2019-07-12",
         url="https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/"),
    dict(id="X2", title="Postmortem of database outage of January 31", publisher="GitLab", date="2017-02-10",
         url="https://about.gitlab.com/blog/2017/02/10/postmortem-of-database-outage-of-january-31/"),
]
INSIGHTS = [
    dict(id="I1", text="11 of 15 interviewees pause during travel; most trips are under 2 weeks"),
    dict(id="I2", text="62% of surveyed subscribers would rather pause than cancel"),
    dict(id="I3", text="2 of 3 competitors cap pauses at 2-4 weeks"),
]
RESEARCH, INCIDENTS, FEATURES = [], [], []

# ── collectors ───────────────────────────────────────────────────────────────
commits, pulls, tickets, messages, sessions, docs, timeline = [], [], [], [], {}, {}, []


def utc(s):  # "2026-04-07 10:15" (IST) -> "2026-04-07T04:45:00Z"
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=IST).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def later(s, minutes):
    return (datetime.strptime(s, "%Y-%m-%d %H:%M") + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def h(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()


def gh(p):
    return {"login": f"{p}-tb"}


def note(at, kind, title, records=(), noise=False):
    for d in records:
        DEC[d]["at"] = min(DEC[d]["at"] or "9", utc(at))  # earliest record
    if not noise:
        timeline.append((at, kind, title, records))


def commit(author, at, msg, files, small=False):
    sha = h(author, at, msg)
    commits.append({
        "sha": sha, "author": gh(author),
        "commit": {"author": {"name": PEOPLE[author][0], "email": f"{author}@{DOMAIN}", "date": utc(at)}, "message": msg},
        "files": [{"filename": f, "status": "modified", "additions": 1 if small else rnd.randint(6, 80),
                   "deletions": 1 if small else rnd.randint(0, 30)} for f in files],
    })
    return sha


def pr(author, at, title, body, work, reviews=(), branch=None, records=(), noise=False, merge_after=240, fixes=None):
    """work: [(msg, files)], commits spaced 40 min apart. reviews: [(who, state, body)]."""
    n = 101 + len(pulls)
    shas = [commit(author, later(at, 40 * i), msg, files) for i, (msg, files) in enumerate(work)]
    end = later(at, 40 * len(work))
    pulls.append({
        "number": n, "title": title, "body": body, "user": gh(author), "state": "closed",
        "created_at": utc(at), "merged_at": utc(later(end, merge_after)),
        "head": {"ref": branch or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]}, "base": {"ref": "main"},
        "commits": shas,
        "reviews": [{"id": int(h(n, i)[:8], 16), "user": gh(who), "state": state, "body": text,
                     "submitted_at": utc(later(end, 30 + 20 * i))} for i, (who, state, text) in enumerate(reviews)],
    })
    if fixes:
        next(t for t in tickets if t["key"] == fixes)["links"]["pull_requests"].append(n)
    for d in records:
        DEC[d]["recorded_in"].append(f"pr:{n}")
    note(at, "PR", f"#{n} {title} ({author})", records, noise)
    return n


def thread(space, at, msgs, records=(), noise=False, title=None):
    """msgs: [(person | BOT | EXTERNAL, minutes_after_start, text)]."""
    tid = h(space, at, msgs[0][2])[:11]
    for i, (who, mins, text) in enumerate(msgs):
        sender = who if isinstance(who, dict) else {"name": CHAT_ID[who], "displayName": PEOPLE[who][0], "type": "HUMAN"}
        messages.append({
            "name": f"spaces/{space}/messages/{tid}.{h(tid, i)[:11]}", "sender": sender,
            "createTime": utc(later(at, mins)), "text": text,
            "thread": {"name": f"spaces/{space}/threads/{tid}"}, "space": {"name": f"spaces/{space}"},
        })
    ref = f"thread:spaces/{space}/threads/{tid}"
    for d in records:
        DEC[d]["recorded_in"].append(ref)
    note(at, "Chat", f"#{space}: {title or msgs[0][2][:70]}", records, noise)
    return ref


def ticket(key, at, summary, description, assignee, reporter, status="Done", done_after_days=3,
           labels=(), records=(), noise=False):
    def user(p):
        return {"accountId": f"acc-{p}", "displayName": PEOPLE[p][0], "emailAddress": f"{p}@{DOMAIN}"}
    tickets.append({"key": key, "fields": {
        "summary": summary, "description": description, "assignee": user(assignee), "reporter": user(reporter),
        "status": {"name": status}, "created": utc(at), "labels": list(labels),
        "resolutiondate": utc(later(at, done_after_days * 1440)) if status == "Done" else None},
        "links": {"pull_requests": []}})
    for d in records:
        DEC[d]["recorded_in"].append(f"ticket:{key}")
    note(at, "Ticket", f"{key} {summary} (assignee {assignee})", records, noise)


def session(person, at, branch, title, turns, records=(), noise=False):
    """turns: [(prompt, reply, [(path, old, new)])]. Writes Claude Code JSONL lines."""
    sid = "%s-%s-%s-%s-%s" % (lambda x: (x[:8], x[8:12], x[12:16], x[16:20], x[20:32]))(h(person, at, title))
    cwd = f"/home/{person}/code/tiffinbox"
    lines, parent, t = [], None, 0

    def line(kind, message):
        nonlocal parent, t
        u = h(sid, len(lines))
        u = f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:32]}"
        lines.append({"type": kind, "sessionId": sid, "uuid": u, "parentUuid": parent, "timestamp": utc(later(at, t)),
                      "cwd": cwd, "gitBranch": branch, "version": "2.1.3", "userType": "external",
                      "isSidechain": False, "message": message})
        parent, t = u, t + 2

    for prompt, reply, edits in turns:
        line("user", {"role": "user", "content": prompt})
        content = [{"type": "text", "text": reply}]
        content += [{"type": "tool_use", "id": f"toolu_{h(sid, p, t)[:20]}", "name": "Edit",
                     "input": {"file_path": f"{cwd}/{p}", "old_string": old, "new_string": new}} for p, old, new in edits]
        line("assistant", {"role": "assistant", "model": "claude-sonnet-4-5", "content": content})
        for c in content[1:]:
            line("user", {"role": "user", "content": [{"type": "tool_result", "tool_use_id": c["id"],
                                                         "content": f"The file {c['input']['file_path']} has been updated successfully."}]})
    lines.append({"type": "ai-title", "sessionId": sid, "aiTitle": title})
    sessions[sid] = (person, lines)
    for d in records:
        DEC[d]["recorded_in"].append(f"session:{sid}")
    note(at, "AI session", f"{title} ({person})", records, noise)
    return f"session:{sid}"


def doc(path, author, at, title, kind, body, records=(), noise=False):
    docs[path] = (f"---\ntitle: {title}\nauthor: {author}@{DOMAIN}\ndate: {utc(at)}\nkind: {kind}\n---\n\n"
                  f"# {title}\n\n{body.strip()}\n")
    for d in records:
        DEC[d]["recorded_in"].append(f"doc:{path}")
    note(at, "Doc", f"{path} ({author})", records, noise)
    return f"doc:{path}"


# ══ THE STORY (Apr 1 - Sep 30, 2026, times in IST) ═══════════════════════════
# ── April: the product gets built, fast and without much review ─────────────
# date = last update (created Apr 2, pause section added Jul 20); a doc node keeps its latest version
doc("docs/prd/subscriptions.md", "neha", "2026-07-20 11:00", "PRD: Weekly tiffin subscriptions", "prd", """
## Problem
Office workers in Pune want a home-style lunch without ordering every day.

## Billing
- We charge on day 1 of each cycle; paused days are prorated as credit on the next cycle.
- Failed charges are retried automatically before a subscription is marked unpaid.

## Pausing (added 2026-07-20)
- Customers can pause from the app. Based on interviews, the survey and the competitor scan
  (docs/research/), pauses are capped at 14 days. Longer breaks should cancel and resubscribe.

## Out of scope for v1
Family plans, corporate billing.
""", records=["D5", "D15"])

pr("arjun", "2026-04-06 11:30", "payments: retry failed charges",
   "Retries failed charges: 3 attempts at 30s, 60s and 120s (RupeeRail quickstart default). "
   "After the last attempt the order goes to payment_failed.",
   [("payments: add retry loop for failed charges", ["api/payments/retry.py"]),
    ("payments: tests for retry exhaustion", ["api/payments/retry.py"])], records=["D13"])
pr("arjun", "2026-04-08 15:00", "subscriptions: billing cycle and proration",
   "Implements the PRD billing rules: charge on day 1 of each cycle; paused days are prorated as credit.",
   [("subscriptions: billing cycle job", ["api/subscriptions/billing.py"]),
    ("subscriptions: proration for paused days", ["api/subscriptions/billing.py"])], records=["D5"])
pr("priya", "2026-04-10 10:30", "deploy: GitHub Actions to k8s",
   "First deploy pipeline. On merge to main it builds the image and rolls out to all pods at once. "
   "Good enough while we are small.",
   [("deploy: build and push image", [".github/workflows/deploy.yml"]),
    ("k8s: api deployment manifest", ["infra/k8s/api-deploy.yaml"]),
    ("deploy: kubectl apply on main", [".github/workflows/deploy.yml"])], records=["D16"])
pr("priya", "2026-04-13 12:00", "terraform: base infra (VPC, RDS, Redis)",
   "VPC, Postgres on RDS, Redis for sessions. Applied from my machine for now.",
   [("terraform: vpc and rds", ["infra/terraform/main.tf"]), ("terraform: redis", ["infra/terraform/main.tf"])])
pr("priya", "2026-04-15 16:00", "backup: nightly database dump",
   "CronJob runs a nightly pg_dump at 01:00 UTC to S3, kept for 7 days.",
   [("backup: pg_dump cronjob", ["infra/backup/db_backup.yaml"])], records=["D17"])
pr("priya", "2026-04-16 11:00", "scripts: secrets rotation helper",
   "Rotates the RupeeRail API key and the DB password in the k8s secret. Run quarterly.",
   [("scripts: rotate_secrets.sh", ["infra/scripts/rotate_secrets.sh"])])
pr("kavya", "2026-04-17 10:00", "web: checkout page v1", "Checkout with saved address and UPI/card via RupeeRail.",
   [("web: checkout page", ["web/checkout/CheckoutPage.tsx"]), ("web: api client", ["web/lib/api.ts"])],
   reviews=[("arjun", "APPROVED", "API calls match the orders contract. LGTM.")])
pr("rohan", "2026-04-20 14:00", "recommend: v1 model",
   "Popularity + cuisine affinity model. Features include price and price_bucket.",
   [("ml: recommendation model", ["ml/recommend/model.py"]), ("ml: feature builder", ["ml/recommend/features.py"])])
pr("rohan", "2026-04-21 12:00", "api: /recommend endpoint", "Serves the v1 model behind the API.",
   [("api: /recommend endpoint", ["api/recommend/endpoint.py"])],
   reviews=[("arjun", "APPROVED", "Endpoint looks fine; added a timeout comment.")])
pr("arjun", "2026-04-22 11:00", "orders: create and list orders", "Order service with cart -> order conversion.",
   [("orders: service", ["api/orders/service.py"]), ("orders: list endpoint", ["api/orders/service.py"])],
   reviews=[("rohan", "APPROVED", "Works with the ETA call. LGTM.")])
pr("priya", "2026-04-24 15:00", "ci: lint and tests on every PR", "Runs ruff, pytest and the web build on PRs.",
   [("ci: workflow", [".github/workflows/ci.yml"])])
pr("rohan", "2026-04-28 12:00", "eta: delivery time model v1", "Gradient-boosted ETA model served from the API.",
   [("eta: predict", ["ml/eta/predict.py"])], reviews=[("arjun", "APPROVED", "Call site in orders looks right.")])

# ── May: double payments, the checkout outage, canary deploys, lunch-rush race ─
ticket("WEB-14", "2026-05-04 12:10", "Customers charged twice after double-clicking Pay",
       "Three support tickets this week. Double click on Pay sends two payment requests.", "kavya", "neha")
pr("kavya", "2026-05-05 10:00", "checkout: disable Pay after first click",
   "Fixes WEB-14. We disable the Pay button after the first click and show a spinner until the API answers.",
   [("checkout: disable pay button while pending", ["web/checkout/CheckoutPage.tsx"])],
   reviews=[("arjun", "APPROVED", "Backend also rejects a second charge for the same order within 60s, so this is belt and braces.")],
   records=["D12"], fixes="WEB-14")

thread("incidents", "2026-05-12 14:05", [
    ("kavya", 0, "Checkout is throwing 502s for everyone. Anyone deploying?"),
    ("priya", 3, "Yes, v1.8 went out 5 min ago. All api pods are crashlooping, missing env var. Rolling back."),
    ("neha", 6, "Customers are posting on Instagram that they can't pay for lunch. I'll put up a banner."),
    ("arjun", 9, "Payments queue is backing up; nothing lost, it will drain once api is back."),
    ("priya", 38, "Rolled back, all green. Root cause: the deploy updates every pod at once, so one bad config "
                  "took down 100% of api. Writing the postmortem."),
], title="INC-1 checkout down 38 min")
INCIDENTS.append(dict(id="INC-1", title="Checkout down for 38 minutes after an all-at-once deploy", at=utc("2026-05-12 14:05"),
                      severity="sev1", caused_by="D16", recorded_in=[f"thread:{messages[-1]['thread']['name']}",
                                                                      "doc:docs/postmortems/2026-05-12-checkout-outage.md"]))
doc("docs/postmortems/2026-05-12-checkout-outage.md", "priya", "2026-05-14 11:00", "Postmortem: checkout outage (May 12)",
    "postmortem", """
**Impact:** checkout returned 502 for 38 minutes at lunch peak. About 140 orders lost.
**Cause:** v1.8 shipped a config that needed a new env var. The pipeline rolls out to all pods at once,
so every api pod crashlooped at the same time.
**Action items:** research progressive delivery (Priya), add an env-var check to CI (Priya).
""")
doc("docs/research/canary-deploys.md", "priya", "2026-05-15 15:00", "Research: progressive delivery after INC-1", "research", """
Cloudflare's 2 July 2019 outage: one WAF rule was pushed to every machine at once and CPU hit 100% worldwide.
Their fix was staged rollouts that watch error rates before going wider.
Same shape as our INC-1: one change, every pod, no stop button.

Options considered: blue/green (needs 2x capacity, too expensive now), canary (cheap on k8s).
Recommendation: canary 10% of pods for 30 minutes and roll back automatically if 5xx goes above 2%.
""")
RESEARCH.append(dict(id="R1", title="Progressive delivery after INC-1", author="priya", doc="docs/research/canary-deploys.md",
                     cites=["X1"], found=[], informs=["D6"]))
session("priya", "2026-05-18 10:00", "canary-deploys", "Canary deploys in GitHub Actions", [
    ("After our checkout outage I want canary deploys: 10% of pods for 30 minutes, then the rest, and auto rollback "
     "if 5xx goes over 2%. We use plain k8s Deployments and GitHub Actions. Edit deploy.yml.",
     "I'll add a canary Deployment with 1 of 10 replicas, a 30 minute watch step that queries the 5xx rate, and a "
     "rollback step. Promotion only happens if the error rate stays under 2%.",
     [(".github/workflows/deploy.yml", "kubectl apply -f infra/k8s/api-deploy.yaml",
       "kubectl apply -f infra/k8s/api-canary.yaml\n# watch 10% of pods for 30 minutes")]),
    ("Make the watch window configurable but default it to 30 min.",
     "Added CANARY_MINUTES with default 30 and documented why in a comment pointing at INC-1.",
     [(".github/workflows/deploy.yml", "sleep 1800", "sleep $((CANARY_MINUTES * 60))")]),
], records=["D6"])
pr("priya", "2026-05-19 11:00", "deploy: canary 10% for 30 minutes with auto-rollback",
   "After INC-1. Deploys now go to 10% of pods for 30 minutes; if 5xx > 2% we roll back automatically. "
   "See docs/research/canary-deploys.md.",
   [("deploy: canary stage", [".github/workflows/deploy.yml"]), ("deploy: error-rate gate and rollback", [".github/workflows/deploy.yml"])],
   records=["D6"])
doc("docs/runbooks/deploy.md", "priya", "2026-05-20 16:00", "Runbook: deploying the api", "runbook", """
1. Merge to main. The pipeline deploys a canary: 10% of pods for 30 minutes.
2. Watch the error-rate gate in the Actions log. If 5xx > 2% it rolls back by itself.
3. Manual rollback: re-run the previous successful deploy job.
Never edit pods by hand.
""", records=["D6"])

thread("eng", "2026-05-26 13:20", [
    ("neha", 0, "Support says some customers got two identical orders today at 12:58. ORD-31."),
    ("rohan", 15, "I see two ETA calls 40 ms apart for the same cart in the logs. Looks like a race."),
    ("arjun", 30, "Yep, two requests both read the cart before either wrote. Fixing in orders/service.py."),
], title="double orders at lunch")
ticket("ORD-31", "2026-05-26 13:25", "Duplicate orders during lunch rush",
       "Two orders created for one cart when the customer taps twice on a slow network.", "arjun", "neha")
pr("arjun", "2026-05-28 11:00", "orders: optimistic locking on cart checkout",
   "Fixes ORD-31. We use optimistic locking on a version column: the second writer gets a conflict and retries. "
   "Cheaper than row locks at lunch peak.",
   [("orders: add version column", ["api/orders/service.py"]), ("orders: retry on version conflict", ["api/orders/service.py"])],
   reviews=[("rohan", "COMMENTED", "Should the ETA call move after the commit so we don't compute it twice?"),
            ("rohan", "APPROVED", "LGTM after the move.")], records=["D3"], fixes="ORD-31")

# ── June: tokens, webhooks, the backup scare ────────────────────────────────
ticket("SEC-4", "2026-05-30 10:00", "Security review findings", "Access tokens live for 24 h. Recommend <= 15 min with refresh.",
       "arjun", "neha")
pr("arjun", "2026-06-02 11:00", "auth: 15 minute access tokens with refresh",
   "Fixes SEC-4. Access tokens now expire after 15 minutes; the web app refreshes them silently.",
   [("auth: short-lived access tokens", ["api/auth/tokens.py"]), ("auth: refresh endpoint", ["api/auth/tokens.py"])],
   reviews=[("kavya", "APPROVED", "Tested the silent refresh in the web app. Works.")], records=["D4"], fixes="SEC-4")
pr("arjun", "2026-06-04 15:00", "k8s: raise api memory limit to 512Mi", "Orders spikes at lunch were OOM-killing pods.",
   [("k8s: api memory 512Mi", ["infra/k8s/api-deploy.yaml"])],
   reviews=[("priya", "APPROVED", "Fine. Requests 256Mi, limits 512Mi.")])

thread("payments", "2026-06-09 18:40", [
    (BOT, 0, "Webhook delivery retried for 3 events due to timeouts on your endpoint."),
    ("neha", 20, "A customer got two refunds for one order. Is that related?"),
    ("arjun", 35, "Yes. RupeeRail re-sent the payment webhook and we processed it twice. Fix tomorrow. PAY-61."),
], title="webhook processed twice")
ticket("PAY-61", "2026-06-09 19:00", "Webhook processed twice -> double refund",
       "Gateway retried a webhook after a timeout and we marked the order paid twice.", "arjun", "neha")
pr("arjun", "2026-06-11 11:00", "webhooks: dedupe on event_id",
   "Fixes PAY-61. We store each RupeeRail event_id and dedupe on event_id before doing anything, so a re-sent "
   "webhook is a no-op.",
   [("webhooks: processed_events table", ["api/payments/webhooks.py"]), ("webhooks: skip seen event ids", ["api/payments/webhooks.py"])],
   records=["D2"], fixes="PAY-61")
doc("docs/adr/0003-webhook-idempotency.md", "neha", "2026-06-12 15:00", "ADR 0003: Webhook idempotency", "adr", """
**Status:** accepted (written by Neha after a walkthrough with Arjun)
**Context:** RupeeRail retries webhooks when our endpoint is slow, so the same event can arrive more than once (PAY-61).
**Decision:** dedupe on event_id. Every event id is stored; a repeat is acknowledged and ignored.
**Consequences:** the processed_events table grows; we keep 90 days.
""", records=["D2"])

thread("incidents", "2026-06-16 17:30", [
    ("priya", 0, "Tried restoring last night's backup to staging to debug a data issue. The dump is 0 bytes. "
                 "So is every dump since May 30."),
    ("arjun", 10, "May 30 is when we rotated the DB password. Did the backup job get the new one?"),
    ("priya", 18, "No. pg_dump failed auth and the job still exited 0. We have had no backups for 17 days."),
    ("neha", 25, "Do we need to tell customers?"),
    ("priya", 40, "No data lost, prod is fine. Taking a manual dump now. Fixing the job properly this week."),
], title="INC-2 backups silently empty")
INCIDENTS.append(dict(id="INC-2", title="Database backups silently empty for 17 days", at=utc("2026-06-16 17:30"),
                      severity="sev2", caused_by="D17", recorded_in=[f"thread:{messages[-1]['thread']['name']}"]))
doc("docs/research/backup-restore.md", "priya", "2026-06-18 12:00", "Research: backups we can trust", "research", """
GitLab's 31 Jan 2017 database incident: five backup methods were set up and none worked when needed,
because nobody had tested a restore. Our INC-2 is the same failure in miniature.

Takeaways: alert on failed or tiny dumps; a backup only counts once it has been restored.
Plan: dump at 3 AM IST (lowest traffic), alert if the job fails or the dump is under 1 MB,
and a restore test every quarter into a scratch database with row-count checks.
""")
RESEARCH.append(dict(id="R2", title="Backups we can trust", author="priya", doc="docs/research/backup-restore.md",
                     cites=["X2"], found=[], informs=["D9"]))
pr("priya", "2026-06-22 11:00", "backup: 3 AM IST dumps, failure alert, quarterly restore test",
   "After INC-2. Dumps run at 3 AM IST, the job fails loudly on auth errors or small dumps, and a restore test every "
   "quarter restores into a scratch DB and checks row counts.",
   [("backup: schedule 21:30 UTC", ["infra/backup/db_backup.yaml"]), ("backup: fail on auth error and tiny dumps", ["infra/backup/db_backup.yaml"]),
    ("backup: quarterly restore test job", ["infra/backup/db_backup.yaml"])], records=["D9"])
doc("docs/runbooks/backup-restore.md", "priya", "2026-06-23 15:00", "Runbook: backups and restores", "runbook", """
- Dumps run daily at 3 AM IST to s3://tiffinbox-backups (30 days).
- Alerts fire in #infra if a dump fails or is under 1 MB.
- We do a restore test every quarter: restore into a scratch DB, compare row counts, record the date here.
- Last restore test: 2026-06-24 (passed).
""", records=["D9"])

thread("product", "2026-06-24 12:00", [
    ("neha", 0, "Getting a pattern in reviews: 'the app only recommends the expensive thalis'. REC-9."),
    ("rohan", 30, "Price is the strongest feature in the ranker right now. I'll look at removing it."),
], title="recs push expensive meals")
ticket("REC-9", "2026-06-24 12:20", "Recommendations push expensive meals",
       "App reviews and support say recommendations favour the most expensive thalis.", "rohan", "neha",
       records=["D10"])
session("rohan", "2026-06-26 11:00", "recs-no-price", "Remove price from recommendation ranking", [
    ("Users complain the recommender pushes expensive meals. Price is our top feature. Remove it from ranking "
     "without hurting relevance too much.",
     "I'll drop price and price_bucket from the ranking features and keep cuisine affinity and recency. Offline NDCG "
     "drops from 0.41 to 0.39, which is a small cost for removing the bias.",
     [("ml/recommend/features.py", "FEATURES = [\"price\", \"price_bucket\", \"cuisine\", \"recency\"]",
       "FEATURES = [\"cuisine\", \"recency\"]")]),
], records=["D10"])
pr("rohan", "2026-06-27 10:00", "recommend: remove price features",
   "REC-9. Ranking no longer uses price. NDCG 0.41 -> 0.39.",
   [("ml: drop price features", ["ml/recommend/features.py"]), ("ml: retrain", ["ml/recommend/model.py"])], records=["D10"], fixes="REC-9")

# ── July: Terraform lock, PM research, pause cap, ETA fallback ──────────────
pr("priya", "2026-07-01 11:00", "terraform: remote state with locking",
   "State moves to S3 with a DynamoDB lock. Applies only run from CI on merge.",
   [("terraform: s3 backend", ["infra/terraform/main.tf"]), ("terraform: dynamodb lock table", ["infra/terraform/main.tf"])],
   records=["D7"])
thread("infra", "2026-07-01 16:00", [
    ("priya", 0, "PSA: Terraform state now lives in S3 with a DynamoDB lock. Please never run terraform apply from a "
                 "laptop again; CI applies on merge to main. Last week a laptop apply with stale state tried to "
                 "destroy the Redis cluster."),
], records=["D7"], title="PSA terraform state")

doc("docs/research/pause-interviews.md", "neha", "2026-07-07 18:00", "Research: why subscribers pause", "research", """
15 interviews (9 office workers, 4 students, 2 families), 20 minutes each.
- 11 of 15 pause during travel (work trips, going home for festivals).
- Most trips are under 2 weeks; only 2 people paused for a month or more.
- People who could not pause easily cancelled instead.
""")
doc("docs/research/pause-survey.md", "neha", "2026-07-09 17:00", "Research: pause survey", "research", """
In-app survey, 412 responses. 62% would rather pause than cancel when they travel.
Median expected pause: 8 days.
""")
doc("docs/research/competitor-scan.md", "neha", "2026-07-10 16:00", "Research: competitor pause policies", "research", """
Three meal-subscription competitors checked. Two cap pauses at 2-4 weeks; one allows unlimited pauses
but charges a holding fee.
""")
RESEARCH += [dict(id="R3", title="Why subscribers pause", author="neha", doc="docs/research/pause-interviews.md", cites=[], found=["I1"], informs=[]),
             dict(id="R4", title="Pause survey", author="neha", doc="docs/research/pause-survey.md", cites=[], found=["I2"], informs=[]),
             dict(id="R5", title="Competitor pause policies", author="neha", doc="docs/research/competitor-scan.md", cites=[], found=["I3"], informs=[])]
thread("product", "2026-07-14 11:00", [
    ("neha", 0, "Proposal from the research: pauses are capped at 14 days. Interviews, survey and competitors all point "
                "the same way. Longer than that, cancel and resubscribe."),
    ("kavya", 20, "UI-wise: a date picker limited to 14 days from today?"),
    ("arjun", 35, "Billing already prorates paused days, so the cap is a validation in billing.py. Easy."),
], records=["D15"], title="pause cap proposal")
pr("arjun", "2026-07-22 11:00", "subscriptions: pause up to 14 days",
   "Implements the PRD update: pauses are capped at 14 days. Validation in billing.py; the web date picker is limited too.",
   [("subscriptions: pause cap validation", ["api/subscriptions/billing.py"])],
   reviews=[("kavya", "APPROVED", "Matches the date picker. LGTM.")], records=["D15"])
FEATURES.append(dict(id="F1", name="Subscription pause", decisions=["D15"], implemented_by=[f"pr:{pulls[-1]['number']}"], about=["api/subscriptions/billing.py"]))
pr("rohan", "2026-07-24 15:00", "eta: static fallback on model timeout",
   "At lunch peak the ETA model sometimes takes over a second. If it takes over 300 ms we fall back to a static "
   "40 minutes so checkout never waits.",
   [("eta: timeout wrapper", ["ml/eta/predict.py"]), ("eta: fall back to a static 40 minutes", ["ml/eta/predict.py"])],
   reviews=[("arjun", "APPROVED", "Orders already handles a missing ETA, so the fallback is safe.")], records=["D11"])

# ── August: retries = 7 (the star why-trace), CI cache, the key-rotation trap ─
thread("rupeerail-shared", "2026-08-03 16:00", [
    ("arjun", 0, "Hi Vikram, we see payment webhooks arriving late around your deploy windows. Is that expected?"),
    (EXTERNAL, 45, "Yes, during our deploys webhook delivery pauses for up to about 5 minutes, then everything queued is "
                   "delivered. We retry delivery for 1 hour."),
], title="external: webhook delays during gateway deploys")
thread("payments", "2026-08-04 13:55", [
    (BOT, 0, "Scheduled maintenance: RupeeRail API deploy 14:00-14:10 IST. Webhook delivery may be delayed."),
    ("arjun", 27, "12 orders flipped to payment_failed between 14:02 and 14:06 even though the customers were charged."),
    ("arjun", 45, "Found it. Our retry policy is 3 attempts at 30s, 60s and 120s, so we give up after 3.5 minutes. "
                  "RupeeRail confirmed their webhooks pause ~5 min during deploys. Moving to 7 retries with "
                  "exponential backoff, which covers about 13 minutes. Tracking in PAY-88."),
    ("arjun", 46, "Re-synced the 12 orders by hand from the RupeeRail dashboard."),
], records=["D1"], title="orders failed during gateway deploy")
ticket("PAY-88", "2026-08-04 14:45", "Orders marked payment_failed during RupeeRail deploys",
       "RupeeRail pauses webhooks for ~5 min during deploys; our 3 retries (30/60/120s) give up after 3.5 min. "
       "Plan: 7 retries with exponential backoff.", "arjun", "arjun", records=["D1"])
session("arjun", "2026-08-05 10:30", "pay-88-retries", "Retry policy for gateway deploy gaps", [
    ("Our payment retry gives up after 3 tries (30/60/120s). RupeeRail webhooks pause up to 5 minutes during their "
     "deploys, so paid orders get marked failed. Change retry.py to 7 attempts with exponential backoff, cap each "
     "wait at 3 minutes, add jitter.",
     "With a 15 s base doubling and a 180 s cap the waits are 15, 30, 60, 120, 180, 180, 180 seconds, about 12.75 "
     "minutes in total. That covers a 5 minute gateway pause even if a deploy overruns. I'll set RETRIES = 7.",
     [("api/payments/retry.py", "RETRIES = 3\nDELAYS = [30, 60, 120]",
       "RETRIES = 7  # RupeeRail webhooks pause ~5 min during their deploys (PAY-88)\nBASE, CAP = 15, 180")]),
    ("Add a test that a 5 minute gap still succeeds.",
     "Added test_survives_5_minute_gateway_pause using a fake clock.",
     [("api/payments/retry.py", "", "def _delay(attempt): return min(CAP, BASE * 2 ** attempt) + jitter()")]),
], records=["D1"])
pr("arjun", "2026-08-05 12:00", "payments: 7 retries with exponential backoff",
   "Fixes PAY-88. RupeeRail pauses webhook delivery for up to ~5 minutes during deploys and our 3 retries gave up "
   "after 3.5 minutes. Now 7 retries, 15 s base, 180 s cap, jitter: about 13 minutes of cover.",
   [("payments: 7 retries with backoff and jitter", ["api/payments/retry.py"]),
    ("payments: test 5 minute gateway pause", ["api/payments/retry.py"])], records=["D1"], fixes="PAY-88")

pr("kavya", "2026-08-12 11:00", "ci: frontend lint and type-check step", "Adds eslint and tsc to the CI workflow for web/.",
   [("ci: web lint and tsc", [".github/workflows/ci.yml"])],
   reviews=[("priya", "APPROVED", "Put it in its own job so it runs in parallel. LGTM.")])
thread("eng", "2026-08-18 12:30", [
    ("kavya", 0, "Builds failed 4 times today with missing modules, then passed on retry. Is CI flaky?"),
    ("rohan", 10, "Same on my ml PR this morning."),
    ("priya", 25, "Probably the node_modules cache being restored from an older lockfile. Looking."),
], title="flaky CI builds")
session("priya", "2026-08-19 10:00", "ci-cache", "Fix flaky CI cache", [
    ("CI restores node_modules from cache and sometimes it is from an old lockfile, so builds fail. Fix ci.yml.",
     "The cache key is just the OS. I'll make the cache key include the hash of package-lock.json so a lockfile "
     "change always misses the cache.",
     [(".github/workflows/ci.yml", "key: ${{ runner.os }}-node", "key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}")]),
], records=["D14"])
pr("priya", "2026-08-20 11:00", "ci: cache key includes lockfile hash",
   "Fixes the flaky builds: the cache key includes the hash of package-lock.json.",
   [("ci: lockfile hash in cache key", [".github/workflows/ci.yml"])], records=["D14"])

thread("infra", "2026-08-26 15:10", [
    ("priya", 0, "Rotated the RupeeRail API key on staging per the quarterly checklist. Charges work but no webhooks "
                 "are being processed?"),
    ("arjun", 12, "Signature check fails on every webhook. It's buried in their docs: rotating the API key also "
                  "rotates the webhook signing secret. We still have the old WEBHOOK_SECRET in the k8s secret, so "
                  "webhooks.py rejects everything and only logs at debug. On prod every payment confirmation would "
                  "silently fail."),
    ("priya", 20, "Yikes. I'll make rotate_secrets.sh update both in one step and refuse to finish until a test "
                  "webhook verifies."),
    ("arjun", 22, "And let's never rotate one without the other."),
], records=["D8"], title="key rotation broke webhooks on staging")
pr("priya", "2026-08-27 11:00", "scripts: rotate gateway key and webhook secret together",
   "rotate_secrets.sh now updates RUPEERAIL_API_KEY and WEBHOOK_SECRET in one step and sends a test webhook before "
   "it finishes. Rotating the API key also rotates the webhook signing secret on RupeeRail's side.",
   [("scripts: rotate webhook secret with the api key", ["infra/scripts/rotate_secrets.sh"]),
    ("scripts: verify with a test webhook", ["infra/scripts/rotate_secrets.sh"])],
   reviews=[("arjun", "APPROVED", "Tested on staging: rotation + test webhook passes.")], records=["D8"])

# ── September: resignations, Meera joins, the handover ──────────────────────
thread("general", "2026-09-15 18:00", [
    ("neha", 0, "Team: Arjun and Priya have resigned; their last day is Sep 30. Meera joins backend on Sep 22."),
    ("kavya", 5, "Going to miss you both!"),
    ("arjun", 12, "Happy to do KT with Meera in her first week."),
], title="resignations announced")
thread("general", "2026-09-22 10:00", [
    ("neha", 0, "Welcome Meera! She takes over payments, orders and auth from Arjun."),
    ("meera", 4, "Thanks all, excited to be here."),
], title="Meera joins")
KT = [dict(id="KT-1", at=utc("2026-09-24 15:00"), leaver="arjun", learner="meera", via="kt_session", duration_min=90,
           covered=["D1", "D8", "infra/scripts/rotate_secrets.sh"],
           notes="Walked through retry.py and the PAY-88 history, then the key-rotation trap and rotate_secrets.sh.")]
pr("meera", "2026-09-25 11:00", "payments: retry count from env (default 7)",
   "First PR. RETRIES stays 7 by default (see PAY-88: gateway deploy gaps) but can be set per environment.",
   [("payments: RETRIES from env", ["api/payments/retry.py"]), ("k8s: PAYMENT_RETRIES env", ["infra/k8s/api-deploy.yaml"])],
   reviews=[("arjun", "APPROVED", "Keep the default at 7. LGTM.")])
pr("meera", "2026-09-28 11:00", "webhooks: log signature failures at error level",
   "Signature failures were only logged at debug, which hid the staging key-rotation issue. Now error + metric.",
   [("webhooks: error log and metric on bad signature", ["api/payments/webhooks.py"])],
   reviews=[("arjun", "APPROVED", "Good catch.")])
session("meera", "2026-09-29 10:00", "explore-payments", "Understand payments retry and webhooks", [
    ("Explain how retry.py and webhooks.py work together and anything I must not change.",
     "retry.py retries failed charges 7 times with backoff because the gateway pauses webhooks during deploys; "
     "webhooks.py dedupes on event_id and verifies signatures with WEBHOOK_SECRET. Do not lower RETRIES, and rotate "
     "the API key only with rotate_secrets.sh.", []),
])

# ══ NOISE: normal work and trivia (~40% of events) ═══════════════════════════
OWN = {  # person: (files they work on, who may review)  -- keeps the answer key intact
    "kavya": (["web/checkout/CheckoutPage.tsx", "web/menu/MenuGrid.tsx", "web/lib/api.ts"], ["arjun", "rohan"]),
    "arjun": (["api/orders/service.py", "api/auth/tokens.py", "api/subscriptions/billing.py"], ["rohan", "kavya"]),
    "rohan": (["ml/recommend/model.py", "ml/recommend/features.py", "ml/eta/predict.py"], []),
    "priya": (["infra/terraform/main.tf", "infra/backup/db_backup.yaml", ".github/workflows/deploy.yml"], []),
}
NOISE_PRS = [
    ("kavya", "menu: lazy-load dish images", ["web/menu/MenuGrid.tsx"], "rohan"),
    ("kavya", "menu: veg / non-veg filter", ["web/menu/MenuGrid.tsx"], "rohan"),
    ("kavya", "api client: toast on network errors", ["web/lib/api.ts"], "arjun"),
    ("kavya", "checkout: address autocomplete", ["web/checkout/CheckoutPage.tsx"], "arjun"),
    ("kavya", "menu: skeleton loaders", ["web/menu/MenuGrid.tsx"], None),
    ("arjun", "orders: filter by status", ["api/orders/service.py"], "rohan"),
    ("arjun", "orders: 10 minute cancel window", ["api/orders/service.py"], "rohan"),
    ("arjun", "billing: invoice emails", ["api/subscriptions/billing.py"], "kavya"),
    ("arjun", "auth: rate-limit login attempts", ["api/auth/tokens.py"], "kavya"),
    ("arjun", "webhooks: structured logging", ["api/payments/webhooks.py"], None),
    ("arjun", "payments: log attempt number", ["api/payments/retry.py"], None),
    ("rohan", "recommend: weekly retrain job", ["ml/recommend/model.py"], None),
    ("rohan", "recommend: cuisine embeddings", ["ml/recommend/features.py"], None),
    ("rohan", "recommend: cache endpoint responses", ["api/recommend/endpoint.py"], "arjun"),
    ("rohan", "eta: add rain feature", ["ml/eta/predict.py"], "arjun"),
    ("priya", "terraform: tag all resources", ["infra/terraform/main.tf"], None),
    ("priya", "backup: keep dumps 30 days", ["infra/backup/db_backup.yaml"], None),
    ("priya", "deploy: post deploy status to chat", [".github/workflows/deploy.yml"], None),
]
TRIVIA = ["fix typo", "fix typo in comment", "run formatter", "update comment", "fix lint warning"]
NOISE_THREADS = [
    ("general", [("neha", "Lunch is on the house Friday, we crossed 2,000 subscribers!"), ("kavya", "🎉"), ("rohan", "Biryani please")]),
    ("general", [("kavya", "Is the office AC fixed?"), ("priya", "Facilities say Monday.")]),
    ("general", [("rohan", "Anyone up for cricket Saturday?"), ("arjun", "In."), ("kavya", "In!")]),
    ("general", [("neha", "Reminder: town hall at 5 today.")]),
    ("general", [("priya", "Who left the chai on the stove again"), ("arjun", "Not me 👀")]),
    ("general", [("neha", "Diwali week: we pause standups Tue-Thu."), ("kavya", "👍")]),
    ("eng", [("kavya", "Do we have a staging login for testing?"), ("arjun", "Use test@tiffinbox.example, OTP 000000 on staging.")]),
    ("eng", [("rohan", "Can someone review my ETA PR today?"), ("arjun", "After lunch.")]),
    ("eng", [("arjun", "Postgres upgrade to 16 next week on staging first.")]),
    ("eng", [("kavya", "Moving the web app to React 19 this sprint."), ("neha", "Any user-visible change?"), ("kavya", "No.")]),
    ("eng", [("priya", "Staging will be down 15 min at 6 PM for a node pool upgrade.")]),
    ("eng", [("rohan", "Model training box is free tonight if anyone needs a GPU.")]),
    ("eng", [("neha", "Sprint demo Friday 4 PM. Bring one screen each.")]),
    ("eng", [("kavya", "Storybook is live on staging now."), ("rohan", "Nice")]),
    ("product", [("neha", "NPS this month: 41 (up from 36)."), ("kavya", "The checkout fixes helped?")]),
    ("product", [("neha", "Adding a 'skip a day' button is the top request this week.")]),
    ("product", [("neha", "Ops asked for a printable kitchen prep list per area."), ("arjun", "Can export from orders, I'll scope it.")]),
    ("product", [("rohan", "Recs CTR is 7.2% this week."), ("neha", "Great, keep an eye on it after the price change.")]),
    ("product", [("neha", "Corporate plans are parked until Q4.")]),
    ("payments", [(BOT, "Daily settlement report is ready.")]),
    ("payments", [(BOT, "Daily settlement report is ready.")]),
    ("payments", [("neha", "Finance wants the refund report weekly instead of monthly."), ("arjun", "Sure, I'll schedule it.")]),
    ("infra", [("priya", "AWS bill is 8% up, mostly Redis. Will right-size next week.")]),
    ("infra", [("priya", "Rotating the DB password tonight, expect 1 minute of reconnects.")]),
    ("infra", [("priya", "Upgraded the k8s cluster to 1.33 on staging.")]),
    ("incidents", [("kavya", "Menu images slow in Pune for 10 min, CDN issue on their side, resolved.")]),
    ("dm-arjun-priya", [("arjun", "Lunch?"), ("priya", "10 min")]),
    ("dm-arjun-priya", [("priya", "Coffee run, want anything?"), ("arjun", "Cold coffee pls")]),
]
NOISE_TICKETS = [
    ("WEB", "kavya", "Menu grid jumps when images load"), ("WEB", "kavya", "Address form loses state on back"),
    ("WEB", "kavya", "Dark mode contrast on price tags"), ("WEB", "kavya", "Add order history page"),
    ("WEB", "kavya", "Checkout spinner never stops on timeout"), ("ORD", "arjun", "Export kitchen prep list"),
    ("ORD", "arjun", "Order cancel window"), ("ORD", "arjun", "Orders API pagination"),
    ("PAY", "arjun", "Weekly refund report"), ("PAY", "arjun", "Show UPI handle on receipts"),
    ("REC", "rohan", "Weekly retrain job"), ("REC", "rohan", "Cold-start recs for new users"),
    ("REC", "rohan", "ETA error dashboard"), ("REC", "rohan", "Add weather to ETA features"),
    ("INF", "priya", "Right-size Redis"), ("INF", "priya", "Upgrade k8s to 1.33"),
    ("INF", "priya", "Tag all AWS resources"), ("INF", "priya", "Status page for customers"),
    ("PRD", "neha", "Write skip-a-day spec"), ("PRD", "neha", "Corporate plans discovery"),
    ("PRD", "neha", "Onboarding funnel analysis"), ("WEB", "kavya", "Storybook for shared components"),
]
NOISE_SESSIONS = [
    ("kavya", "web/menu/MenuGrid.tsx", "Lazy-load images in MenuGrid"), ("kavya", "web/lib/api.ts", "Typed API client errors"),
    ("kavya", "web/checkout/CheckoutPage.tsx", "Address autocomplete"), ("arjun", "api/orders/service.py", "Orders status filter"),
    ("arjun", "api/subscriptions/billing.py", "Invoice email template"), ("arjun", "api/auth/tokens.py", "Login rate limiting"),
    ("rohan", "ml/recommend/model.py", "Weekly retrain schedule"), ("rohan", "ml/eta/predict.py", "Rain feature for ETA"),
    ("priya", "infra/terraform/main.tf", "Tag all terraform resources"), ("priya", ".github/workflows/deploy.yml", "Deploy status to chat"),
    ("priya", "infra/backup/db_backup.yaml", "30 day backup retention"), ("rohan", "ml/recommend/features.py", "Cuisine embeddings"),
]


def workday(start="2026-04-01", end="2026-09-14"):
    a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    while True:
        d = a + timedelta(days=rnd.randint(0, (b - a).days))
        if d.weekday() < 5:
            return f"{d:%Y-%m-%d} {rnd.randint(10, 18):02d}:{rnd.choice(['05', '20', '35', '50'])}"


for who, title, files, rev in NOISE_PRS:
    pr(who, workday(), title, f"{title[0].upper()}{title[1:]}.",
       [(title, files)] + ([(f"{title}: tests", files)] if rnd.random() < 0.6 else []),
       reviews=[(rev, "APPROVED", rnd.choice(["LGTM", "Looks good.", "Nice, ship it.", "LGTM, one nit inline."]))] if rev else (),
       noise=True)
for who, (files, _) in OWN.items():  # trivia on your own files
    for _ in range(6):
        commit(who, workday(), rnd.choice(TRIVIA), [rnd.choice(files)], small=True)
# trivia traps: a trivial touch must NOT make someone a knower
commit("rohan", "2026-07-30 17:05", "fix typo in retry docstring", ["api/payments/retry.py"], small=True)
commit("arjun", "2026-09-03 12:20", "bump actions/checkout to v5", [".github/workflows/deploy.yml"], small=True)
commit("kavya", "2026-06-30 16:35", "fix typo", ["infra/terraform/main.tf"], small=True)
for space, msgs in NOISE_THREADS:
    thread(space, workday(), [(w, 3 * i, t) for i, (w, t) in enumerate(msgs)], noise=True)
for i, (proj, who, title) in enumerate(NOISE_TICKETS):
    done = rnd.random() < 0.8
    ticket(f"{proj}-{40 + i}", workday(), title, f"{title}.", who, rnd.choice(["neha", who]),
           status="Done" if done else "To Do", noise=True)
for who, path, title in NOISE_SESSIONS:
    session(who, workday(), re.sub(r"[^a-z]+", "-", title.lower()).strip("-"), title,
            [(f"{title}. Keep the change small.", f"Done: a small change in {path.split('/')[-1]}.", [(path, "", "# ...")])], noise=True)


# ══ CHECK: recompute knowers from the raw fixtures and compare to answer_key.json ═
def check():
    key = json.loads((OUT / "answer_key.json").read_text(encoding="utf-8"))
    cutoff = utc("2026-09-21 23:59")  # the state on the day of the dry run, before Meera
    trivial = re.compile(key["rules"]["trivial_commit_regex"], re.I)
    by_sha = {c["sha"]: c for c in commits}
    login = {f"{p}-tb": p for p in PEOPLE}
    company_spaces = {s for s, (_, kind, ext) in SPACES.items() if kind == "SPACE" and not ext}

    file_knowers, file_committers = {f: set() for f in FILES}, {f: set() for f in FILES}
    for c in commits:
        if c["commit"]["author"]["date"] <= cutoff and not trivial.match(c["commit"]["message"]):
            for f in c["files"]:
                file_knowers[f["filename"]].add(login[c["author"]["login"]])
                file_committers[f["filename"]].add(login[c["author"]["login"]])
    for p in pulls:
        touched = {f["filename"] for s in p["commits"] for f in by_sha[s]["files"]}
        for r in p["reviews"]:
            if r["submitted_at"] <= cutoff:
                for f in touched:
                    file_knowers[f].add(login[r["user"]["login"]])

    def participants(ref):
        kind, _, rid = ref.partition(":")
        if kind == "pr":
            p = next(p for p in pulls if p["number"] == int(rid))
            return {login[p["user"]["login"]]} | {login[r["user"]["login"]] for r in p["reviews"]}
        if kind == "thread":
            if rid.split("/")[1] not in company_spaces:  # company-only: no DMs, no external spaces
                return set()
            return {p for p, u in CHAT_ID.items() for m in messages if m["thread"]["name"] == rid and m["sender"]["name"] == u}
        if kind == "ticket":
            t = next(t for t in tickets if t["key"] == rid)
            return {t["fields"]["assignee"]["accountId"][4:]}
        if kind == "session":
            return {sessions[rid][0]}
        if kind == "doc":
            return {re.search(r"author: (\w+)@", docs[rid]).group(1)}

    def text(ref):
        kind, _, rid = ref.partition(":")
        if kind == "pr":
            p = next(p for p in pulls if p["number"] == int(rid))
            return " ".join([p["title"], p["body"]] + [r["body"] for r in p["reviews"]])
        if kind == "thread":
            return " ".join(m["text"] for m in messages if m["thread"]["name"] == rid)
        if kind == "ticket":
            t = next(t for t in tickets if t["key"] == rid)
            return t["fields"]["summary"] + " " + t["fields"]["description"]
        if kind == "session":
            return json.dumps(sessions[rid][1])
        if kind == "doc":
            return docs[rid]

    errors = []
    dec_knowers = {}
    for d in DEC.values():
        k = set().union(*(participants(r) for r in d["recorded_in"])) | set().union(*(file_committers[f] for f in d["about"]))
        dec_knowers[d["id"]] = k
        if not any(d["evidence"] in text(r) for r in d["recorded_in"]):
            errors.append(f"{d['id']}: evidence quote not found in any source")
    for d, want in key["decision_knowers"].items():
        if dec_knowers[d] != set(want):
            errors.append(f"{d}: knowers {sorted(dec_knowers[d])} != key {sorted(want)}")
    for f, want in key["file_knowers"].items():
        if file_knowers[f] != set(want):
            errors.append(f"{f}: knowers {sorted(file_knowers[f])} != key {sorted(want)}")

    knowers = {**{d: k for d, k in dec_knowers.items() if DEC[d]["status"] == "active"}, **file_knowers}
    for case, want in key["dry_runs"].items():
        leavers = set(case.split("+"))
        got = sorted(i for i, k in knowers.items() if k & leavers and not k - leavers)
        if got != sorted(want["agenda"]):
            errors.append(f"dry run {case}: agenda {got} != key {sorted(want['agenda'])}")
    learned = {i for kt in KT for i in kt["covered"]}
    learned |= {f["filename"] for p in pulls if p["user"]["login"] == "meera-tb" for s in p["commits"] for f in by_sha[s]["files"]}
    remaining = sorted(set(key["dry_runs"]["arjun+priya"]["agenda"]) - learned)
    if remaining != sorted(key["after_meera"]["remaining"]):
        errors.append(f"after Meera: {remaining} != key {sorted(key['after_meera']['remaining'])}")
    return errors


# ══ WRITE ═══════════════════════════════════════════════════════════════════
def dump(path, data):
    path = OUT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for d in ("github", "google_chat", "sessions", "docs"):
        shutil.rmtree(OUT / d, ignore_errors=True)
    dump("people.json", [dict(id=p, name=n, role=r, email=f"{p}@{DOMAIN}", github=f"{p}-tb", chat_user=CHAT_ID[p],
                              joined_at=j, resigned_at=rs, last_day=ld) for p, (n, r, j, rs, ld) in PEOPLE.items()])
    dump("files.json", dict(files=[dict(path=f, service=s) for f, s in FILES.items()],
                            service_depends_on=[dict(service=a, depends_on=b) for a, b in SERVICE_DEPENDS_ON]))
    dump("github/pulls.json", pulls)
    dump("github/commits.json", sorted(commits, key=lambda c: c["commit"]["author"]["date"]))
    dump("tickets.json", sorted(tickets, key=lambda t: t["fields"]["created"]))
    dump("google_chat/spaces.json", [dict(name=f"spaces/{s}", displayName=n, spaceType=k, externalUserAllowed=e)
                                     for s, (n, k, e) in SPACES.items()])
    dump("google_chat/messages.json", sorted(messages, key=lambda m: m["createTime"]))
    for sid, (_, lines) in sessions.items():
        (OUT / "sessions").mkdir(exist_ok=True)
        (OUT / "sessions" / f"{sid}.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    for path, body in docs.items():
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        (OUT / path).write_text(body, encoding="utf-8")
    dump("extractions.json", dict(decisions=list(DEC.values()), patterns=PATTERNS, incidents=INCIDENTS, research=RESEARCH,
                                  insights=INSIGHTS, external_sources=EXTERNAL_SOURCES, features=FEATURES))
    dump("kt_sessions.json", KT)
    (OUT / "timeline.md").write_text(
        "# TiffinBox timeline (generated by build.py, story events only; noise omitted)\n\n"
        "| When (IST) | Source | What | Records |\n|---|---|---|---|\n"
        + "".join(f"| {at} | {k} | {t.replace('|', '/')} | {', '.join(r)} |\n" for at, k, t, r in sorted(timeline)),
        encoding="utf-8")

    print(f"{len(commits)} commits, {len(pulls)} PRs, {sum(len(p['reviews']) for p in pulls)} reviews, "
          f"{len(tickets)} tickets, {len({m['thread']['name'] for m in messages})} chat threads "
          f"({len(messages)} messages), {len(sessions)} AI sessions, {len(docs)} docs")
    errors = check()
    print("\n".join(errors) or "answer key: OK")
    sys.exit(1 if errors else 0)
