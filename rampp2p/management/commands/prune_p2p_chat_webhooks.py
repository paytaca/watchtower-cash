from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rampp2p.models import ChatWebhookDelivery


class Command(BaseCommand):
    help = 'Prune a bounded batch of replay records for expired P2P chat messages.'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000)

    def handle(self, *args, **options):
        if options['batch_size'] < 1:
            raise CommandError('batch-size must be positive')
        cutoff = timezone.now()
        ids = list(ChatWebhookDelivery.objects.filter(expires_at__lt=cutoff).order_by('expires_at').values_list('pk', flat=True)[:options['batch_size']])
        count, _ = ChatWebhookDelivery.objects.filter(pk__in=ids, expires_at__lt=cutoff).delete()
        self.stdout.write(f'{count} expired chat webhook replay records deleted')
