from django.core.management.base import BaseCommand, CommandError
from main.tasks import checktransaction


class Command(BaseCommand):
    help = "Use for checking missed deposit transactions"

    def add_arguments(self, parser):
        parser.add_argument('txn_ids', nargs='+', type=int)
        

    def handle(self, *args, **options):
        print(args)
        print(options)
        # if options['transaction']:
        #     checktransaction.delay()
        
        self.stdout.write(self.style.SUCCESS(f'aw')) 