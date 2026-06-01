import hmac

from main.models import Recipient
from main.utils.webhook import encrypt_webhook_secret, decrypt_webhook_secret
from django.db.models import Q

_UNSET = object()


class WebhookOwnershipRequired(Exception):
    """
    Raised when attempting to create a Recipient with a web_url that already
    has a webhook_secret registered. The caller must use POST /recipient/webhook-secret/
    with proof of ownership to add further recipients for that URL.
    """
    pass


class RecipientHandler(object):

    def __init__(self, web_url=None, telegram_id=None, webhook_secret=_UNSET):
        self.web_url = web_url
        self.telegram_id = telegram_id
        self.webhook_secret = webhook_secret

    def find(self):
        # Optimized: use .first() directly instead of .exists() + .first() to avoid two queries
        if self.web_url and self.telegram_id:
            recipient = Recipient.objects.filter(Q(web_url=self.web_url) & Q(telegram_id=self.telegram_id)).first()
            if not recipient: return 'create'
            return recipient
        if self.web_url:
            recipient = Recipient.objects.filter(web_url=self.web_url).first()
            if not recipient: return 'create'
            return recipient
        if self.telegram_id:
            recipient = Recipient.objects.filter(telegram_id=self.telegram_id).first()
            if not recipient: return 'create'
            return recipient
        return None
    
    def get_or_create(self):
        status = self.find()
        if status == 'create':
            # Security: if any existing recipient for this web_url already has a
            # webhook_secret, block creation of a new recipient sharing that URL.
            # Without this check an attacker could subscribe arbitrary addresses
            # with web_url=<victim> + telegram_id=<anything> to create unlimited
            # extra recipients and DDoS the victim's server with unsigned POSTs.
            if self.web_url and Recipient.objects.filter(
                web_url=self.web_url, webhook_secret__isnull=False
            ).exists():
                raise WebhookOwnershipRequired(
                    f"A recipient with web_url '{self.web_url}' already has a "
                    "webhook_secret. Provide the current secret via "
                    "POST /recipient/webhook-secret/ to register additional recipients."
                )
            recipient = Recipient()
            recipient.web_url = self.web_url
            recipient.telegram_id = self.telegram_id
            if self.web_url and self.webhook_secret is not _UNSET:
                plaintext = self.webhook_secret or None
                recipient.webhook_secret = encrypt_webhook_secret(plaintext) if plaintext else None
            recipient.save()
            return recipient, True
        if status is not None:
            recipient = status
            if recipient.webhook_secret:
                if self.webhook_secret is _UNSET:
                    raise WebhookOwnershipRequired(
                        f"A recipient with web_url '{recipient.web_url}' already has a "
                        "webhook_secret. Provide the current secret to subscribe additional "
                        "addresses for this URL."
                    )
                stored = decrypt_webhook_secret(recipient.webhook_secret)
                if len(self.webhook_secret) != len(stored) or not hmac.compare_digest(self.webhook_secret, stored):
                    raise WebhookOwnershipRequired(
                        f"Invalid webhook_secret for web_url '{recipient.web_url}'."
                    )
            return recipient, False
        return status, False
