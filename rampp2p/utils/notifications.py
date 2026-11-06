from notifications.utils.send import send_push_notification_to_wallet_hashes
from main.utils.broadcast import broadcast_to_engagementhub
from django.utils import timezone

from datetime import timedelta

from .utils import satoshi_to_bch

import logging
logger = logging.getLogger(__name__)

# Reminders are sent 1, 3, and 7 days after the ad becomes unavailable.
UNAVAILABLE_REMINDER_MAX_AGE = timedelta(days=7)
UNAVAILABLE_REMINDER_INITIAL_DELAY = timedelta(days=1)

def send_push_notification(recipients: list, message: str, extra: dict):
    logger.warning(f'Sending push notifications | recipients: {recipients} | message: {message} | extra: {extra}')
    notif_title = "P2P Exchange"
    send_push_notification_to_wallet_hashes(
        recipients,
        message,
        title=notif_title,
        extra=extra
    )

    broadcast_to_engagementhub({
        'title': notif_title,
        'message': message,
        'wallet_hash': recipients,
        'notif_type': 'RP',
        'date_posted': timezone.now().isoformat()
    })

def _ad_unavailable_message(ad, reason):
    if ad.trade_limits_in_fiat:
        symbol = ad.fiat_currency.symbol
        amount = ad.trade_amount_fiat
        trade_floor = ad.trade_floor_fiat
    else:
        symbol = ad.crypto_currency.symbol
        amount = satoshi_to_bch(ad.trade_amount_sats or 0)
        trade_floor = satoshi_to_bch(ad.trade_floor_sats or 0)

    if reason == "EMPTY":
        return f"Your ad #{ad.id} has no remaining {symbol} to trade. Top up to keep receiving orders."
    return f"Your ad #{ad.id} only has {amount} {symbol} left, below its minimum order of {trade_floor} {symbol}. Top up to keep receiving orders."

def notify_ad_owner_ad_unavailable(ad, reason, is_reminder=False):
    """Notifies the ad owner that the ad cannot accept orders. Returns True if sent."""
    try:
        message = _ad_unavailable_message(ad, reason)
        if is_reminder:
            message = f"Reminder: {message}"

        send_push_notification(
            [ad.owner.wallet_hash], message, extra={"ad_id": ad.id}
        )
        return True
    except Exception as err:
        logger.warning(f"Failed to notify owner of ad #{ad.id}: {err}")
        return False

def start_ad_unavailable_reminders(ad, reason):
    """Sends the initial notification and schedules the first reminder.

    The schedule is armed even if the initial push fails so the day-1 task
    retries it; count stays 0 so that retry keeps the initial wording.
    """
    sent = notify_ad_owner_ad_unavailable(ad, reason)
    now = timezone.now()
    type(ad).objects.filter(pk=ad.pk).update(
        unavailable_reminder_started_at=now,
        unavailable_reminder_count=0,
        unavailable_reminder_next_at=now + UNAVAILABLE_REMINDER_INITIAL_DELAY,
    )
    return sent

def advance_ad_unavailable_reminders(ad):
    """Advances the reminder schedule, stopping once the next delay exceeds max age."""
    count = ad.unavailable_reminder_count + 1
    # Offsets are 3, 7, 15, 31, ... days from started_at; the seed reminder is
    # day 1, set in start_ad_unavailable_reminders.
    next_at = ad.unavailable_reminder_started_at + timedelta(days=(2 ** (count + 1)) - 1)
    if next_at > ad.unavailable_reminder_started_at + UNAVAILABLE_REMINDER_MAX_AGE:
        next_at = None

    type(ad).objects.filter(pk=ad.pk).update(
        unavailable_reminder_count=count,
        unavailable_reminder_next_at=next_at,
    )

def clear_ad_unavailable_reminders(ad):
    type(ad).objects.filter(pk=ad.pk).update(
        unavailable_reminder_started_at=None,
        unavailable_reminder_count=0,
        unavailable_reminder_next_at=None,
    )
