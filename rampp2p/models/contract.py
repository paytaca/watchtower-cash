from django.db import models
from .order import Order

class Contract(models.Model):
    # order = models.OneToOneField(Order, on_delete=models.CASCADE, editable=False, unique=True)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, unique=True)
    address = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)