from django.db import models


class Report(models.Model):
    REASON_CHOICES = [
        ('inactive', 'Inactive account'),
        ('spammer', 'Spammer'),
        ('scammer', 'Scammer'),
    ]

    reporter = models.ForeignKey(
        'rampp2p.Peer',
        on_delete=models.CASCADE,
        related_name='filed_reports'
    )
    reported_peer = models.ForeignKey(
        'rampp2p.Peer',
        on_delete=models.CASCADE,
        related_name='reports_received'
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('reporter', 'reported_peer')

    def __str__(self):
        return f'{self.reporter.name} reported {self.reported_peer.name}'
