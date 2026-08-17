# Overhaust

Overhaust is an AI memory and efficiency layer that helps AI agents avoid reprocessing redundant information, making your AI credits go further.

## Core Idea

AI agents waste enormous amounts of usage because they repeatedly process information they already know or do not need. Overhaust creates a persistent AI memory and efficiency layer that remembers what matters and gives an AI agent only the information it actually needs.

## Features

- **Persistent Memory**: Stores project knowledge, decisions, and context locally
- **Smart Context Assembly**: Given a task, retrieves only relevant information
- **Token Estimation**: Estimates token usage to show potential savings
- **Autonomous Agent**: Can understand tasks, retrieve context, and update memory
- **REST API**: Full API for integration with AI agents and applications
- **Local-First**: Data stays on the user's machine by default

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) Docker

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/overhaust.git
cd overhaust

# Install Python dependencies
pip install -r requirements.txt  # We'll create this later

# Start the API server
cd services/api
PYTHONPATH=/Users/atharv11/Desktop/overhaust python main.py
```

The API will be available at http://localhost:8000

### Frontend Setup

```bash
cd apps/web
npm install
npm run dev
```

## API Documentation

Once the server is running, visit http://localhost:8000/docs for interactive API documentation.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for development guidelines.

## License

MIT