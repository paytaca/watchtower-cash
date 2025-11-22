from notifications.utils.send import send_push_notification_to_wallet_hashes, NotificationTypes
from django.conf import settings
from django.utils import timezone
from main.utils.broadcast import broadcast_to_engagementhub
from main.models import Transaction, WalletHistory
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def send_wallet_history_push_notification(wallet_history_obj):
    # Check transaction age - skip if older than 1 hour
    transaction_date = wallet_history_obj.tx_timestamp if wallet_history_obj.tx_timestamp else wallet_history_obj.date_created
    if transaction_date:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        if transaction_date < one_hour_ago:
            logger.warning(
                f"Skipping push notification for transaction {wallet_history_obj.txid}: "
                f"transaction is older than 1 hour (age: {timezone.now() - transaction_date})"
            )
            return None
    
    fiat_value = None
    decimals = 0
    if wallet_history_obj.cashtoken_ft:
        token = wallet_history_obj.cashtoken_ft
        token_name = settings.DEFAULT_TOKEN_DETAILS['fungible']['name']
        decimals = 0
        
        if token.info:
            token_name = token.info.symbol
            decimals = token.info.decimals
    else:
        token_name = wallet_history_obj.token.token_ticker or wallet_history_obj.token.name
        if token_name.lower() == "bch":
            token_name = "BCH"
        decimals = wallet_history_obj.token.decimals
        fiat_value = wallet_history_obj.fiat_value or wallet_history_obj.usd_value

    incoming = wallet_history_obj.amount >= 0
    extra = {
        "txid": wallet_history_obj.txid,
        "type": NotificationTypes.MAIN_TRANSACTION,
        "token_id": resolve_token_id_for_notifications(wallet_history_obj),
    }

    if incoming:
        # title = "Payment Received" if incoming else "Payment Sent"
        title = "Payment Received"
        if token_name.lower() == "bch":
            amount = abs(wallet_history_obj.amount)
        else:
            amount = abs(wallet_history_obj.amount) / (10 ** decimals)
        amount = f'{amount:.5f}'.rstrip('0').rstrip('.')
        # message = f"{'Received' if incoming else 'Sent'} {amount} {token_name}"
        message = f"Received {amount} {token_name}"
        if fiat_value and fiat_value.get('value', None):
            message += f" ({abs(fiat_value['value'])} {fiat_value['currency']})"

        broadcast_to_engagementhub({
            'title': title,
            'message': message,
            'wallet_hash': wallet_history_obj.wallet.wallet_hash,
            'notif_type': 'TR',
            'extra_data': parse_transaction_extra_data(wallet_history_obj),
            'date_posted': timezone.now().isoformat()
        })

        return send_push_notification_to_wallet_hashes(
            [wallet_history_obj.wallet.wallet_hash],
            message,
            title=title,
            extra=extra,   
        )

def send_wallet_history_push_notification_nft(wallet_history_obj):
    # Check transaction age - skip if older than 1 hour
    transaction_date = wallet_history_obj.tx_timestamp if wallet_history_obj.tx_timestamp else wallet_history_obj.date_created
    if transaction_date:
        one_hour_ago = timezone.now() - timedelta(hours=1)
        if transaction_date < one_hour_ago:
            logger.warning(
                f"Skipping push notification for NFT transaction {wallet_history_obj.txid}: "
                f"transaction is older than 1 hour (age: {timezone.now() - transaction_date})"
            )
            return None
    
    transaction = Transaction.objects.filter(
        txid=wallet_history_obj.txid,
        cashtoken_nft_id__isnull=False
    )

    if transaction.exists() and wallet_history_obj.amount >= 0:
        title = 'NFT Received'
        message = f'Received {transaction.get().cashtoken_nft.info.name}'
        extra = {
            "txid": wallet_history_obj.txid,
            "type": NotificationTypes.MAIN_TRANSACTION,
            "token_id": wallet_history_obj.cashtoken_nft.token_id,
        }

        broadcast_to_engagementhub({
            'title': title,
            'message': message,
            'wallet_hash': wallet_history_obj.wallet.wallet_hash,
            'notif_type': 'NF',
            'extra_data': parse_transaction_extra_data(wallet_history_obj),
            'date_posted': timezone.now().isoformat()
        })

        return send_push_notification_to_wallet_hashes(
            [wallet_history_obj.wallet.wallet_hash],
            message,
            title=title,
            extra=extra
        )

def parse_transaction_extra_data(wallet_history):
    token_id = resolve_token_id_for_notifications(wallet_history)
    return f'{wallet_history.txid};{token_id}'

def resolve_token_id_for_notifications(wallet_history_obj):
    if wallet_history_obj.token and wallet_history_obj.token.tokenid != settings.WT_DEFAULT_CASHTOKEN_ID:
        return wallet_history_obj.token.tokenid

    if wallet_history_obj.cashtoken_ft:
        return wallet_history_obj.cashtoken_ft.token_id
    elif wallet_history_obj.cashtoken_nft:
        return wallet_history_obj.cashtoken_nft.token_id
