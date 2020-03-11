from django.core.management.base import BaseCommand, CommandError
from main.tasks import checktransaction


class Command(BaseCommand):
    help = "Use for checking missed deposit transactions"

    def add_arguments(self, parser):
        parser.add_argument('txn_ids', nargs='+', type=int)
        

    def handle(self, *args, **options):
        for txid in options['txn_ids']:
            checktransaction.delay(txid)
        self.stdout.write(self.style.SUCCESS('A task to check transaction has be deployed!')) 