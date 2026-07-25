# Deployment guide

Use managed PostgreSQL, Redis, and Qdrant in production. Set a unique `JWT_SECRET`, restrict `CORS_ORIGINS`, use HTTPS behind Nginx or an ingress, and inject secrets from the platform secret manager. Scale Celery separately from API containers. Configure object storage for clone artifacts if indexing large repositories.
