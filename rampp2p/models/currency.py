from django.db import models
from .payment import PaymentType
from .peer import Peer

class FiatCurrency(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    symbol = models.CharField(max_length=3, unique=True, db_index=True)
    payment_types = models.ManyToManyField(PaymentType, related_name='payment_currency')
    
    cashin_blacklist = models.ManyToManyField(Peer, related_name='cashin_currency_blacklist', blank=True)
    cashin_whitelist = models.ManyToManyField(Peer, related_name='cashin_currency_whitelist', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
       return self.symbol
    
    class Meta:
        ordering = ['name', 'symbol']

class CryptoCurrency(models.Model):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
       return self.symbol