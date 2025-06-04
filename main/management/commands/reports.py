from django.core.management.base import BaseCommand, CommandError
from main.models import Project, Transaction, Wallet
from django.utils import timezone
from datetime import timedelta
import pytz


class Command(BaseCommand):
    help = "Generate reports on a given project"

    def add_arguments(self, parser):
        parser.add_argument("-p", "--project", type=str, default='paytaca')

    def handle(self, *args, **options):
        project_name = options['project']
        project = Project.objects.get(name__iexact=project_name)
        
        # Set Manila timezone
        manila_tz = pytz.timezone('Asia/Manila')
        now = timezone.now().astimezone(manila_tz)
        
        print('\n########### REPORTS ###########\n')
        print('Date: ' + now.strftime('%B %d, %Y %I:%M%p'))
        print('\n')
        
        print('WALLETS:\n')
        qs = Wallet.objects.filter(
            project=project,
            wallet_type='bch'
        )
        total_wallets = qs.all().count()
        print('All time: ' + str(total_wallets))

        month_diff = now - timedelta(days=30)
        wallets_month = qs.filter(date_created__date__gte=month_diff.date()).count()
        daily_average = round(wallets_month / 30)
        print('Last 30 days: {} (average {} daily)'.format(str(wallets_month), str(daily_average)))

        week_diff = now - timedelta(days=7)
        wallets_week = qs.filter(date_created__date__gte=week_diff.date()).count()
        daily_average = round(wallets_week / 7)
        print('Last 7 days: {} (average {} daily)'.format(str(wallets_week), str(daily_average)))

        yesterday = now - timedelta(days=1)
        wallets_yesterday = qs.filter(date_created__date=yesterday.date()).count()
        print('Yesterday: ' + str(wallets_yesterday))

        wallets_today = qs.filter(date_created__date=now.date()).count()
        print('Today: ' + str(wallets_today))

        print('\nTRANSACTIONS:\n')
        qs = Transaction.objects.filter(
            wallet__project=project
        )

        total_transactions = qs.order_by('txid').distinct('txid').count()
        print('All time: ' + str(total_transactions))

        month_diff = now - timedelta(days=30)
        transactions_month = qs.filter(date_created__date__gte=month_diff.date()).count()
        daily_average = round(transactions_month / 30)
        print('Last 30 days: {} (average {} daily)'.format(str(transactions_month), str(daily_average)))

        week_diff = now - timedelta(days=7)
        transactions_week = qs.filter(date_created__date__gte=week_diff.date()).count()
        daily_average = round(transactions_week / 7)
        print('Last 7 days: {} (average {} daily)'.format(str(transactions_week), str(daily_average)))

        yesterday = now - timedelta(days=1)
        transactions_yesterday = qs.filter(date_created__date=yesterday.date()).count()
        print('Yesterday: ' + str(transactions_yesterday))

        transactions_today = qs.filter(date_created__date=now.date()).count()
        print('Today: ' + str(transactions_today))

        print('\nDAILY ACTIVE USERS (DAU):\n')
        # Filter for BCH wallets only
        dau_qs = Wallet.objects.filter(
            project=project,
            wallet_type='bch',
            last_balance_check__isnull=False
        )

        # Calculate time ranges
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        # Last 30 days average DAU
        dau_month = dau_qs.filter(
            last_balance_check__gte=month_start,
            last_balance_check__lt=today_end
        ).count()
        daily_average = round(dau_month / 30)
        print('Last 30 days average: ' + str(daily_average))

        # Last 7 days average DAU
        dau_week = dau_qs.filter(
            last_balance_check__gte=week_start,
            last_balance_check__lt=today_end
        ).count()
        daily_average = round(dau_week / 7)
        print('Last 7 days average: ' + str(daily_average))

        # Yesterday's DAU
        dau_yesterday = dau_qs.filter(
            last_balance_check__gte=yesterday_start,
            last_balance_check__lt=yesterday_end
        ).count()
        print('Yesterday: ' + str(dau_yesterday))

        # Today's DAU
        dau_today = dau_qs.filter(
            last_balance_check__gte=today_start,
            last_balance_check__lt=today_end
        ).count()
        print('Today: ' + str(dau_today))

        print('\n########### END ###########\n')
