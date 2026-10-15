# KT Brain: System Architecture (high level)

_2026-10-15. Goes into the README as-is. To view it, paste the block into GitHub or https://mermaid.live._

```mermaid
flowchart LR
  subgraph SRC["Data sources"]
    GH["Public GitHub repo<br/>commits · PRs · reviews · issues"]
    UP["Web uploads<br/>docs .md/.pdf · Claude Code .jsonl"]
    FX["TiffinBox fixtures<br/>synthetic 6-month scene"]
  end

  subgraph LAPTOP["Developer laptop (local-first)"]
    LOGS["~/.claude/projects · ~/.codex/sessions<br/>company docs folder"]
    HOOK["Claude Code SessionEnd hook<br/>git post-commit hook"]
    CLI["ktbrain sync CLI<br/>redact secrets · extract metadata"]
    LOGS --> CLI
    HOOK --> CLI
  end

  subgraph API["FastAPI backend"]
    ING["Connectors<br/>github · docs · claude_code · codex · fixtures"]
    NORM["Normalize to timestamped events"]
    EXT["Extractor (Claude API)<br/>Decision · Pattern · Incident · Insight"]
    CHK["Chunker + embeddings"]
    DER["Derive<br/>KNOWS score · criticality"]
    Q["graph.py<br/>all Cypher lives here"]
    ING --> NORM
    NORM --> Q
    NORM --> EXT --> Q
    NORM --> CHK --> Q
    DER --> Q
  end

  subgraph DB["FalkorDB: the only database"]
    SYS["graph: system<br/>workspaces · tokens · ingest jobs"]
    TPL["graph: tiffinbox_template"]
    WS["graph: ws_{id}, one per workspace<br/>entities · edges · Chunk text<br/>vector + full-text indexes"]
    DRY["graph: dryrun_{id}<br/>temporary copy, deleted after"]
    TPL -- "GRAPH.COPY: load demo" --> WS
    WS -- "GRAPH.COPY: simulate departure" --> DRY
  end

  subgraph APP["Product surfaces"]
    UI["React SPA<br/>Sources · Radar · Simulate departure · Agenda<br/>Why-trace · Handover · Ask"]
    MCP["MCP server (stretch)<br/>why · who_knows · kt_agenda"]
  end

  GH --> ING
  UP --> ING
  FX --> ING
  CLI -- "extracted nodes + snippets<br/>workspace token" --> ING
  Q <--> DB
  UI <--> API
  MCP <--> Q
  USER(["Manager / new hire / judge"]) --> UI
  AGENT(["New hire's Claude Code"]) --> MCP
```

## Storage: one database
FalkorDB is the only database. There is no Postgres and no blob store.
- **Entities and edges**, including `KNOWS` and `LEARNED`, are graph nodes and relationships.
- **Text** is stored as `Chunk` nodes linked in order by `NEXT`, so any document can be rebuilt from its chunks. Vector and full-text indexes sit on those same nodes.
- **Session logs are slimmed before storing.** We keep prompts, assistant text, file paths, branch and timestamps, and drop tool output and file dumps, which make up most of a JSONL file's size.
- **Originals:** PDFs are dropped after text extraction. With the CLI, raw logs never leave the laptop.
- **App metadata** (workspaces, tokens, ingest jobs) lives in a small `system` graph.

Add an object store (S3/R2) only if keeping originals becomes a requirement, or RAM cost per tenant gets too high. Even then it holds files, not a second database.
