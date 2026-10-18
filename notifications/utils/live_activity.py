"""
Delivery of order live-activity pushes.

iOS receives APNs Live Activity pushes (`apns-push-type: liveactivity` on the
`<bundle-id>.push-type.liveactivity` topic). The `push_notifications` library
cannot express that payload, so it is sent through `apns2` directly, reusing the
same credentials configured for regular APNs pushes.

Android receives a data-only, high-priority FCM message that the app's
`PaytacaMessagingService` turns into an ongoing notification. It must NOT carry
an `AndroidNotification`, otherwise the system tray renders it instead of the
native ongoing notification.
"""
import json
import logging
import time

from django.conf import settings
from firebase_admin import messaging

from push_notifications.conf import get_manager

LOGGER = logging.getLogger("django")

APNS_LIVE_ACTIVITY_TOPIC_SUFFIX = ".push-type.liveactivity"
DEFAULT_APP_TOPIC = "com.paytaca.app"

# Must match `OrderLiveActivityAttributes.ContentState` on iOS.
CONTENT_STATE_KEYS = (
    "statusCode",
    "statusLabel",
    "stageIndex",
    "stageCount",
    "progress",
    "countdownAt",
    "countdownLabel",
    "isTerminal",
    "terminalType",
    "updatedAt",
)


class _LiveActivityPushType:
    """`apns2` (0.7.x) has no live-activity push type; `send_notification_async`
    only reads the `.value` attribute, so a tiny stand-in enum is enough."""

    value = "liveactivity"


class _LiveActivityPayload:
    """APNs payload whose keys live inside `aps` (apns2.Payload merges `custom`
    at the top level instead), plus the attributes apns2 reads to infer a push
    type."""

    alert = None
    badge = None
    sound = None

    def __init__(self, aps):
        self._aps = aps

    def dict(self):
        return {"aps": self._aps}


def _manager_flag(method_name, application_id=None, default=None):
    try:
        return getattr(get_manager(), method_name)(application_id)
    except Exception:
        return default


def get_live_activity_apns_topic(application_id=None):
    base = getattr(settings, "LIVE_ACTIVITY_APNS_TOPIC", None)
    if not base:
        base = _manager_flag("get_apns_topic", application_id)
    return f"{base or DEFAULT_APP_TOPIC}{APNS_LIVE_ACTIVITY_TOPIC_SUFFIX}"


def _apns_client(application_id=None):
    from apns2 import client as apns2_client
    from apns2 import credentials as apns2_credentials

    manager = get_manager()
    if manager.has_auth_token_creds(application_id):
        key_path, key_id, team_id = manager.get_apns_auth_creds(application_id)
        creds = apns2_credentials.TokenCredentials(key_path, key_id, team_id)
    else:
        creds = apns2_credentials.CertificateCredentials(
            manager.get_apns_certificate(application_id)
        )

    client = apns2_client.APNsClient(
        creds,
        use_sandbox=bool(_manager_flag("get_apns_use_sandbox", application_id, False)),
        use_alternative_port=_manager_flag(
            "get_apns_use_alternative_port", application_id, None
        ),
    )
    client.connect()
    return client


def build_apns_aps(activity: dict, event: str = "update") -> dict:
    """Build the `aps` dictionary for an ActivityKit update or end."""
    now = int(time.time())
    aps = {
        "timestamp": now,
        "event": event,
        "content-state": {key: activity.get(key) for key in CONTENT_STATE_KEYS},
    }

    if event == "end":
        # Keep the final content-state on screen before the activity dismisses.
        aps["dismissal-date"] = now + int(
            getattr(settings, "LIVE_ACTIVITY_DISMISSAL_DELAY", 4 * 60 * 60)
        )
    else:
        aps["stale-date"] = now + int(
            getattr(settings, "LIVE_ACTIVITY_STALE_DELAY", 60 * 30)
        )

    return aps


def send_live_activity_apns(token, aps: dict, application_id=None):
    client = _apns_client(application_id)
    payload = _LiveActivityPayload(aps)
    topic = get_live_activity_apns_topic(application_id)
    stream_id = client.send_notification_async(
        token,
        payload,
        topic=topic,
        expiration=0,
        push_type=_LiveActivityPushType(),
    )
    return client.get_notification_result(stream_id)


def send_live_activity_fcm(token, activity: dict, action=None, application_id=None):
    data = {
        "live_activity": "1",
        "payload": json.dumps(activity),
        "activity_id": str(activity.get("id", "")),
    }
    if action:
        data["action"] = action

    message = messaging.Message(
        data=data,
        token=token,
        android=messaging.AndroidConfig(priority="high"),
    )
    return messaging.send(message, app=get_manager().get_firebase_app(application_id))


def send_order_live_activity(activity: dict, tokens, application_id=None):
    """
    Push `activity` to every registered token and, once the order is terminal,
    drop the registrations so the server stops pushing.

    Parameters:
        activity (dict): normalized OrderLiveActivity payload
        tokens (QuerySet[OrderLiveActivityToken]): registrations for one order
        application_id (str): optional push-notifications application id
    """
    from notifications.models import OrderLiveActivityToken

    token_list = list(tokens)
    if not token_list:
        return []

    is_terminal = bool(activity.get("isTerminal"))

    results = []
    for token in token_list:
        result = None
        try:
            if token.platform == OrderLiveActivityToken.Platform.IOS:
                # ActivityKit: an `end` event renders the final content-state and
                # then dismisses the activity.
                event = "end" if is_terminal else "update"
                result = send_live_activity_apns(
                    token.token, build_apns_aps(activity, event=event),
                    application_id=application_id,
                )
                if isinstance(result, tuple) and result and result[0] == "Unregistered":
                    token.delete()
            else:
                # Android: the payload's `isTerminal` makes the native service
                # post a dismissible terminal notification, so no cancel action
                # is sent here.
                result = send_live_activity_fcm(
                    token.token, activity, application_id=application_id,
                )
        except Exception as error:
            # FCM raises `UnregisteredError` for stale tokens; drop those silently.
            if error.__class__.__name__ == "UnregisteredError":
                token.delete()
            else:
                LOGGER.exception(f"Failed to send order live activity push: {error}")
            result = error
        results.append((token.platform, result))

    if is_terminal:
        OrderLiveActivityToken.objects.filter(
            pk__in=[token.pk for token in token_list]
        ).delete()

    return results
