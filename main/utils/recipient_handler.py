import hmac
from main.models import Recipient
from django.db.models import Q

_UNSET = object()

class RecipientHandler(object):

    def __init__(self, web_url=None, telegram_id=None, webhook_secret=_UNSET, current_webhook_secret=_UNSET):
        self.web_url = web_url
        self.telegram_id = telegram_id
        self.webhook_secret = webhook_secret
        self.current_webhook_secret = current_webhook_secret

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
            recipient = Recipient()
            recipient.web_url = self.web_url
            recipient.telegram_id = self.telegram_id
            if self.web_url and self.webhook_secret is not _UNSET:
                recipient.webhook_secret = self.webhook_secret or None
            recipient.save()
            return recipient, True
        if status is not None:
            recipient = status
            if self.web_url and self.webhook_secret is not _UNSET:
                # Require current secret to prove ownership before allowing rotation/clear
                if recipient.webhook_secret:
                    if self.current_webhook_secret is _UNSET or not hmac.compare_digest(
                        str(self.current_webhook_secret), str(recipient.webhook_secret)
                    ):
                        return recipient, False
                recipient.webhook_secret = self.webhook_secret or None
                recipient.save(update_fields=['webhook_secret'])
            return recipient, False
        return status, False
