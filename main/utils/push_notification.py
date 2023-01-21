from notifications.utils.send import send_push_notification_to_wallet_hashes

def send_wallet_history_push_notification(wallet_history_obj):
    token_name = wallet_history_obj.token.token_ticker or wallet_history_obj.token.name
    if token_name.lower() == "bch":
        token_name = "BCH"

    fiat_value = wallet_history_obj.fiat_value
    incoming = wallet_history_obj.amount >= 0

    extra = { "txid": wallet_history_obj.txid }
    title = "Payment Received" if incoming else "Payment Sent"
    message = f"{'Received' if incoming else 'Sent'} {wallet_history_obj.amount} {token_name}"
    if fiat_value and fiat_value.get('value', None):
        message += f" ({fiat_value['value']} {fiat_value['currency']})"

    return send_push_notification_to_wallet_hashes(
        [wallet_history_obj.wallet.wallet_hash],
        message,
        title=title,
        extra=extra,   
    )
