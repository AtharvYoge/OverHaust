# Security

## Boundaries
- Local-first: all data stays in local SQLite (`data/overhaust_memory.db`).
- API binds localhost by default; CORS restricted to local dev origins.
- No arbitrary code execution anywhere in the codebase.
- No filesystem writes outside the DB file; agent has no shell access.

## Input handling
- API payloads validated via Pydantic; 1MB content cap on memory writes.
- SQL access is parameterized (sqlite3 placeholders) — no string interpolation.

## Secrets
- Never commit `.env`. See `.env.example` for the (currently zero) required secrets.
- No API keys are needed for the local prototype; tokenizer runs offline (tiktoken).

## Known gaps (documented, not hidden)
- No authentication on the API — bind to localhost only, or put it behind a reverse proxy with auth before exposing.
- Knowledge extraction is regex-based; it does not sanitize adversarial prompt-injection text stored in memories. Treat stored content as data, never as instructions.
- Token counts are estimates (tiktoken cl100k_base), not provider-billed usage.
