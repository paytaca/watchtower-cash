from django.apps import apps
from notifications.utils.send import send_push_notification_to_wallet_hashes

def send_transaction_transfer_push_notification(tx_transfer_obj):
    Wallet = apps.get_model("main", "Wallet")

    recipient_wallet = Wallet.objects.filter(
        addresses__address=tx_transfer_obj.to_addr
    ).first()

    sender_wallet = Wallet.objects.filter(
        addresses__address=tx_transfer_obj.from_addr
    ).first()

    if recipient_wallet and sender_wallet and recipient_wallet.id == sender_wallet.id:
        return

    extra = {
        "txid": tx_transfer_obj.transaction.txid,
        "log_index": tx_transfer_obj.log_index,
    }

    response = { "sender": None, "recipient": None }

    is_nft = False
    if tx_transfer_obj.token_contract and tx_transfer_obj.token_contract.token_type == 721:
        is_nft = True

    # send to sender
    if sender_wallet:
        sender_title = "Payment Sent"
        sender_message = f"SmartBCH: Sent {tx_transfer_obj.normalized_amount} {tx_transfer_obj.unit_symbol}"
        if is_nft:
            sender_title = "NFT Sent"
            sender_message = f"SmartBCH: Sent NFT {tx_transfer_obj.token_contract.address}#{tx_transfer_obj.token_id} {tx_transfer_obj.unit_symbol}"

        response["sender"] = send_push_notification_to_wallet_hashes(
            [sender_wallet.wallet_hash],
            sender_message,
            title=sender_title,
            extra=extra,
        )

    if recipient_wallet:
        recipient_title = "Payment Received"
        recipient_message = f"SmartBCH: Received {tx_transfer_obj.normalized_amount} {tx_transfer_obj.unit_symbol}"
        if is_nft:
            recipient_title = "NFT Received"
            recipient_message = f"SmartBCH: Received NFT {tx_transfer_obj.token_contract.address}#{tx_transfer_obj.token_id} {tx_transfer_obj.unit_symbol}"

        response["recipient"] = send_push_notification_to_wallet_hashes(
            [recipient_wallet.wallet_hash],
            recipient_message,
            title=recipient_title,
            extra=extra,
        )

    return response
