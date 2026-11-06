from celery import shared_task
from django.utils import timezone
from rampp2p.models import Ad
from rampp2p.utils.notifications import (
    UNAVAILABLE_REMINDER_INITIAL_DELAY,
    UNAVAILABLE_REMINDER_MAX_AGE,
    advance_ad_unavailable_reminders,
    clear_ad_unavailable_reminders,
    notify_ad_owner_ad_unavailable,
)

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
    expired_ads.update(
        is_public=False,
        modified_at=now,
        unavailable_reminder_started_at=None,
        unavailable_reminder_count=0,
        unavailable_reminder_next_at=None,
    )
    logger.info(f'Expired {count} ads')

@shared_task(queue='rampp2p__expire_ads')
def send_ad_unavailable_reminders():
    now = timezone.now()
    # Allow the final (day 7) reminder to still send if this task runs late.
    reminder_cutoff = (
        now - UNAVAILABLE_REMINDER_MAX_AGE - UNAVAILABLE_REMINDER_INITIAL_DELAY
    )
    ads = Ad.objects.filter(
        unavailable_reminder_next_at__lte=now,
        unavailable_reminder_started_at__gte=reminder_cutoff,
        deleted_at__isnull=True,
        is_public=True,
    ).select_related('owner', 'fiat_currency', 'crypto_currency')

    sent_count = 0
    for ad in ads:
        reason = ad.get_unavailable_reason()
        if reason is None:
            # The owner topped up since the last notification.
            clear_ad_unavailable_reminders(ad)
            continue

        if not notify_ad_owner_ad_unavailable(ad, reason, is_reminder=True):
            # Leave the schedule unchanged so the reminder is retried.
            continue

        advance_ad_unavailable_reminders(ad)
        sent_count += 1

    logger.info(f'Sent {sent_count} unavailable-ad reminders')
