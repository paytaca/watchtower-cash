from celery import shared_task
from django.utils import timezone
from rampp2p.models import Ad

import logging
logger = logging.getLogger(__name__)

@shared_task(queue='rampp2p__expire_ads')
def expire_ads():
    now = timezone.now()
    expired_ads = Ad.objects.filter(
        expires_at__lte=now,
        is_public=True,
        deleted_at__isnull=True
    )
    count = expired_ads.count()
    expired_ads.update(is_public=False, modified_at=now)
    logger.warning(f'Expired {count} ads')
