from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from rampp2p.models import RegistrationChallenge, RegistrationRequestBucket


class Command(BaseCommand):
    help = 'Prune a bounded batch of expired P2P registration challenges and rate-limit buckets.'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000)

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        if batch_size < 1:
            raise CommandError('batch-size must be positive')
        cutoff = timezone.now() - timedelta(days=1)
        for model in (RegistrationChallenge, RegistrationRequestBucket):
            ids = list(model.objects.filter(expires_at__lt=cutoff).order_by('expires_at').values_list('pk', flat=True)[:batch_size])
            deleted, _ = model.objects.filter(pk__in=ids, expires_at__lt=cutoff).delete()
            self.stdout.write(f'{model.__name__}: {deleted} expired records deleted')
