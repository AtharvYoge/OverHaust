# Overhaust Architecture

## Overview

Overhaust is designed as a modular system with three main layers:
1. **User Application** (Web frontend)
2. **Local Context/Memory Engine** (Backend services)
3. **Autonomous Agent / Agent Connection Layer** (API and MCP)

## Core Components

### Memory Store (`packages/memory`)
- Persistent storage using SQLite
- Stores projects, memories, and knowledge extractions
- Supports different memory types (permanent, temporary, task, resolved, stale)
- Includes indexing for efficient retrieval
- Provides memory update, search, and cleanup functionality

### Knowledge Extraction & Context Engine (`packages/context`)
- Extracts structured knowledge from conversations, documents, code, etc.
- Uses pattern matching to identify project identity, architecture, decisions, issues, preferences
- Assembles context packages based on project knowledge and user tasks
- Filters relevant knowledge, files, decisions, and constraints
- Estimates token usage for context packages

### Token Estimation (`packages/tokenization`)
- Provides token estimation for various AI models
- Uses tiktoken for accurate counting
- Supports OpenAI-compatible models (with fallback to cl100k_base)
- Calculates token reduction between original and optimized text

### Autonomous Agent (`packages/agent`)
- Implements an AI agent that can:
  - Understand user tasks
  - Retrieve relevant project context
  - Update project memory with new learnings
  - Mark issues as resolved or memories as stale
  - Track action history for transparency
- Uses the memory store, context engine, and token estimator

### API Layer (`services/api`)
- RESTful API built with FastAPI
- Endpoints for:
  - Task understanding
  - Context retrieval
  - Memory updates
  - Knowledge search
  - Token estimation
  - Agent history
- Dependency injection for testability
- CORS enabled for frontend integration

### Frontend (`apps/web`)
- React + TypeScript + Vite application
- Demonstrates API usage
- Shows context retrieval and token estimation examples

## Data Flow

1. User interacts with the frontend or connects via API/MCP
2. Request goes to the backend API
3. API uses the autonomous agent to process the request
4. Agent understands the task and retrieves relevant context from memory store
5. Context engine assembles relevant knowledge and estimates tokens
6. Agent may update memory with new information
7. Response returned to user/frontend

## Security Considerations

- Input validation on all API endpoints
- No execution of arbitrary code
- File system access restricted to intended directories
- No logging of sensitive information
- Environment-based configuration for secrets

## Scalability

- Memory store uses SQLite for local-first operation
- Designed to migrate to PostgreSQL for production scaling
- Stateless API services can be horizontally scaled
- Context extraction and assembly can be optimized with caching

## Future Enhancements

- MCP server implementation for direct agent connections
- Additional knowledge extraction sources (PDFs, code analysis)
- Advanced NLP for better knowledge extraction
- Real tokenizers for different model providers
- User authentication and multi-tenant support
- Analytics dashboard for usage tracking
- Integration with specific AI agents (Cursor, Claude Code, etc.)
EOF