from django.core.management.base import BaseCommand, CommandError
from main.models import Transaction, BlockHeight


class Command(BaseCommand):
    help = "Use for checking missed deposit transactions"

    def add_arguments(self, parser):
        parser.add_argument("-c", "--confirmations", type=int)
                
    def handle(self, *args, **options):
        conf = options["confirmations"] if options["confirmations"] else 6

        if conf > 1:
            conf -= 1
            latest = BlockHeight.objects.order_by('-number').first()
            allowed_block = latest.number - conf
            transactions = Transaction.objects.filter(blockheight__number__lte=allowed_block).filter(spent=True)
            
            if transactions.count():
                delete_records = input(f'You are going to delete {transactions.count()} spent transactions. Are you sure? (Y/n)')
                if delete_records not in ['N', 'n', 'No', 'no', 'NO', 'nO']:
                    self.stdout.write(self.style.SUCCESS(f'Deleted {transactions.count()} spent transactions')) 
            else:
                self.stdout.write(self.style.WARNING(f'no spent transactions having {conf} confirmations')) 
        else:
            self.stdout.write(self.style.WARNING(f'0 conf cannot be deleted.')) 
