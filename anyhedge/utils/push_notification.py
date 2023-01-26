from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes
from ..models import (
    HedgePositionOffer,
    MutualRedemption,
)

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


def send_mutual_redemption_proposal_update(hedge_position_obj, action="", position="", redemption_type=""):
    """
    Parameters:
        action ("proposed" | "cancelled" | "declined"): 
        position ("hedge" | "long"): which side proposed/cancelled/declined
        redemption_type (str): type of mutual redemption, see MutualRedemption model for options
            - we pass it as a parameter instead of accessing the instance since
              the mutual_redemption obj is deleted when "cancelled"/"declined".
    """

    title = "Anyhedge"
    extra = {
        "address": hedge_position_obj.address,
        "type": NotificationTypes.ANYHEDGE_MUTUAL_REDEMPTION_UPDATE,
    }

    if position != "hedge" and position != "long":
        return

    mutual_redemption_text = ""
    if redemption_type == MutualRedemption.TYPE_REFUND:
        mutual_redemption_text = "Refund"
    elif redemption_type == MutualRedemption.TYPE_EARLY_MATURATION:
        mutual_redemption_text = "Early maturation"
    elif redemption_type == MutualRedemption.TYPE_ARBITRARY:
        mutual_redemption_text = "Arbitrary mutual redemption"
    else:
        mutual_redemption_text = "Mutual redemption"

    if action == "proposed":
        message = f"{mutual_redemption_text} proposed by {position}"
    elif action == "cancelled":
        message = f"{mutual_redemption_text} proposal cancelled."
    elif action == "declined":
        message = f"{mutual_redemption_text} proposal declined by {position}."
    else:
        message = f"{mutual_redemption_text} proposal updated."

    message += f"\n{hedge_position_obj.address}"

    response = { "hedge": None, "long": None }
    if position == "long" and hedge_position_obj.hedge_wallet_hash:
        extra["position"] = "hedge"
        response["hedge"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.hedge_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    if position == "hedge" and hedge_position_obj.long_wallet_hash:
        extra["position"] = "long"
        response["long"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.long_wallet_hash],
            message,
            title=title,
            extra=extra,
        )

    return response


def send_mutual_redemption_completed(hedge_position_obj):
    title = "Anyhedge"
    extra = {
        "address": hedge_position_obj.address,
        "type": NotificationTypes.ANYHEDGE_MUTUAL_REDEMPTION_UPDATE,
    }

    response = { "hedge": None, "long": None }
    if hedge_position_obj.hedge_wallet_hash:
        message = f"Hedge position mutually redeemed:\n{hedge_position_obj.address}"
        extra["position"] = "hedge"
        response["hedge"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.hedge_wallet_hash],
            message,
            title=title,
            extra=extra,
        )
    if hedge_position_obj.long_wallet_hash:
        message = f"Long position mutually redeemed:\n{hedge_position_obj.address}"
        extra["position"] = "long"
        response["hedge"] = send_push_notification_to_wallet_hashes(
            [hedge_position_obj.long_wallet_hash],
            message,
            title=title,
            extra=extra,
        )