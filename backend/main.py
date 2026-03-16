import os
import litestar
from litestar import Litestar, post, get
from litestar.config.cors import CORSConfig
from litestar.exceptions import NotAuthorizedException
from celery_app import app as celery_app
import json

CMS_API_KEY = os.environ.get('CMS_API_KEY', 'admin-key')
SECRET_KEY = os.environ.get('SECRET_KEY', 'secret')


def validate_webhook_secret(request: litestar.Request):
    auth_header = request.headers.get('authorization')
    if not auth_header:
        raise NotAuthorizedException('Missing authorization')
    token = auth_header.replace('Bearer ', '')
    if token != SECRET_KEY:
        raise NotAuthorizedException('Invalid secret')
    return True


@post('/webhook/campaign')
async def campaign_webhook(data: dict, request: litestar.Request) -> dict:
    validate_webhook_secret(request)

    """
    # DEBUG
    with open('/app/cms-payload.json', 'w+') as f:
        json.dump(data, f, indent='\t')
    """

    keys = data.get('keys')
    if len(keys) == 0:
        return {'status': 'ignored'}
    else:
        assert len(keys) == 1, 'multiple ids, ignoring for now'
        id = keys[0]
        celery_app.send_task('process_campaign', args=[id])
        return {'status': 'queued', 'campaign_id': id}


@get('/health')
async def health() -> dict:
    return {'status': 'ok'}


is_production = os.environ.get('DEPLOYMENT') == 'production'
cors_config = CORSConfig(allow_origins=['*'])

app = Litestar(
    [campaign_webhook, health], debug=not is_production, cors_config=cors_config
)
