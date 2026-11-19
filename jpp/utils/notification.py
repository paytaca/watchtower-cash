from django.conf import settings
from django.utils import timezone
from urllib.parse import urlencode

from main.models import Wallet, Address
from notifications.utils.send import NotificationTypes
from main.utils.broadcast import broadcast_to_engagementhub


def get_authenticated_wallet(request):
    """Return the Wallet the request proved it holds, or None.

    "Proved" means the wallet-hash header plus the AuthToken key, which is what
    `WalletAuthentication` checks; it sets `is_authenticated` only after the key
    validates. A wallet-hash header on its own is unproven — anyone can send
    someone else's hash, and `WalletAuthentication` admits that as anonymous.
    """
    wallet = getattr(request, "user", None) if request is not None else None
    if isinstance(wallet, Wallet) and wallet.is_authenticated:
        return wallet
    return None


def send_invoice_notifications(instance, request, require_owner=True):
    """Notify the wallet that owns the address named in `merchant_data`.

    `merchant_data` is caller-supplied, so the address in it is not evidence of
    anything. Without the owner gate, any anonymous caller could create an
    invoice naming a victim's address and have this server push a payment
    request to that victim — with only the invoice's own name in the payload, so
    it reads as a genuine request.

    The gate means the notification only fires when the request authenticated as
    the wallet that holds the address. `require_owner=False` is for trusted
    callers only (the Django admin action), where the staff user is the
    authority and no wallet headers are present.

    `settings.JPP_PAYMENT_REQUEST_PUSH_ENABLED` is the kill switch and defaults
    to False: the whole push is off until the endpoint is proven safe, whatever
    the caller. Restoring it is a config flip, not a code change.
    """
    if not getattr(settings, "JPP_PAYMENT_REQUEST_PUSH_ENABLED", False):
        return {"success": False, "reason": "payment request push is disabled"}

    try:
        address = instance.merchant_data["address"]
    except (AttributeError, TypeError, KeyError):
        return {"success": False, "reason": "no merchant_data address"}

    if not isinstance(address, str):
        return {"success": False, "reason": "merchant_data address is not a string"}

    if require_owner:
        wallet = get_authenticated_wallet(request)
        if wallet is None:
            return {"success": False, "reason": "caller is not an authenticated wallet"}
        if not Address.objects.filter(address=address, wallet=wallet).exists():
            return {"success": False, "reason": "caller does not own merchant_data address"}
        wallet_hashes = [wallet.wallet_hash]
    else:
        wallet_hashes = [*Wallet.objects.filter(addresses__address=address)
            .values_list("wallet_hash", flat=True)
            .distinct()]

    if not wallet_hashes:
        return {"success": False, "reason": "no wallet owns merchant_data address"}

    address_path = Address.objects.filter(address=address) \
        .values_list("address_path", flat=True) \
        .first()

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

    result = broadcast_to_engagementhub({
        'title': title,
        'message': message,
        'wallet_hash': wallet_hashes,
        'notif_type': 'TR',
        'extra_data': extra['payment_url'],
        'date_posted': timezone.now().isoformat()
    })
    return dict(success=True, broadcast=result)
