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

Both deliveries do network I/O (TLS handshake + HTTP requests), so this module is
only called from the `notifications.tasks.push_order_live_activity` task, never
inline in a request or a model signal. Tokens for one order are pushed within a
single APNs connection / FCM batch call.
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

# APNs reasons that mean the deployment itself is wrong (credentials or topic),
# as opposed to a single bad device. These are logged as errors because they
# would otherwise silently push into the void.
APNS_CONFIGURATION_ERRORS = frozenset(
    [
        "BadTopic",
        "DeviceTokenNotForTopic",
        "InvalidProviderToken",
        "MissingTopic",
        "TopicDisallowed",
    ]
)

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

    # Connecting is deferred to `connect()` (called by the send helpers), which
    # retries; this only builds the client.
    return apns2_client.APNsClient(
        creds,
        use_sandbox=bool(_manager_flag("get_apns_use_sandbox", application_id, False)),
        use_alternative_port=_manager_flag(
            "get_apns_use_alternative_port", application_id, None
        ),
    )


def _close_apns_client(client):
    """Best-effort teardown of the HTTP/2 connection (apns2 has no close())."""
    connection = getattr(client, "_connection", None)
    close = getattr(connection, "close", None)
    if callable(close):
        try:
            close()
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.debug(f"Failed to close APNs connection: {error}")


def _masked_token(token):
    """Push tokens are credentials; never write them whole to the logs."""
    token = str(token or "")
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def _apns_is_success(result):
    return result == "Success"


def _apns_is_unregistered(result):
    # apns2 returns ("Unregistered", timestamp) for expired activity tokens (410).
    return (
        isinstance(result, tuple) and bool(result) and result[0] == "Unregistered"
    )


def _log_apns_failure(token, result):
    reason = result[0] if isinstance(result, tuple) and result else result
    message = (
        f"Live activity APNs push rejected for token {_masked_token(token)}: {reason}"
    )
    if reason in APNS_CONFIGURATION_ERRORS:
        LOGGER.error(
            f"{message} (check LIVE_ACTIVITY_APNS_TOPIC / APNs credentials for "
            f"'{get_live_activity_apns_topic()}')"
        )
    else:
        LOGGER.warning(message)


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


def send_live_activity_apns_batch(aps_by_token: dict, application_id=None) -> dict:
    """
    Send one live-activity `aps` payload to many iOS tokens over a single
    connection (one TLS handshake for the whole order instead of one per token).

    Returns:
        dict: {token: result} where result is `"Success"`, a reason string, or
        an `("Unregistered", timestamp)` tuple.
    """
    if not aps_by_token:
        return {}

    from apns2 import client as apns2_client

    client = _apns_client(application_id)
    try:
        notifications = [
            apns2_client.Notification(token, _LiveActivityPayload(aps))
            for token, aps in aps_by_token.items()
        ]
        # `send_notification_batch` connects (with retries) and reads the
        # results of all streams, so a connection failure raises from here.
        return client.send_notification_batch(
            notifications,
            topic=get_live_activity_apns_topic(application_id),
            expiration=0,
            push_type=_LiveActivityPushType(),
        )
    finally:
        _close_apns_client(client)


def send_live_activity_apns(token, aps: dict, application_id=None):
    """Send to a single token. Prefer `send_live_activity_apns_batch`."""
    return send_live_activity_apns_batch(
        {token: aps}, application_id=application_id
    ).get(token)


def build_fcm_message(token, activity: dict, action=None):
    data = {
        "live_activity": "1",
        "payload": json.dumps(activity),
        "activity_id": str(activity.get("id", "")),
    }
    if action:
        data["action"] = action

    return messaging.Message(
        data=data,
        token=token,
        android=messaging.AndroidConfig(priority="high"),
    )


def send_live_activity_fcm(token, activity: dict, action=None, application_id=None):
    """Send to a single Android token. Prefer the batch path in
    `send_order_live_activity` when pushing to several devices."""
    message = build_fcm_message(token, activity, action=action)
    return messaging.send(message, app=get_manager().get_firebase_app(application_id))


def send_live_activity_fcm_batch(messages, application_id=None):
    """Send several FCM messages over one batch call.

    Returns one `messaging.SendResponse` per message; failures come back as
    responses rather than exceptions, so one bad token does not abort the batch.
    """
    if not messages:
        return []
    batch_response = messaging.send_each(
        messages, app=get_manager().get_firebase_app(application_id)
    )
    return batch_response.responses


def send_order_live_activity(activity: dict, tokens, application_id=None):
    """
    Push `activity` to every registered token of one order.

    Registrations are pruned when they are known to be dead (`Unregistered`) and,
    for terminal orders, only for the devices that actually received the `end`
    event: a failed terminal push keeps its registration so the client (or a
    later status change) can still dismiss the activity.

    Parameters:
        activity (dict): normalized OrderLiveActivity payload
        tokens (QuerySet[OrderLiveActivityToken]): registrations for one order
        application_id (str): optional push-notifications application id

    Returns:
        list[tuple[str, object]]: (platform, result) per token
    """
    from notifications.models import OrderLiveActivityToken

    token_list = list(tokens)
    if not token_list:
        return []

    is_terminal = bool(activity.get("isTerminal"))
    ios_tokens = [
        token
        for token in token_list
        if token.platform == OrderLiveActivityToken.Platform.IOS
    ]
    android_tokens = [
        token
        for token in token_list
        if token.platform != OrderLiveActivityToken.Platform.IOS
    ]

    # Tokens whose registration should be dropped. Kept in a set because the
    # same registration may be flagged more than once.
    prunable_pks = set()

    apns_results, apns_error = {}, None
    if ios_tokens:
        # ActivityKit: an `end` event renders the final content-state and then
        # dismisses the activity.
        event = "end" if is_terminal else "update"
        aps = build_apns_aps(activity, event=event)
        try:
            apns_results = send_live_activity_apns_batch(
                {token.token: aps for token in ios_tokens},
                application_id=application_id,
            )
        except Exception as error:
            apns_error = error
            LOGGER.exception(f"Failed to send order live activity APNs batch: {error}")

    fcm_responses, fcm_error = {}, None
    if android_tokens:
        try:
            responses = send_live_activity_fcm_batch(
                [build_fcm_message(token.token, activity) for token in android_tokens],
                application_id=application_id,
            )
            # Responses come back in request order; key by registration pk so a
            # token registered twice for the same order keeps its own result.
            fcm_responses = {
                token.pk: response
                for token, response in zip(android_tokens, responses)
            }
        except Exception as error:
            fcm_error = error
            LOGGER.exception(f"Failed to send order live activity FCM batch: {error}")

    results = []
    for token in token_list:
        if token.platform == OrderLiveActivityToken.Platform.IOS:
            result = apns_results.get(token.token, apns_error)
            if _apns_is_success(result):
                if is_terminal:
                    prunable_pks.add(token.pk)
            elif _apns_is_unregistered(result):
                prunable_pks.add(token.pk)
            elif apns_error is None:
                # A batch-level error was already logged with its traceback; only
                # per-token rejections need a line here.
                _log_apns_failure(token.token, result)
        else:
            # Android: the payload's `isTerminal` makes the native service post
            # a dismissible terminal notification, so no cancel action is sent.
            response = fcm_responses.get(token.pk)
            if response is None:
                result = fcm_error
            elif response.success:
                result = "Success"
                if is_terminal:
                    prunable_pks.add(token.pk)
            else:
                result = response.exception
                if isinstance(result, messaging.UnregisteredError):
                    # Stale FCM token: drop it silently.
                    prunable_pks.add(token.pk)
                else:
                    LOGGER.error(
                        f"Live activity FCM push rejected for token "
                        f"{_masked_token(token.token)}: {result}"
                    )
        results.append((token.platform, result))

    if prunable_pks:
        OrderLiveActivityToken.objects.filter(pk__in=prunable_pks).delete()

    return results
