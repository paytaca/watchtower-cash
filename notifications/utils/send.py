from push_notifications.models import GCMDevice, APNSDevice

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
    )
    apns_devices = APNSDevice.objects.filter(
        device_wallets__wallet_hash__in=wallet_hash_list,
    )
    return (gcm_devices, apns_devices)

def parse_send_message_for_gcm(message, **kwargs):
    # gcm send_message functions filter out kwargs already
    if "priority" in kwargs and not isinstance(kwargs["priority"], str):
        if isinstance(kwargs["priority"], (float, int)) and kwargs["priority"] >= 10:
            kwargs["priority"] = "high"
        else:
            kwargs["priority"] = "normal"
    
    return (message, kwargs)


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
        
        gcm_send_response = gcm_devices.send_message(gcm_message, **gcm_kwargs)
    except Exception as exception:
        gcm_send_response = exception

    try:
        apns_send_response = apns_devices.send_message(apns_message, **apns_kwargs)
    except Exception as exception:
        apns_send_response = exception

    return (
        gcm_send_response,
        apns_send_response,
    )


class NotificationTypes:
    MAIN_TRANSACTION = "transaction"
    SBCH_TRANSACTION = "sbch_transaction"

    ANYHEDGE_OFFER_SETTLED = "anyhedge_offer_settled"
    ANYHEDGE_MATURED = "anyhedge_matured"
    ANYHEDGE_REQUIRE_FUNDING = "anyhedge_require_funding"
