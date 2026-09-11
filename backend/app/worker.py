from celery import Celery
from .core import settings
celery_app = Celery("reposage", broker=settings().redis_url, backend=settings().redis_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
    broker_connection_timeout=0.2,
)

@celery_app.task(name="index_repository")
def index_repository(repository_id: str):
    from .indexer import index
    return index(repository_id)
