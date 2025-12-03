from main.models import Recipient
from django.db.models import Q

class RecipientHandler(object):

    def __init__(self, web_url=None, telegram_id=None):
        self.web_url = web_url
        self.telegram_id = telegram_id

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
            recipient.save()
            return recipient, True
        if status is not None:
            return status, False
        return status, False
