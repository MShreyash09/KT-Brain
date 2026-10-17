# Deploying KT Brain

| Piece | Where | Notes |
|---|---|---|
| UI (React, static) | **Vercel** | `frontend/vercel.json` sends `/api/*` on to Render |
| API (FastAPI, one worker) | **Render** web service | also runs the once-a-minute GitHub sync and radar watch |
| Database | **FalkorDB Cloud** | `FALKORDB_URL` on Render |
| Keep-alive | a cron ping every 10 min | Render's free tier sleeps after 15 min without traffic |

If any of this fails on the day, run everything on one machine instead: see **Run it locally** in the [README](README.md#run-it-locally).

## Topology

```mermaid
flowchart LR
  subgraph Users
    B(["Browser"])
    L(["Laptop<br/>ktbrain sync · ktbrain mcp"])
  end
  CRON(["cron-job.org<br/>every 10 min"])

  subgraph Vercel
    V["Static SPA (frontend/dist)<br/>rewrite /api/* → Render"]
  end

  subgraph Render["Render web service"]
    A["uvicorn app:app (1 worker)<br/>auto_sync loop every 60 s"]
  end

  F[("FalkorDB Cloud<br/>story graphs · ws_* company graphs<br/>kt_system: accounts, tokens, keys")]
  LLM["AI provider (Groq)"]
  GH["GitHub API"]

  B -- "HTTPS, cookie kt" --> V
  L -- "HTTPS, Bearer CLI token" --> V
  V -- "/api/* proxied" --> A
  CRON -- "GET /api/health" --> A
  A -- "FALKORDB_URL" --> F
  A --> LLM
  A --> GH
```

## Why `/api` goes through Vercel

Sign-in sets an `httponly`, `SameSite=Lax` cookie (`backend/app.py`), and the frontend calls relative `/api/...` paths. If the browser called `onrender.com` from `vercel.app` directly, the two sites would be cross-site: the cookie would never be sent and the backend has no CORS setup. The Vercel rewrite keeps everything on one origin, so it works without code changes.

```mermaid
sequenceDiagram
  participant B as Browser (your-app.vercel.app)
  participant V as Vercel rewrite
  participant R as Render (FastAPI)
  B->>V: POST /api/auth/login
  V->>R: POST https://your-service.onrender.com/api/auth/login
  R-->>V: 200, Set-Cookie: kt=... (no Domain)
  V-->>B: 200, Set-Cookie: kt=...  (stored for your-app.vercel.app)
  B->>V: GET /api/brain/ask?q=...  (cookie sent: same origin)
  V->>R: proxied with the cookie
  R-->>B: answer
```

## What happens when the backend starts

This runs on every Render deploy, and on every wake-up after the instance has slept.

```mermaid
sequenceDiagram
  participant R as Render (lifespan)
  participant F as FalkorDB Cloud
  R->>F: GRAPH.LIST
  alt first boot: story graphs missing
    R->>F: build tiffinbox_sep21 and tiffinbox_template from data/tiffinbox/
  end
  R->>F: kt_system indexes
  alt demo company missing
    R->>F: GRAPH.COPY tiffinbox_template → ws_tiffinbox, demo users (demo123)
  end
  loop every 60 s while the instance is awake
    R->>F: due daily GitHub syncs → ingest + derive
    R->>F: agent.watch per company → radar alerts + KT briefs
  end
```

The background loop runs only while the instance is awake. That's the second reason for the cron ping: without it, the daily sync and the radar watch stop whenever Render puts the service to sleep.

## Step by step

### 1. FalkorDB Cloud

1. Create an instance, in the same region you'll pick on Render. An Ask makes dozens of small queries, so the round trips between regions add up.
2. Copy its connection details into a URL: `redis://default:<password>@<host>:<port>`. Use `rediss://` if the console says TLS is required.
3. From your laptop, check it supports everything KT Brain uses (`GRAPH.COPY`, `algo.pageRank`, `algo.betweenness`, full-text indexes):

   ```bash
   cd backend
   FALKORDB_URL='redis://default:...@host:port' uv run python check_db.py      # PowerShell: $env:FALKORDB_URL = '...'
   ```

The database is reachable from the internet, and the password is the only thing protecting it. `kt_system` holds each company's AI key and GitHub token in plain text, so use the long generated password and never paste the URL anywhere public.

### 2. Render (the API)

New → **Web Service** → connect `MShreyash09/KT-Brain`.

| Setting | Value |
|---|---|
| Language | Python 3 |
| Branch | `main` |
| Root Directory | *leave empty*: the backend reads the fixtures from `data/tiffinbox/` next to `backend/` |
| Build Command | `pip install uv && cd backend && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt && pip install -r requirements.txt` |
| Start Command | `cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Instance type | Free works (512 MB) |

The build command installs the exact versions in `uv.lock`, into Render's own Python.

**Environment variables:**

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.11.11` (the version the backend is developed on) |
| `FALKORDB_URL` | the URL from step 1 |
| `LLM_KEY` | the server's AI key. Used by the public story, and by Ask and upload extraction for any company without its own key. The background KT briefs use it for the demo company only |
| `LLM_BASE`, `LLM_MODEL` | optional, default Groq `openai/gpt-oss-120b` |
| `GITHUB_TOKEN` | a fine-grained token with no permissions beyond reading public repos. Repo syncs use it when a company hasn't saved its own. Without it, GitHub allows 60 requests an hour per IP, shared by every judge on the server, which is about one small sync an hour |

Don't set `ALLOW_LOCAL_LLM`: it turns off the check that stops AI-provider URLs from pointing at private addresses.

Keep it at **one worker** (the start command above does). The public answer cache, the public-ask rate limit and the story cache live in process memory, and a second worker would run every sync and radar watch twice.

Deploy, then check: `https://your-service.onrender.com/api/health` → `{"ok":true}`. The first boot also builds the story graphs in FalkorDB Cloud, which takes a few seconds.

### 3. Vercel (the UI)

1. In `frontend/vercel.json`, replace `YOUR-SERVICE` with your Render host name, then commit and push:

   ```json
   { "rewrites": [{ "source": "/api/:path*", "destination": "https://your-service.onrender.com/api/:path*" }] }
   ```
2. Vercel → Add New → Project → import the repo.
   - **Root Directory:** `frontend`
   - **Framework preset:** Vite (detected)
   - **Build:** `npm run build`
   - **Output:** `dist`
   - No environment variables are needed.
3. Deploy, and open `https://your-app.vercel.app`.

### 4. Keep-alive cron

On [cron-job.org](https://cron-job.org) (free), or UptimeRobot, add a job:

- **URL:** `https://your-service.onrender.com/api/health`. Ping Render directly, not the Vercel URL, so it doesn't count against Vercel.
- **Schedule:** every 10 minutes. Render sleeps after 15 minutes without traffic.
- `/api/health` doesn't touch the database, so the ping costs nothing.

On the free tier, Render's 750 instance hours a month cover one service that's always awake (about 744 hours). A second free service kept awake would run out before the month ends. GitHub Actions `schedule` also works, but its runs are often late by 10 minutes or more, so it can miss the window.

### 5. Smoke test

- [ ] The home page shows the TiffinBox story. That means `/api/workspace` works through the rewrite.
- [ ] Sign in as `admin@tiffinbox.example` / `demo123` and stay signed in after a reload. If you get bounced back to sign-in, the cookie isn't coming back: check `vercel.json`.
- [ ] Ask a question and get an answer with cited paths. Without `LLM_KEY`, you get the evidence only.
- [ ] As `meera@tiffinbox.example`, create a CLI token, then run `claude mcp add ktbrain -- python /absolute/path/to/cli/ktbrain.py mcp --server https://your-app.vercel.app --token <token>`. `/mcp` in Claude Code should list 3 tools.
- [ ] Upload a doc close to the 8 MB limit. I couldn't confirm that Vercel's proxy accepts bodies that large. If it refuses, stay under its limit, or run `ktbrain sync` against the Render URL directly.
- [ ] Next day: the cron job's history shows 200s, and Render's logs show no cold starts.

## A judge tries their own repo

Each registered company gets its own graph, `ws_<company-id>`, so a judge's repo never touches TiffinBox. The demo
company refuses repo connections, because its admin login is shared.

```mermaid
flowchart LR
  J(["Judge"]) -- "#/register: company, name, email, password" --> C["new Company in kt_system<br/>graph ws_acme_3f2a"]
  C -- "Admin → Sources → GitHub repository" --> S["sync in the background<br/>GITHUB_TOKEN: 100 commits, 40 PRs"]
  S --> G[("ws_acme_3f2a<br/>commits · files · PRs · reviews<br/>KNOWS derived")]
  G --> R["Radar · dry runs · Ask<br/>Ask uses LLM_KEY"]
  D[("ws_tiffinbox + story graphs")] -.- X["untouched"]
```

## Before you share the URL

- [ ] **The demo company is public by design:** anyone can sign in as its admin with `demo123`. Don't save a personal AI key or GitHub token in the demo company's settings. Use `LLM_KEY` on Render, which the demo company falls back to and the UI never shows.
- [ ] Rotate any key that has appeared in a log or a terminal.
- [ ] On Groq's free tier (8,000 tokens a minute, about 2 asks a minute), any ask past the limit returns the evidence without an answer. For a live demo with many visitors, use a paid tier.

## Updating

Pushing to `main` redeploys both Render and Vercel. Graphs and accounts live in FalkorDB Cloud, so a redeploy keeps them.

If you change `data/tiffinbox/`, delete the two story graphs so the next start rebuilds them. Then restart the service in Render (Manual Deploy → Restart service), because the public story is cached for the life of the process.

```bash
cd backend
FALKORDB_URL='redis://default:...@host:port' uv run python -c "from graph import graph; [graph(n).delete() for n in ('tiffinbox_sep21', 'tiffinbox_template')]"
```

## Backups

Everything lives in FalkorDB Cloud: graphs, accounts, CLI tokens and saved keys. Check whether your plan takes snapshots. If it doesn't, the TiffinBox demo still rebuilds itself on the next boot, but registered companies and their data are lost if the instance is lost.
