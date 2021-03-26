from django.core.management.base import BaseCommand, CommandError
from main.models import Transaction


class Command(BaseCommand):
    help = "Use for checking missed deposit transactions"

    def handle(self, *args, **options):
        transactions = Transaction.objects.filter(spent=True)
        if transactions.count():
            delete_records = input(f'You are going to delete {transactions.count()} spent transactions. Are you sure? (Y/n)')
            if delete_records not in ['N', 'n', 'No', 'no', 'NO', 'nO']:
                self.stdout.write(self.style.SUCCESS(f'Deleted {transactions.count()} spent transactions')) 
        else:
            self.stdout.write(self.style.WARNING('no spent transactions')) 