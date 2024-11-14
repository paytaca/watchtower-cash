from django.db import models

class AppVersion(models.Model):
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web')
    ]

    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    latest_version = models.CharField(max_length=10)
    min_required_version = models.CharField(max_length=10)
    release_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.platform} - Latest: {self.latest_version}, Min Required: {self.min_required_version}"

class ServiceFee(models.Model):
    class FeeType(models.TextChoices):
        FIXED = 'FIXED'
        FLOATING = 'FLOATING'

    type = models.CharField(max_length=8, choices=FeeType.choices, default=FeeType.FLOATING.value)
    fixed_value = models.DecimalField(max_digits=18, decimal_places=8, default=1000, blank=True)
    floating_value = models.DecimalField(max_digits=18, decimal_places=8, default=0.5, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return super().__str__()
    
    @property
    def fee_value(self):
        if self.type == self.FeeType.FIXED:
            return self.fixed_value
        return self.floating_value
    
    def get_fee_value(self, trade_amount=None):
        if self.type == self.FeeType.FLOATING and trade_amount:
            bch_fee = trade_amount * (self.floating_value / 100)
            # convert value to sats
            sats_fee = bch_fee * 100000000 # 100,000,000 sats = 1 BCH
            return sats_fee
        return self.fixed_value