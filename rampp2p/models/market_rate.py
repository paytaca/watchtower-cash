from django.db import models

class MarketRate(models.Model):
    currency = models.CharField(max_length=10, unique=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.currency