from django.core.management.base import BaseCommand, CommandError
from main.models import Project, Transaction, Wallet
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Generate reports on a given project"

    def add_arguments(self, parser):
        parser.add_argument("-p", "--project", type=str, default='paytaca')

    def handle(self, *args, **options):
        project_name = options['project']
        project = Project.objects.get(name__iexact=project_name)
        print('\n########### REPORTS ###########\n')
        
        print('WALLETS:\n')
        qs = Wallet.objects.filter(
            project=project,
            wallet_type='bch'
        )
        total_wallets = qs.all().count()
        print('All time: ' + str(total_wallets))

        month_diff = timezone.now() - timedelta(days=30)
        wallets_month = qs.filter(date_created__date__gte=month_diff).count()
        daily_average = round(wallets_month / 30)
        print('Last 30 days: {} (average {} daily)'.format(str(wallets_month), str(daily_average)))

        week_diff = timezone.now() - timedelta(days=7)
        wallets_week = qs.filter(date_created__date__gte=week_diff).count()
        daily_average = round(wallets_week / 7)
        print('Last 7 days: {} (average {} daily)'.format(str(wallets_week), str(daily_average)))

        yesterday = timezone.now() - timedelta(days=1)
        wallets_yesterday = qs.filter(date_created__date=yesterday.date()).count()
        print('Yesterday: ' + str(wallets_yesterday))

        wallets_today = qs.filter(date_created__date=timezone.now().date()).count()
        print('Today: ' + str(wallets_today))

        print('\nTRANSACTIONS:\n')
        qs = Transaction.objects.filter(
            wallet__project=project
        )

        total_transactions = qs.order_by('txid').distinct('txid').count()
        print('All time: ' + str(total_transactions))

        month_diff = timezone.now() - timedelta(days=30)
        transactions_month = qs.filter(date_created__date__gte=month_diff).count()
        daily_average = round(transactions_month / 30)
        print('Last 30 days: {} (average {} daily)'.format(str(transactions_month), str(daily_average)))

        week_diff = timezone.now() - timedelta(days=7)
        transactions_week = qs.filter(date_created__date__gte=week_diff).count()
        daily_average = round(transactions_week / 7)
        print('Last 7 days: {} (average {} daily)'.format(str(transactions_week), str(daily_average)))

        yesterday = timezone.now() - timedelta(days=1)
        transactions_yesterday = qs.filter(date_created__date=yesterday.date()).count()
        print('Yesterday: ' + str(transactions_yesterday))

        transactions_today = qs.filter(date_created__date=timezone.now().date()).count()
        print('Today: ' + str(transactions_today))

        print('\n########### END ###########\n')
