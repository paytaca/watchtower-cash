from django.db import models
from django.utils.translation import gettext_lazy as _

class Order(models.Order):
  ad = models.ForeignKey('Ad', on_delete=models.PROTECT, editable=False)
  creator = models.ForeignKey('Peer', on_delete=models.PROTECT, editable=False)
  fiat_amount = models.FloatField(editable=False)
  locked_price = models.FloatField(editable=False)
  arbiter = models.ForeignKey('Arbiter', on_delete=models.PROTECT, editable=False)
  contract_address = models.CharField(max_length=50, blank=True, null=True, editable=False)
  chat_room = models.ForeignKey('ChatRoom', on_delete=models.PROTECT, editable=False)
  is_appealed = models.BooleanField(default=False)
  buyer_feedback = models.ForeignKey('PeerFeedback', on_delete=models.PROTECT, blank=True, null=True)
  seller_feedback = models.ForeignKey('PeerFeedback', on_delete=models.PROTECT, blank=True, null=True)
  arbiter_feedback = models.ForeignKey('ArbiterFeedback', on_delete=models.PROTECT, blank=True, null=True)
  created_at = models.DateTimeField(auto_now_add=True, editable=False)

  # TODO: should not be deletable