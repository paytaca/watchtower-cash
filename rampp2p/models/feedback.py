from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from .peer import Peer
from .order import Order

class Feedback(models.Model):
    from_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='created_feedbacks', editable=False)
    to_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='received_feedbacks', editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='feedbacks', editable=False)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)