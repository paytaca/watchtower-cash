from main.models import Recipient
from django.db.models import Q

class RecipientHandler(object):

    def __init__(self, web_url=None, telegram_id=None):
        self.web_url = web_url
        self.telegram_id = telegram_id

    def find(self):
        if self.web_url and self.telegram_id:
            qs = Recipient.objects.filter(Q(web_url=self.web_url) & Q(telegram_id=self.telegram_id))
            if not qs.exists(): return 'create'
            return qs.first()
        if self.web_url:
            qs = Recipient.objects.filter(web_url=self.web_url)
            if not qs.exists(): return 'create'
            return qs.first()
        if self.telegram_id:
            qs = Recipient.objects.filter(telegram_id=self.telegram_id)
            if not qs.exists(): return 'create'
            return qs.first()
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
