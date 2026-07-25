# RepoSage

RepoSage is an AI-powered GitHub repository intelligence platform. It ingests a public repository, indexes source-aware code chunks, and answers questions with file-and-line citations.

## Quick start

1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (optional for local deterministic search).
2. Run `docker compose up --build`.
3. Open `http://localhost:3000`; the API is at `http://localhost:8000/docs`.

## Architecture

The Next.js dashboard calls a versioned FastAPI REST API. Repository cloning and indexing run as Celery jobs. PostgreSQL stores relational data and Qdrant stores versioned embeddings with filterable payloads. Search fuses PostgreSQL full-text keyword results with Qdrant semantic results using reciprocal-rank fusion, then builds a bounded cited context for the configured LLM provider.

See [docs/architecture.md](docs/architecture.md), [docs/development.md](docs/development.md), and [docs/deployment.md](docs/deployment.md).
