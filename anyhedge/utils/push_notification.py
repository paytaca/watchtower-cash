from django.apps import apps
from ..models import HedgePositionOffer

def send_position_offer_settled(hedge_position_offer):
    GCMDevice = apps.get_model("push_notifications", "GCMDevice")
    APNSDevice = apps.get_model("push_notifications", "APNSDevice")

    gcm_devices = GCMDevice.objects.filter(
        device_wallets__wallet_hash=hedge_position_offer.wallet_hash,
    )
    apns_devices = APNSDevice.objects.filter(
        device_wallets__wallet_hash=hedge_position_offer.wallet_hash,
    )

    extra = {
        "address": hedge_position_offer.hedge_position.address,
    }
    title = "Anyhedge"
    if hedge_position_offer.position == HedgePositionOffer.POSITION_HEDGE:
        message = f"Hedge position offer of {hedge_position_offer.satoshis/10**8} BCH " + \
                    "is now ready for funding"
    elif hedge_position_offer.position == HedgePositionOffer.POSITION_LONG:
        message = f"Long position offer of {hedge_position_offer.satoshis/10**8} BCH " + \
                    "is now ready for funding" 

    gcm_send_response = gcm_devices.send_message(message, title=title, extra=extra)
    apns_send_response = apns_devices.send_message(message, title=title, extra=extra)
    return (gcm_send_response, apns_send_response)


def send_contract_matured(hedge_position_obj):
    GCMDevice = apps.get_model("push_notifications", "GCMDevice")
    APNSDevice = apps.get_model("push_notifications", "APNSDevice")

    response = { "hedge": None, "long": None }
    title = "Anyhedge"
    extra = { "address": hedge_position_obj.address }

    if hedge_position_obj.hedge_wallet_hash:
        message = f"Hedge position has matured:\n{hedge_position_obj.address}"
        hedge_gcm_devices = GCMDevice.objects.filter(
            device_wallets__wallet_hash=hedge_position_obj.hedge_wallet_hash,
        )
        hedge_apns_devices = APNSDevice.objects.filter(
            device_wallets__wallet_hash=hedge_position_obj.hedge_wallet_hash,
        )
        response["hedge"] = (
            hedge_gcm_devices.send_message(message, title=title, extra=extra),
            hedge_apns_devices.send_message(message, title=title, extra=extra),
        )

    if hedge_position_obj.long_wallet_hash:
        message = f"Long position matured:\n{hedge_position_obj.address}"
        long_gcm_devices = GCMDevice.objects.filter(
            device_wallets__wallet_hash=hedge_position_obj.long_wallet_hash,
        )
        long_apns_devices = APNSDevice.objects.filter(
            device_wallets__wallet_hash=hedge_position_obj.long_wallet_hash,
        )

        response["long"] = (
            long_gcm_devices.send_message(message, title=title, extra=extra),
            long_apns_devices.send_message(message, title=title, extra=extra),
        )

    return response        
