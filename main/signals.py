from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from main.models import Block, Transaction
from django.utils import timezone
from main.utils import block_setter


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

@receiver(post_save, sender=Block)
def block_post_save(sender, instance=None, created=False, **kwargs):
    if not created:
        if instance.transactions_count:
            if instance.currentcount == instance.transactions_count:
                Block.objects.filter(id=instance.id).update(processed=True, updated_datetime=timezone.now())
    if created:
        # Queue to "PENDING-BLOCKS"
        beg = Block.objects.first().number
        end = Block.objects.last().number
        
        _all = list(Block.objects.values_list('number', flat=True))

        for i in range(beg, end):
            if i not in _all:
                obj, created = Block.objects.get_or_create(number=i)
                                
        block_setter(instance.number)
        
