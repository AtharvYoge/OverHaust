# Technology Stack Decision

## Frontend
- **React + TypeScript + Vite**
  - Chosen for: Excellent developer performance, modern React features, fast builds, good ecosystem
  - Alternatives considered: Next.js (chosen Vite for simpler setup for prototype)
  
## Backend
- **Python FastAPI**
  - Chosen for: Excellent Python performance, automatic OpenAPI docs, async support, great for AI/ML tasks
  - Alternatives considered: Node.js/Express (chosen Python for better AI/ML library support)
  
## Database
- **SQLite** (for local storage)
  - Chosen for: Zero-configuration, file-based, ACID compliant, perfect for local-first approach
  - Production consideration: PostgreSQL (mentioned in ARCHITECTURE.md for future scaling)
  
## Agent & MCP
- **Python** with official MCP SDK
  - Chosen for: Consistency with backend, excellent AI/ML libraries
  
## Testing
- **Frontend**: Vitest + React Testing Library
- **Backend**: Pytest
- **E2E**: Playwright (considered for future)

## Additional Tools
- **TypeScript** for type safety across frontend
- **Docker** for containerization (optional for development)
- **ESLint & Prettier** for code quality

This stack supports:
- Local-first operation (SQLite file can be copied/moved)
- Easy maintenance
- Excellent ecosystem support
- Scalability path to PostgreSQL
- Strong AI/ML library availability (Python ecosystem)

