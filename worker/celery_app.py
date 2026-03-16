from celery import Celery
import os

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

app = Celery('creative_automation', broker=redis_url, backend=redis_url)

app.conf.task_routes = {'process_campaign': {'queue': 'campaigns'}}

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
