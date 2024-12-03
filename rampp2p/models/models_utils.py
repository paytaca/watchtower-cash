from django.db import models
from datetime import date
from django.conf import settings

class AppVersion(models.Model):
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web')
    ]

    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    latest_version = models.CharField(max_length=10)
    min_required_version = models.CharField(max_length=10)
    release_date = models.DateField(default=date.today)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.platform} - Latest: {self.latest_version}, Min Required: {self.min_required_version}"
    
    class Meta:
        unique_together = ('platform', 'latest_version', 'min_required_version')

class TradeFee(models.Model):
    class FeeCategory(models.TextChoices):
        ARBITRATION = 'Arbitration Fee'
        SERVICE = 'Service Fee'

    class FeeType(models.TextChoices):
        FIXED = 'FIXED'
        FLOATING = 'FLOATING'

    category = models.CharField(max_length=30, choices=FeeCategory.choices, unique=True)
    type = models.CharField(max_length=8, choices=FeeType.choices, default=FeeType.FIXED.value)
    fixed_value = models.IntegerField(default=1000, blank=True)
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
            sats_fee = trade_amount * (self.floating_value / 100)
            if sats_fee < settings.DUST_LIMIT_CAP:
                sats_fee = self.fixed_value
            return int(sats_fee)
        return self.fixed_value

class FeatureToggle(models.Model):
    feature_name = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=False)

    def __str__(self):
        return self.feature_name