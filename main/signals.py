from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from main.models import Transaction

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance=None, created=False, **kwargs):
    if created:
        block = instance.blockheight
        if block:
            allblocks = block.transactions_count + len(block.genesis)
            if allblocks == block.transactions.all().distinct('txid').count():
                block.processed = True
                block.save()