
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.timezone import now
from .models import Signature, MultisigTransactionProposal

@receiver([post_save, post_delete], sender=Signature)
def update_transaction_timestamp(sender, instance, **kwargs):
        MultisigTransactionProposal.objects.filter(id=instance.transaction_proposal.id).update(updated_at=now())

