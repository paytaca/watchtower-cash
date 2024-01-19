import logging
import requests
import typing
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

from main.models import Subscription
from main.tasks import send_telegram_message

from smartbch.models import (
    TransactionTransfer,
    TransactionTransferReceipientLog,
)


LOGGER = logging.getLogger(__name__)


def __assert_instance(obj, types):
    assert isinstance(obj, types), f"Expected {obj} to be type {types}, {type(obj)}"


def send_transaction_transfer_notification_to_subscriber(
    subscription:Subscription,
    tx_transfer_obj:TransactionTransfer
) -> (TransactionTransferReceipientLog, typing.Optional[str]):
    """
        Sends the TransactionTransfer details to Subscription's recipient/s
    
    Parameters
    ------------
        subscription: main.models.Subscription
        tx_transfer_obj: smartbch.models.TransactionTransfer

    Return
    ------------
        (log, error): tuple
            log: smartbch.models.TransactionTransferReceipientLog
                serves as map to check if nofitication is sent to subscriber.
                If not None, implies success
            error: str
                information for showing
                If not None, implies failure to send notification
    """

    __assert_instance(subscription, Subscription)
    __assert_instance(tx_transfer_obj, TransactionTransfer)

    recipient = subscription.recipient
    websocket = subscription.websocket

    # check if already sent successfully
    notification_log = TransactionTransferReceipientLog.objects.filter(
        subscription=subscription,
        transaction_transfer=tx_transfer_obj,
        sent_at__isnull=False
    )
    if notification_log.exists():
        return notification_log.first(), None

    data = tx_transfer_obj.get_subscription_data()

    remarks = []
    if recipient and recipient.valid:
        if recipient.web_url:
            LOGGER.info(f"Webhook call to be sent to: {recipient.web_url}")
            LOGGER.info(f"Data: {str(data)}")

            resp = requests.post(recipient.web_url, data=data)
            if resp.status_code == 200:
                remarks.append("Sent to web url.")
                LOGGER.info(
                    "ACKNOWLEDGEMENT SENT TX TRANSFER INFO : {0} TO: {1} DATA: {2}".format(
                        tx_transfer_obj.transaction.txid,
                        recipient.web_url,
                        str(data),
                    )
                )
            elif resp.status_code == 404 or resp.status_code == 522 or resp.status_code == 502:
                recipient.valid = False
                recipient.save()
                LOGGER.info(f"!!! ATTENTION !!! THIS IS AN INVALID DESTINATION URL: {recipient.web_url}")
            else:
                return f"unknown_web_url_response_status_code: {resp.status_code}", None

        if recipient.telegram_id:
            LOGGER.info(f"Sending telegram message for {tx_transfer_obj} to telegram({recipient.telegram_id})")
            message = ""
            if tx_transfer_obj.token_contract:
                message=f"""<b>WatchTower Notification</b> ℹ️
                    \n Address: {subscription.address.address}
                    \n Token: {tx_transfer_obj.token_contract.name}
                    \n Token Address: {tx_transfer_obj.token_contract.address}
                    \n Amount: {tx_transfer_obj.amount}
                    \nhttps://www.smartscout.cash/transaction/{tx_transfer_obj.transaction.txid}
                """
            else:
                message=f"""<b>WatchTower Notification</b> ℹ️
                    \n Address: {subscription.address.address}
                    \n Amount: {tx_transfer_obj.amount} BCH
                    \nhttps://www.smartscout.cash/transaction/{tx_transfer_obj.transaction.txid}
                """

            send_telegram_message(message, recipient.telegram_id)
            remarks.append("Sent to telegram.")


    if websocket:
        room_name = f"{subscription.address.address}"

        # send to websocket connections subscribed to address 
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"{room_name}", 
            {
                "type": "send_update",
                "data": data
            }
        )

        # send to websocket token connections subscribed to address and contract address
        if tx_transfer_obj.token_contract and tx_transfer_obj.token_contract.address:
            room_name += f"_{tx_transfer_obj.token_contract.address}"

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"{room_name}", 
                {
                    "type": "send_update",
                    "data": data
                }
            )
        remarks.append("Sent to websocket.")

    log, _ = TransactionTransferReceipientLog.objects.update_or_create(
        transaction_transfer=tx_transfer_obj,
        subscription=subscription,
        defaults={
            "sent_at": timezone.now(),
            "remarks": " ".join(remarks),
        }
    )

    return log, None
