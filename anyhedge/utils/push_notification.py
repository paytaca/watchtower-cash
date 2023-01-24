from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes
from ..models import HedgePositionOffer

def send_position_offer_settled(hedge_position_offer):
    extra = {
        "address": hedge_position_offer.hedge_position.address,
        "type": NotificationTypes.ANYHEDGE_OFFER_SETTLED,
        "position": hedge_position_offer.position,
    }
    title = "Anyhedge"
    if hedge_position_offer.position == HedgePositionOffer.POSITION_HEDGE:
        message = f"Hedge position offer of {hedge_position_offer.satoshis/10**8} BCH " + \
                    "is now ready for funding"
    elif hedge_position_offer.position == HedgePositionOffer.POSITION_LONG:
        message = f"Long position offer of {hedge_position_offer.satoshis/10**8} BCH " + \
                    "is now ready for funding" 

    return send_push_notification_to_wallet_hashes(
        [hedge_position_offer.wallet_hash],
        message,
        title=title,
        extra=extra,
    )


def send_contract_matured(hedge_position_obj):
    response = { "hedge": None, "long": None }
    title = "Anyhedge"
    extra = {
        "address": hedge_position_obj.address,
        "type": NotificationTypes.ANYHEDGE_MATURED,
    }

    if hedge_position_obj.hedge_wallet_hash:
        message = f"Hedge position has matured:\n{hedge_position_obj.address}"
        extra["position"] = "hedge"
        response["hedge"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.hedge_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    if hedge_position_obj.long_wallet_hash:
        message = f"Long position matured:\n{hedge_position_obj.address}"
        extra["position"] = "long"
        response["long"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.long_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    return response        

def send_contract_require_funding(hedge_position_obj):
    if hedge_position_obj.funding_tx_hash:
        return

    response = { "hedge": None, "long": None }
    title = "Anyhedge"
    extra = {
        "address": hedge_position_obj.address,
        "type": NotificationTypes.ANYHEDGE_REQUIRE_FUNDING,
    }
    if not hedge_position_obj.hedge_funding_proposal and hedge_position_obj.hedge_wallet_hash:
        message = f"Hedge position require funding:\n{hedge_position_obj.address}"
        extra["position"] = "hedge"
        response["hedge"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.hedge_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    if not hedge_position_obj.long_funding_proposal and hedge_position_obj.long_wallet_hash:
        message = f"Long position matured:\n{hedge_position_obj.address}"
        extra["position"] = "long"
        response["long"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.long_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    return response
