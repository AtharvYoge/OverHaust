# Development Guide

This guide covers local setup, testing, and common development workflows for Overhaust.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Git

## Repository layout

```
OverHaust-1/
├── apps/web/           # React demo UI (Vite + TypeScript)
├── packages/           # Core Python libraries (memory, context, agent, tokenization)
├── services/           # Runnable services (API, MCP server, ingestion, connections)
├── scripts/            # Demos and evaluation helpers
├── tests/evaluation/   # Scenario-based quality checks
└── data/               # Default SQLite database location (created at runtime)
```

## Backend setup

From the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m services.api.main
```

The API listens on port 8000 by default. Override with `OVERHAUST_API_PORT` (see `.env.example`).

Copy `.env.example` to `.env` and adjust paths if needed:

```bash
cp .env.example .env
```

## Frontend setup

```bash
cd apps/web
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## Running tests

### Backend (pytest)

From the repository root:

```bash
python3 -m pytest -v
python3 -m tests.evaluation.retrieval_benchmark   # Phase 2B paraphrase benchmark
```

This runs unit tests for memory, context, agent, ingestion, MCP, connections, and evaluation scenarios.

### Frontend

```bash
cd apps/web
npm run build
python3 ../../scripts/verify_frontend.py
```

### Demos

```bash
python3 scripts/demo.py              # In-process demo (no server required)
python3 scripts/e2e_demo.py          # Requires API server running
python3 scripts/evaluate.py          # Regenerates evaluation report
```

### MCP server

Run manually for IDE integration:

```bash
python3 -m services.mcp_server.server
```

Or use the config generators in `services/agent/connections.py` for Cursor, Claude Code, and Windsurf.

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OVERHAUST_DB_PATH` | SQLite database file path | `<repo>/data/overhaust_memory.db` |
| `OVERHAUST_API_BASE_URL` | API URL for clients/demos | `http://localhost:8000` |
| `OVERHAUST_API_PORT` | API listen port | `8000` |
| `OVERHAUST_DEFAULT_MODEL` | Token estimation model name | `gpt-4` |
| `OVERHAUST_EMBEDDINGS` | Enable hybrid semantic retrieval (`0`=off, `1`=on) | `0` |
| `OVERHAUST_EMBEDDING_MODEL` | fastembed model id | `BAAI/bge-small-en-v1.5` |
| `VITE_API_BASE_URL` | Frontend API base URL | `http://localhost:8000` |

See `.env.example` for the full list.

## Architecture docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — high-level overview
- [ARCHITECTURE_AUDIT.md](ARCHITECTURE_AUDIT.md) — detailed audit and extension points
- [NEXT_PHASE_PLAN.md](NEXT_PHASE_PLAN.md) — RAG, KSoR, and knowledge-graph roadmap
- [PHASE_2B_IMPLEMENTATION.md](PHASE_2B_IMPLEMENTATION.md) — hybrid RAG (Phase 2B)

## Conventions

- Keep changes local-first: no cloud dependencies unless explicitly planned.
- Prefer extending `RelevanceEngine` and ingestion pipelines over adding parallel retrieval paths.
- Preserve MCP tool names and REST API paths unless a breaking change is coordinated.
- Run `python3 -m pytest -v` before opening a pull request.
