# Consolidation report

## Summary

This consolidation keeps the Hermes engineering baseline as the canonical implementation while preserving the original Overhaust product/design intent as a historical reference. The working system remains local-first and prototype-oriented, with portability fixes and actual project-context wiring prioritized over speculative Graphify work.

## Files/features imported from the legacy repo

The legacy GitHub repo was treated as a design/product reference, not as a direct implementation source.

Preserved historical intent and product framing:
- original Overhaust narrative and context-reduction positioning
- architecture intent and product goals
- local-first prototype posture
- historical design guidance about memory + relevance + compact context

Preserved in docs/legacy:
- docs/legacy/README.md
- docs/legacy/product-intent.md
- docs/legacy/architecture.md

## Hermes components retained

The following Hermes implementation areas remain the canonical engineering baseline:
- packages/memory
- packages/context
- packages/agent
- services/ingestion
- services/mcp_server
- services/agent
- tests/evaluation
- scripts/evaluation
- apps/web

## Files rewritten

- README.md: portable setup instructions, local-first configuration
- requirements.txt: explicit runtime dependency declarations
- apps/web/src/App.tsx: VITE_API_BASE_URL config instead of hardcoded localhost
- services/api/main.py: portable project root config and connection registry cleanup
- services/agent/connections.py: env-based API base URL and root-path defaults
- scripts/verify_frontend.py: repo-root-based resolution instead of machine-specific path
- scripts/e2e_demo.py: env-driven API base URL
- test_api.py: renamed helper function to avoid pytest collection as a test function
- services/agent/test_connections.py: removed machine-specific root assumptions
- packages/context/context_engine.py: connected actual project indexing to relevant_files output

## Files removed

No source files were deleted or reset. The consolidation kept the canonical repository intact and only preserved the original legacy product intent in docs/legacy.

## Architecture after consolidation

- Conversation + documents + code + project state
- Memory store for persistent project knowledge
- Relevance engine for ranking knowledge by task
- Project indexer for actual repository structure, files, imports, and symbols
- Context assembler for building real context packages
- API and MCP surfaces that delegate to the same underlying behavior where practical
- Local-first prototype runtime without production auth

## Portability fixes

- replaced hardcoded developer path assumptions with project-root resolution
- removed hardcoded localhost assumptions from scripts and frontend code
- introduced environment-configurable API base URL via OVERHAUST_API_BASE_URL and VITE_API_BASE_URL
- ensured generated IDE MCP configs use the active repo instead of a user-specific checkout

## Dependency fixes

- added the missing runtime dependency for the MCP stack: mcp
- kept the Python install reproducible with explicit package declarations
- separated runtime dependencies from test/verification tooling in the dependency story
- verified clean frontend install/build from apps/web with npm install and npm run build

## Project index → context integration

The primary functional fix was connecting real project indexing to context assembly.

Before:
- ContextAssembler returned synthetic placeholder filenames such as src/component-0.tsx

After:
- ContextAssembler queries the active project root
- ProjectIndexer scans the real repository
- File relevance is scored from actual path and symbol text matches
- ContextPackage.relevant_files contains real indexed files instead of placeholder data

## API/MCP changes

- API and connection registry now resolve a portable project root dynamically
- API connection defaults to OVERHAUST_API_BASE_URL
- IDE config generation and MCP configuration no longer assume a specific machine path
- compatibility behavior remains in place without forcing a broad rewrite

## Frontend changes

- frontend still keeps the Hermes demo UX
- backend URL is now loaded from VITE_API_BASE_URL with localhost as the default
- build validation succeeded in a clean environment: npm install && npm run build

## Tests executed

- pytest -q: 62 passed
- services/mcp_server/test_server.py: 6 passed
- frontend build: npm install && npm run build succeeded
- API smoke test: health endpoint and task analysis endpoint succeeded

## Test counts

- Python suite: 62 passed
- MCP suite: 6 passed
- Frontend build: 1 successful build
- API smoke: 2 endpoint checks passed

## Failures

No failing tests remained in the validation set used for this consolidation.

## Remaining known limitations

- Graphify/knowledge graph work is intentionally deferred to Phase 2
- production authentication remains out of scope for the prototype
- the current architecture remains local-first and not production-hardened
- real IDE end-to-end validation remains pending outside the local prototype environment

## Final status

The canonical Hermes engineering baseline remains in place, legacy product intent is preserved, portability issues are fixed, project-index context wiring is corrected, and the repo is ready for the following step after review.
