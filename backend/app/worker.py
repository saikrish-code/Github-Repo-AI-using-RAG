from celery import Celery
from .core import settings
celery_app = Celery("reposage", broker=settings().redis_url, backend=settings().redis_url)

@celery_app.task(name="index_repository")
def index_repository(repository_id: str):
    from .indexer import index
    return index(repository_id)
