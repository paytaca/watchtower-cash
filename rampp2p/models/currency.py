from django.db import models
from .payment import PaymentType
from .peer import Peer

class FiatCurrency(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    symbol = models.CharField(max_length=3, unique=True, db_index=True)
    payment_types = models.ManyToManyField(PaymentType, related_name='payment_currency', blank=True)
    
    cashin_blacklist = models.ManyToManyField(Peer, related_name='cashin_currency_blacklist', blank=True)
    cashin_whitelist = models.ManyToManyField(Peer, related_name='cashin_currency_whitelist', blank=True)
    cashin_presets = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
       return self.symbol
    
    def get_cashin_presets(self):
        if self.cashin_presets:
            return list(map(int, self.cashin_presets.split(',')))
        return []

    def set_cashin_presets(self, presets):
        self.cashin_presets = ','.join(map(str, presets))
    
    class Meta:
        ordering = ['name', 'symbol']

class CryptoCurrency(models.Model):
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, unique=True)
    cashin_presets = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
       return self.symbol
    
    def get_cashin_presets(self):
        if self.cashin_presets:
            return list(map(int, self.cashin_presets.split(',')))
        return None

    def set_cashin_presets(self, presets):
        self.cashin_presets = ','.join(map(str, presets))