# Developer guide

Run locally with Python 3.12 and Node 20, or use Docker Compose. The API creates tables at startup for the starter deployment. Production deployments should run Alembic migrations before the API.

`POST /api/v1/repositories` validates a public GitHub URL and queues indexing. Without a Celery worker, use the `POST /{id}/index` endpoint in a local process. The embedding and chat services degrade gracefully when no OpenAI key is configured, allowing metadata and keyword search tests to run offline.
