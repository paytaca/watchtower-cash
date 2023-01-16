from django.apps import apps

def send_transaction_transfer_push_notification(tx_transfer_obj):
    GCMDevice = apps.get_model("push_notifications", "GCMDevice")
    APNSDevice = apps.get_model("push_notifications", "APNSDevice")
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

    # send to sender
    if sender_wallet:
        sender_title = "Payment Sent"
        sender_message = f"SmartBCH: Sent {tx_transfer_obj.normalized_amount} {tx_transfer_obj.unit_symbol}"
        sender_gcm_devices = GCMDevice.objects.filter(
            device_wallets__wallet_hash=sender_wallet.wallet_hash,
        )
        sender_apns_devices = APNSDevice.objects.filter(
            device_wallets__wallet_hash=sender_wallet.wallet_hash,
        )
        sender_gcm_response = sender_gcm_devices.send_message(
            sender_message,
            title=sender_title,
            extra=extra,
        )
        sender_apns_response = sender_apns_devices.send_message(
            sender_message,
            title=sender_title,
            extra=extra
        )
        response["sender"] = (sender_gcm_response, sender_apns_response)

    if recipient_wallet:
        recipient_title = "Payment Received"
        recipient_message = f"SmartBCH: Received {tx_transfer_obj.normalized_amount} {tx_transfer_obj.unit_symbol}"
        recipient_gcm_devices = GCMDevice.objects.filter(
            device_wallets__wallet_hash=recipient_wallet.wallet_hash,
        )
        recipient_apns_devices = APNSDevice.objects.filter(
            device_wallets__wallet_hash=recipient_wallet.wallet_hash,
        )
        recipient_gcm_response = recipient_gcm_devices.send_message(
            recipient_message,
            title=recipient_title,
            extra=extra,
        )
        recipient_apns_response = recipient_apns_devices.send_message(
            recipient_message,
            title=recipient_title,
            extra=extra
        )
        response["recipient"] = (recipient_gcm_response, recipient_apns_response)

    return response
