from django.utils import timezone
from decimal import Decimal
from urllib.parse import urlencode

from main.models import (
    Wallet, Address, CashFungibleToken,
)
from notifications.utils.send import (
    send_push_notification_to_wallet_hashes,
    NotificationTypes,
)
from main.utils.broadcast import broadcast_to_engagementhub


def send_invoice_push_notification(instance, request):
    try:
        address = instance.merchant_data["address"]
    except (AttributeError, TypeError, KeyError):
        return

    wallet_hashes = Wallet.objects.filter(addresses__address=address) \
        .values_list("wallet_hash", flat=True) \
        .distinct()
    address_path = Address.objects.filter(address=address) \
        .values_list("address_path", flat=True) \
        .first()

    wallet_hashes = [*wallet_hashes]
    if not wallet_hashes:
        return

    payment_url_params = urlencode({
        "r": instance.get_absolute_uri(request),
    })
    extra = {
        "type": NotificationTypes.PAYMENT_REQUEST,
        "payment_url": f"bitcoincash:?{payment_url_params}",
    }

    if address_path:
        extra["use_address_path"] = address_path

    total_bch = abs(instance.total_bch)
    total_bch = f'{total_bch:.5f}'.rstrip('0').rstrip('.')

    title = "Payment Request"
    message = f"You have a payment request of {total_bch} BCH"

    broadcast_to_engagementhub({
        'title': title,
        'message': message,
        'wallet_hash': wallet_hashes,
        'notif_type': 'TR',
        'extra_data': extra['payment_url'],
        'date_posted': timezone.now().isoformat()
    })

    return send_push_notification_to_wallet_hashes(
        wallet_hashes,
        message,
        title=title,
        extra=extra,
    )

def resolve_invoice_notif_message(instance):
    outputs = instance.outputs.all()

    token_amounts = {}
    nft_outputs = []
    include_bch_amount_text = False
    for output in outputs:
        # if there is non cashtoken output or cashtoken output with sats grater than CT dust
        if not output.category or output.amount > 1000:
            include_bch_amount_text = True

        if output.token_amount:
            category = output.category
            token_amounts[category] = token_amounts.get(category, 0) + output.token_amount
        elif output.capability:
            nft_outputs.append(output)

    amounts_text = []
    if include_bch_amount_text:
        total_bch = abs(instance.total_bch)
        total_bch = f'{total_bch:.5f}'.rstrip('0').rstrip('.')
        amounts_text.append(f"{total_bch} BCH")

    token_amounts_text = []
    for category, amount in token_amounts.items():
        if len(token_amounts_text) >= 2:
            break

        formatted_amount = format_token_amount(category, amount)
        if formatted_amount:
            token_amounts_text.append(formatted_amount)

    other_token_count = len(token_amounts.keys()) - len(token_amounts_text) 
    if other_token_count > 0:
        token_amounts_text.append(f"{other_token_count} fungible {'token' if other_token_count == 1 else 'tokens'}")
    amounts_text += token_amounts_text

    if nft_outputs:
        nft_count = len(nft_outputs)
        amounts_text.append(f"{nft_count} " + ("NFT" if nft_count == 1 else "NFTs"))

    return f"You have a payment request of {join_with_and(amounts_text)}"


def format_token_amount(category, amount):
    ft_obj = CashFungibleToken.objects.filter(category=category).first()
    if not ft_obj or not ft_obj.info:
        return

    info = ft_obj.info
    if not info.symbol: return
    if info.decimals is None: return

    parsed_amount = Decimal(amount) / Decimal(10 ** info.decimals)
    parsed_amount = round(parsed_amount, info.decimals)
    return f"{parsed_amount} {info.symbol}"

def join_with_and(items):
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"
