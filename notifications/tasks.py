import logging

from celery import shared_task

from notifications.models import OrderLiveActivityToken

logger = logging.getLogger(__name__)


@shared_task(queue="notifications__live_activity")
def push_order_live_activity(activity: dict, token_ids):
    """
    Deliver an order live-activity payload outside the request/status-save path.

    Parameters:
        activity (dict): normalized OrderLiveActivity payload
        token_ids (list[int]): registration ids to push to. Passing ids (instead
            of a queryset) keeps the task payload small and lets the task skip
            registrations that were removed before it ran.
    """
    from notifications.utils.live_activity import send_order_live_activity

    tokens = OrderLiveActivityToken.objects.filter(pk__in=token_ids or [])
    try:
        return send_order_live_activity(activity, tokens)
    except Exception as error:
        logger.exception(f"Failed to push order live activity: {error}")
        raise
