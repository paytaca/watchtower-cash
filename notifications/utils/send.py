from push_notifications.models import GCMDevice, APNSDevice


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

    # catching error for 
    gcm_send_response = None
    apns_send_response = None
    try:
        gcm_send_response = gcm_devices.send_message(message, **kwargs)
    except Exception as exception:
        gcm_send_response = exception

    try:
        apns_send_response = apns_devices.send_message(message, **kwargs)
    except Exception as exception:
        apns_send_response = exception

    return (
        gcm_send_response,
        apns_send_response,
    )
