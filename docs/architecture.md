# Architecture

```mermaid
flowchart LR
  UI[Next.js dashboard] --> API[FastAPI /api/v1]
  API --> PG[(PostgreSQL)]
  API --> Q[(Qdrant)]
  API --> R[(Redis)]
  R --> W[Celery workers]
  W --> GH[GitHub clone]
  W --> PG
  W --> Q
  API --> LLM[Configurable LLM provider]
```

## Core data model

```mermaid
erDiagram
  USERS ||--o{ REPOSITORIES : owns
  REPOSITORIES ||--o{ REPOSITORY_BRANCHES : has
  REPOSITORIES ||--o{ CODE_CHUNKS : contains
  REPOSITORIES ||--o{ CONVERSATIONS : has
  CONVERSATIONS ||--o{ MESSAGES : contains
```

Code chunks retain repository, branch, path, language, symbol, imports, exports, commit hash, and line range. Qdrant payloads mirror filterable fields; PostgreSQL full-text search supports BM25-like keyword ranking.
