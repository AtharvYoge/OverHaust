# Changelog

## 0.2.0 (2026-08-17) — Core intelligence
- Conversation ingestion: markdown/plain/JSON/ChatGPT-export parsing, classification
  into 7 categories, dedupe, provenance, honest compression report.
- Project indexer: symbols/imports/exports/deps for 30+ text formats, path
  containment security, incremental diff/apply (add/modify/delete/rename).
- Layered relevance engine: exact phrase, keyword+plural+compound matching,
  metadata, intent boosts/demotes, importance, recency — behind a swappable
  `RelevanceEngine` interface.
- Context builder: relevance-driven selection with per-item explanations;
  minimum-useful-context tests.
- Agent runtime: goal-directed loop with terse action log, gap detection,
  second-pass retrieval, memory learning.
- Real MCP stdio server (9 tools) + stdio handshake test.
- Connection registry: local/API/MCP adapters available; Cursor/Windsurf/
  Claude Code config generators (coming_soon until IDE-validated).
- API: /ingest-conversation, /index-project, /connections endpoints.
- Perf: 1000-msg ingest 92ms; repo index 99ms; search 2.1ms; context 2.6ms.

## 0.1.0 (2026-08-17)
- Initial prototype + first engineering review fixes (security, IDs, CORS, FK).
