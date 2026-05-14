from firebase_admin import messaging
from django.db.models import OuterRef, Exists
from push_notifications.models import GCMDevice, APNSDevice
from notifications.models import DeviceWallet

from .send_response import parse_gcm_response

ANDROID_NOTIF_KWARGS = [
    # part of messaging.AndroidNotification kwargs
    "title", "body", "mesasge",
    "icon", "color",
    "sound", "default_sound",
    "tag", "click_action",
    "body_loc_key", "body_loc_args",
    "title_loc_key", "title_loc_args",
    "channel_id", "image",
    "ticker", "sticky",
    "event_timestamp", "local_only",
    "priority",
    "vibrate_timings_millis", "default_vibrate_timings",
    "light_settings", "default_light_settings",
    "visibility",
    "notification_count",
]


APNS_KWARGS = [
    # part of push_notifications.apns._apns_send() func
    "priority", "collapse_id",

    # part of push_notifications.apns._apns_prepare() func
    "application_id", "badge", "sound", "category",
	"content_available", "action_loc_key", "loc_key", "loc_args",
	"extra", "mutable_content", "thread_id", "url_args",
]


def get_wallet_hashes_devices(wallet_hash_list):
    """
    Returns a query set of (GCMDevice, APNSDevice) that are linked to a list of wallet_hash

    Parameters:
            wallet_hash_list (List<str>): List of wallet hash
    Returns:
            gcm_devices, apns_devices (GCMDeviceQuerySet, APNSDeviceQuerySet): 
                a 2-tuple containing GCMDevices & APNSDevices, respectively
    """
    gcm_devices = GCMDevice.objects.filter(
        device_wallets__wallet_hash__in=wallet_hash_list,
        active=True,
    ).distinct()
    apns_devices = APNSDevice.objects.filter(
        device_wallets__wallet_hash__in=wallet_hash_list,
        active=True,
    ).distinct()
    return (gcm_devices, apns_devices)


def filter_device_queryset_by_wallet_index(queryset, wallet_hash_list, index):
    foreign_key_field = None
    if queryset.model == GCMDevice:
        foreign_key_field = "gcm_device_id"
    elif queryset.model == APNSDevice:
        foreign_key_field = "apns_device_id"

    subq = Exists(
        DeviceWallet.objects.filter(
            multi_wallet_index=index,
            wallet_hash__in=wallet_hash_list,
            **{foreign_key_field: OuterRef("id")},
        )
    )
    return queryset.filter(subq).distinct()


def parse_send_message_for_gcm(message, **kwargs):
    # gcm send_message functions filter out kwargs already
    if "priority" in kwargs and not isinstance(kwargs["priority"], str):
        if isinstance(kwargs["priority"], (float, int)) and kwargs["priority"] >= 10:
            kwargs["priority"] = "high"
        else:
            kwargs["priority"] = "normal"

    data = kwargs.get("extra")
    if not isinstance(data, dict):
        data = {}

    data = { key : str(value) for key, value in data.items() }

    # copied some kwargs in docs, not sure which are necessary
    # not yet sure how to serialize certain kwargs
    # https://firebase.google.com/docs/reference/admin/python/firebase_admin.messaging
    filtered_kwargs = { k: v for k,v in kwargs.items() if  k in ANDROID_NOTIF_KWARGS }
    message = messaging.Message(
        android=messaging.AndroidConfig(
            notification=messaging.AndroidNotification(
                body=message,
                **filtered_kwargs,
            )
        ),
        data=data,
        topic=kwargs.get("topic"),
        condition=kwargs.get("condition"),
    )

    return (message, {})

def parse_send_message_for_apns(message, **kwargs):
    if "title" in kwargs or "subtitle" in kwargs and not isinstance(message, dict):
        message = { "body": message }
        message["title"] = kwargs.pop("title", None)
        message["subtitle"] = kwargs.pop("subtitle", None)

    filtered_kwargs = { k: v for k,v in kwargs.items() if  k in APNS_KWARGS }
    if "priority" in filtered_kwargs and not isinstance(filtered_kwargs["priority"], int):
        priority = filtered_kwargs.pop("priority", None)
        if priority == "normal":
            filtered_kwargs["priority"] = 5
        elif priority == "high":
            filtered_kwargs["priority"] = 10

    return (message, filtered_kwargs)


def send_push_notification_to_wallet_hashes(wallet_hash_list, message, **kwargs):
    """
    Sends a push notification to GCMDevices & APNSDevices given a list of wallet hashes
        this function fails silently on the actual sending of push notifications; and
        simply returns an exception for each batch send response; this is to
        prevent stopping the send to ios devices if sending to gcm devices failes

    Parameters:
            wallet_hash_list (List<str>): List of wallet hash
            message (str): content of the push notification
            **kwargs: remaining key arguments passed to the `.send_message()` function
    Returns:
            gcm_send_message_response, apns_send_message_response (List, List): 
                a 2-tuple containing response after sending push notifications to gcm_devices & apns_devices 
                the response for each can be an exception
    """
    gcm_devices, apns_devices = get_wallet_hashes_devices(wallet_hash_list)

    # message & kwargs are parsed for each os since they each expect some different sets of parameters
    # NOTE: the following functions only filter out kwargs that are not used
    # will need a way to handle overlapping kwargs if they expect different types of values (e.g. "priority" above)
    gcm_message, gcm_kwargs = parse_send_message_for_gcm(message, **kwargs)
    apns_message, apns_kwargs = parse_send_message_for_apns(message, **kwargs)

    gcm_send_response = None
    apns_send_response = None
    try:
        gcm_wallets = gcm_devices.values_list("device_wallets__wallet_hash", "device_wallets__multi_wallet_index").distinct()
        print(f"GCM wallets: {gcm_wallets}")
        for wallet_hash, multi_wallet_index in gcm_wallets:
            if not isinstance(gcm_message.data, dict):
                gcm_message.data = {}

            gcm_message.data["wallet_hash"] = wallet_hash
            gcm_message.data["multi_wallet_index"] = str(multi_wallet_index)

            filtered_gcm_devices = filter_device_queryset_by_wallet_index(
                gcm_devices, wallet_hash_list, multi_wallet_index, 
            )

            print(f"GCM({multi_wallet_index}) | {filtered_gcm_devices}")
            if not filtered_gcm_devices: continue
            _gcm_send_response = filtered_gcm_devices.send_message(gcm_message, **gcm_kwargs)
            _gcm_send_response = parse_gcm_response(_gcm_send_response)

            if not isinstance(gcm_send_response, list): gcm_send_response = []
            if isinstance(_gcm_send_response, list):
                gcm_send_response += _gcm_send_response
            elif isinstance(getattr(_gcm_send_response, "responses", None), list):
                gcm_send_response += _gcm_send_response.responses
            else:
                gcm_send_response.append(_gcm_send_response)

    except Exception as exception:
        gcm_send_response = exception

    try:
        apns_wallets = apns_devices.values_list("device_wallets__wallet_hash", "device_wallets__multi_wallet_index").distinct()
        print(f"APNS wallets: {apns_wallets}")
        for wallet_hash, multi_wallet_index in apns_wallets:
            if "extra" not in apns_kwargs: apns_kwargs["extra"] = {}
            apns_kwargs["extra"]["wallet_hash"] = wallet_hash
            apns_kwargs["extra"]["multi_wallet_index"] = multi_wallet_index

            filtered_apns_devices = filter_device_queryset_by_wallet_index(
                apns_devices, wallet_hash_list, multi_wallet_index, 
            )

            print(f"APNS({multi_wallet_index}) | {filtered_apns_devices}")
            if not filtered_apns_devices: continue
            _apns_send_response = filtered_apns_devices.send_message(apns_message, **apns_kwargs)

            if not isinstance(apns_send_response, list): apns_send_response = []
            apns_send_response += _apns_send_response

    except Exception as exception:
        apns_send_response = exception

    return (
        gcm_send_response,
        apns_send_response,
    )


class NotificationTypes:
    MAIN_TRANSACTION = "transaction"
    SBCH_TRANSACTION = "sbch_transaction"

    PAYMENT_REQUEST = "payment_request"

    ANYHEDGE_OFFER_SETTLED = "anyhedge_offer_settled"
    ANYHEDGE_MATURED = "anyhedge_matured"
    ANYHEDGE_CONTRACT_CANCELLED = "anyhedge_contract_cancelled"
    ANYHEDGE_REQUIRE_FUNDING = "anyhedge_require_funding"
    ANYHEDGE_MUTUAL_REDEMPTION_UPDATE = "anyhedge_mutual_redemption_update"
    ANYHEDGE_MUTUAL_REDEMPTION_COMPLETE = "anyhedge_mutual_redemption_complete"
