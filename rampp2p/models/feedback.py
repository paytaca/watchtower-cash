from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from .peer import Peer
from .order import Order
from .arbiter import Arbiter

class Feedback(models.Model):
    from_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='created_feedbacks', editable=False)
    to_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='received_feedbacks', editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='feedbacks', editable=False, db_index=True)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)

class ArbiterFeedback(models.Model):
    from_peer = models.ForeignKey(Peer, on_delete=models.PROTECT, related_name='arbiter_feedbacks', editable=False)
    to_arbiter = models.ForeignKey(Arbiter, on_delete=models.PROTECT, related_name='feedbacks', editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='arbiter_feedbacks', editable=False, db_index=True)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)