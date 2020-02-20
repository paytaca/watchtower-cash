from django.db import models

class BchToken(models.Model):
    tokenid = models.CharField(max_length=200)
    confirmation_limit = models.IntegerField(default=0)

    def __str__(self):
        return self.tokenid

class Transaction(models.Model):
    txid = models.CharField(max_length=200)

    def __str__(self):
        return self.txid

class SlpAddress(models.Model):
    token = models.ForeignKey(BchToken, on_delete=models.CASCADE, related_name='slpaddress')
    address = models.CharField(max_length=200)
    transactions = models.ManyToManyField(Transaction) 

    class Meta:
        verbose_name = 'Slp Address'
        verbose_name_plural = 'Slp Addresses'
        
    def __str__(self):
        return self.address
