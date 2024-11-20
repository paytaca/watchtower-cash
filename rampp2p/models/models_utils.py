from django.db import models
from datetime import date

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
