def send_wallet_history_push_notification(wallet_history_obj):
    token_name = wallet_history_obj.token.name
    if token_name.lower() == "bch":
        token_name = "BCH"

    gcm_devices = GCMDevice.objects.filter(
        device_wallets__wallet_hash=wallet_history_obj.wallet.wallet_hash,
    )
    apns_devices = APNSDevice.objects.filter(
        device_wallets__wallet_hash=wallet_history_obj.wallet.wallet_hash,
    )

    fiat_value = wallet_history_obj.fiat_value
    incoming = wallet_history_obj.amount >= 0

    extra = { "txid": wallet_history_obj.txid }
    title = "Payment Received" if incoming else "Payment Sent"
    message = f"{'Received' if incoming else 'Sent'} {wallet_history_obj.amount} {token_name}"
    if fiat_value and fiat_value.get('value', None):
        message += f" ({fiat_value['value']} {fiat_value['currency']})"

    gcm_send_response = gcm_devices.send_message(message, title=title, extra=extra)
    apns_send_response = apns_devices.send_message(message, title=title, extra=extra)
    return (gcm_send_response, apns_send_response)
