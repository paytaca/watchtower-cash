from django.conf import settings
from django.db.models.signals import post_save
from main.tasks import client_acknowledgement
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from main.models import BlockHeight, Transaction
from django.utils import timezone
from main.utils import block_setter
from main.utils import check_wallet_address_subscription

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

@receiver(post_save, sender=BlockHeight)
def blockheight_post_save(sender, instance=None, created=False, **kwargs):
    if not created:
        if instance.transactions_count:
            if instance.currentcount == instance.transactions_count:
                BlockHeight.objects.filter(id=instance.id).update(processed=True, updated_datetime=timezone.now())
    if created:
        # Queue to "PENDING-BLOCKS"
        block_setter(instance.number)

@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance=None, created=False, **kwargs):
    subscription = check_wallet_address_subscription(instance.address)
    if subscription.exists() and not instance.acknowledged:
        client_acknowledgement.delay(instance.id)
