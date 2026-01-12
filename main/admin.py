from django.contrib.auth.models import User, Group
from django.contrib.admin import DateFieldListFilter
from django.contrib import admin
from django import forms
from django.urls import path
from django.shortcuts import render
from django.contrib import messages
from decimal import Decimal
from main.models import *
from main.tasks import (
    client_acknowledgement,
    send_telegram_message,
    get_token_meta_data,
    get_bch_utxos,
    get_slp_utxos,
    parse_tx_wallet_histories
)
from main.management.commands.tx_fiat_amounts import get_tx_with_fiat_amounts

from dynamic_raw_id.admin import DynamicRawIDMixin
from django.utils.html import format_html
from django.conf import settings
import datetime
import json


admin.site.site_header = 'WatchTower.Cash Admin'
admin.site.site_title = 'WatchTower.Cash Admin'
REDIS_STORAGE = settings.REDISKV


def recent_actions_view(request):
    """Custom admin view for recent actions"""
    from django.contrib.admin.models import LogEntry
    
    # Get recent actions for the current user
    admin_log = LogEntry.objects.filter(user=request.user).select_related('content_type', 'user')[:50]
    
    context = {
        **admin.site.each_context(request),
        'title': 'Recent Actions',
        'admin_log': admin_log,
        'opts': {'app_label': 'admin', 'model_name': 'logentry'},
        'has_view_permission': True,
        'has_add_permission': False,
        'has_change_permission': False,
        'has_delete_permission': False,
    }
    
    return render(request, 'admin/recent_actions.html', context)


# Patch admin site to add recent actions URL
_original_get_urls = admin.site.get_urls

def get_urls_with_recent_actions(self):
    urls = _original_get_urls()
    custom_urls = [
        path('recent-actions/', self.admin_view(recent_actions_view), name='recent_actions'),
    ]
    return custom_urls + urls

admin.site.get_urls = get_urls_with_recent_actions.__get__(admin.site, type(admin.site))


class TxFiatAmountsForm(forms.Form):
    txid = forms.CharField(
        label="Transaction ID",
        max_length=64,
        help_text="Enter the transaction ID (txid) to analyze",
        required=True
    )
    currency = forms.CharField(
        label="Currency",
        max_length=10,
        initial="PHP",
        help_text="Enter the currency code (e.g., PHP, USD)",
        required=True
    )


class ClearMarketPricesForm(forms.Form):
    category = forms.CharField(
        label="Cashtoken Category",
        max_length=64,
        help_text="Enter the cashtoken category to clear market_prices for",
        required=True
    )
    dry_run = forms.BooleanField(
        label="Dry Run",
        required=False,
        initial=True,
        help_text="Preview what would be updated without actually making changes"
    )


class ClearWalletCachesForm(forms.Form):
    wallet_hash = forms.CharField(
        label="Wallet Hash",
        max_length=70,
        help_text="Enter the wallet hash to clear all caches for",
        required=True
    )


class ViewWalletBalanceHistoryForm(forms.Form):
    wallet_hash = forms.CharField(
        label="Wallet Hash",
        max_length=70,
        help_text="Enter the wallet hash to view balance and history",
        required=True
    )
    history_limit = forms.IntegerField(
        label="History Limit",
        initial=20,
        min_value=1,
        max_value=100,
        help_text="Number of recent history records to display (1-100)",
        required=True
    )

class TokenAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    search_fields = ['tokenid']
    actions = ['get_token_metadata']

    list_display = [
        'tokenid',
        'name',
        'token_ticker',
        'token_type'
    ]

    dynamic_raw_id_fields = [
        'nft_token_group'
    ]

    def get_query(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TokenAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        return qs.filter(subscriber__user=request.user)

    def get_token_metadata(self, request, queryset):
        for token in queryset:
            get_token_meta_data(token.tokenid)


class BlockHeightAdmin(admin.ModelAdmin):
    actions = ['process']
    ordering = ('-number',)

    list_display = [
        'number',
        'processed',
        'created_datetime',
        'updated_datetime',
        'transactions_count',
        'requires_full_scan'
        
    ]

    
    def process(self, request, queryset):
        for trans in queryset:
            pending_blocks = json.loads(REDIS_STORAGE.get('PENDING-BLOCKS'))
            pending_blocks.append(trans.number)
            pending_blocks = list(set(pending_blocks))
            BlockHeight.objects.filter(number=trans.number).update(processed=False)
            REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(pending_blocks))

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions



class TransactionAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    change_list_template = 'admin/main/transaction_changelist.html'
    
    search_fields = [
        'token__name',
        'cashtoken_ft__info__name',
        'cashtoken_nft__info__name',
        'source',
        'txid'
    ]
    
    dynamic_raw_id_fields = [
        'blockheight',
        'address',
        'token',
        'cashtoken_ft',
        'cashtoken_nft',
        'wallet'
    ]

    actions = [
        'resend_unacknowledged_transactions',
        'save_wallet_history'
    ]

    list_display = [
        'id',
        'txid',
        'index',
        'address',
        'project',
        'amount',
        'value',
        'source',
        'blockheight',
        'token',
        'cashtoken',
        'capability',
        'acknowledged',
        'spent',
        'date_created'
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('tx-fiat-amounts/', self.tx_fiat_amounts_view, name='main_transaction_tx_fiat_amounts'),
        ]
        return custom_urls + urls

    def tx_fiat_amounts_view(self, request):
        form = TxFiatAmountsForm()
        tx_data = None
        error = None
        assessment = None

        if request.method == 'POST':
            form = TxFiatAmountsForm(request.POST)
            if form.is_valid():
                txid = form.cleaned_data['txid'].strip()
                currency = form.cleaned_data['currency'].strip().upper()
                
                try:
                    tx_data = get_tx_with_fiat_amounts(txid, currency=currency)
                    
                    # Calculate gain/loss assessment for cashout
                    if tx_data and tx_data.get('outputs') and len(tx_data['outputs']) > 0:
                        total_input_amount = Decimal(str(tx_data.get('total_input_amount', 0) or 0))
                        
                        # First output is the cashout transaction
                        cashout_output = tx_data['outputs'][0]
                        cashout_amount = Decimal(str(cashout_output.get('amount', 0) or 0))
                        
                        # Second output is change (if exists)
                        change_amount = Decimal('0')
                        if len(tx_data['outputs']) > 1:
                            change_output = tx_data['outputs'][1]
                            change_amount = Decimal(str(change_output.get('amount', 0) or 0))
                        
                        # Net received = cashout amount (what merchant gets)
                        net_received = cashout_amount
                        
                        # Total output amount (cashout + change)
                        total_output_amount = Decimal(str(tx_data.get('total_output_amount', 0) or 0))
                        
                        # Calculate gain/loss only if we have valid input and output amounts
                        if total_input_amount > 0 and total_output_amount > 0 and cashout_amount is not None:
                            # Total gain/loss in fiat terms: total_output_amount - total_input_amount
                            total_gain_loss = total_output_amount - total_input_amount
                            
                            # Calculate cashout's portion of the gain/loss
                            # Percentage of total output that is cashout
                            cashout_percentage_of_output = float(cashout_amount) / float(total_output_amount)
                            
                            # Gain/loss for cashout = (cashout / total_output) * (total_output - total_input)
                            cashout_gain_loss = cashout_percentage_of_output * float(total_gain_loss)
                            
                            # Overall percentage based on total gain/loss
                            percentage = (float(total_gain_loss) / float(total_input_amount)) * 100
                            
                            # Calculate gain portion and charge (if gain)
                            gain_portion_of_cashout = None
                            gain_portion_percentage = None
                            charge_on_gain = None
                            if cashout_gain_loss > 0:
                                # It's a gain - charge 10% on the gain
                                gain_portion_of_cashout = cashout_gain_loss
                                charge_on_gain = cashout_gain_loss * 0.10
                                if cashout_amount > 0:
                                    gain_portion_percentage = (gain_portion_of_cashout / float(cashout_amount)) * 100
                            
                            # Calculate loss and reimbursement (if loss)
                            loss_percentage_over_inputs = None
                            reimbursement_amount = None
                            total_after_reimbursement = None
                            if cashout_gain_loss < 0:
                                # It's a loss - this is the amount to cover
                                loss_percentage_over_inputs = abs((cashout_gain_loss / float(total_input_amount)) * 100)
                                reimbursement_amount = abs(cashout_gain_loss)
                                # Total after reimbursement = cashout + reimbursement
                                total_after_reimbursement = float(cashout_amount) + reimbursement_amount
                            
                            # For display purposes, use total gain/loss
                            gain_loss = float(total_gain_loss)
                            
                            assessment = {
                                'total_input_amount': float(total_input_amount),
                                'cashout_amount': float(cashout_amount),
                                'change_amount': float(change_amount),
                                'net_received': float(net_received),
                                'gain_loss': float(total_gain_loss),  # Total gain/loss for display
                                'percentage': float(percentage),  # Percentage based on total gain/loss
                                'is_gain': cashout_gain_loss >= 0,  # Based on cashout's portion
                                'currency': currency,
                                'gain_portion_of_cashout': gain_portion_of_cashout,
                                'gain_portion_percentage': gain_portion_percentage,
                                'charge_on_gain': float(charge_on_gain) if charge_on_gain is not None else None,
                                'loss_percentage_over_inputs': loss_percentage_over_inputs,
                                'reimbursement_amount': reimbursement_amount,
                                'total_after_reimbursement': total_after_reimbursement,
                                'cashout_gain_loss': float(cashout_gain_loss),  # Cashout's portion of gain/loss
                            }
                        
                except Exception as e:
                    error = str(e)
                    messages.error(request, f"Error processing transaction: {error}")

        tx_data_json = None
        if tx_data:
            tx_data_json = json.dumps(tx_data, indent=4, default=str)

        context = {
            'title': 'Cashout Assessment',
            'form': form,
            'tx_data': tx_data,
            'tx_data_json': tx_data_json,
            'assessment': assessment,
            'error': error,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        return render(request, 'admin/main/tx_fiat_amounts.html', context)

    def capability(self, obj):
        if obj.cashtoken_nft:
            return obj.cashtoken_nft.capability
        return None

    def cashtoken(self, obj):
        return obj.cashtoken_ft or obj.cashtoken_nft or None

    def project(self, obj):
        if obj.address.wallet:
            return obj.address.wallet.project
        else:
            return obj.address.project

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def resend_unacknowledged_transactions(self, request, queryset):
        for tr in queryset:
            third_parties = client_acknowledgement(tr.id)
            for platform in third_parties:
                if 'telegram' in platform:
                    message = platform[1]
                    chat_id = platform[2]
                    send_telegram_message(message, chat_id)

    def save_wallet_history(self, request, queryset):
        for tr in queryset:
            parse_tx_wallet_histories(tr.txid, immediate=True)


class RecipientAdmin(admin.ModelAdmin):
    list_display = [
        'web_url',
        'telegram_id',
        'valid'
    ]

class SubscriptionAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    search_fields = ['address__address']

    list_display = [
        'address',
        'recipient',
        'websocket'
    ]

    dynamic_raw_id_fields = [
        'address',
        'recipient'
    ]


class AddressAdmin(DynamicRawIDMixin, admin.ModelAdmin):

    list_display = [
        'address',
        'token_address',
        'wallet',
        'wallet_index',
        'address_path',
        'project'
    ]

    dynamic_raw_id_fields = [
        'wallet',
        'project'
    ]

    search_fields = [
        'wallet__wallet_hash',
        'address'
    ]


class LastBalanceCheckFilter(DateFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)

        self.links = list(self.links)
        self.links.insert(2, ('Yesterday', {
            self.lookup_kwarg_since: str(yesterday),
            self.lookup_kwarg_until: str(today),
        }))


class WalletAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'wallet_hash',
        'wallet_type',
        'project',
        'last_balance_check',
        'last_utxo_scan_succeeded',
        'paytaca_app_version'
    ]
    actions = [ 'rescan_utxos' ]
    list_filter = [
        'wallet_type',
        ('last_balance_check', LastBalanceCheckFilter)
    ]

    dynamic_raw_id_fields = [
        'project'
    ]

    search_fields = [
        'wallet_hash'
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('clear-wallet-caches/', self.clear_wallet_caches_view, name='main_wallet_clear_wallet_caches'),
            path('view-wallet-balance-history/', self.view_wallet_balance_history_view, name='main_wallet_view_balance_history'),
        ]
        return custom_urls + urls

    def clear_wallet_caches_view(self, request):
        form = ClearWalletCachesForm()
        result = None
        error = None

        if request.method == 'POST':
            form = ClearWalletCachesForm(request.POST)
            if form.is_valid():
                wallet_hash = form.cleaned_data['wallet_hash'].strip()
                
                try:
                    from main.utils.cache import clear_wallet_balance_cache, clear_wallet_history_cache
                    from django.conf import settings
                    
                    cache = settings.REDISKV
                    
                    # Count caches before clearing
                    bch_balance_key = f'wallet:balance:bch:{wallet_hash}'
                    token_balance_keys = cache.keys(f'wallet:balance:token:{wallet_hash}:*')
                    history_keys = cache.keys(f'wallet:history:{wallet_hash}:*')
                    
                    bch_balance_exists = cache.exists(bch_balance_key)
                    token_balance_count = len(token_balance_keys) if token_balance_keys else 0
                    history_count = len(history_keys) if history_keys else 0
                    total_cache_count = (1 if bch_balance_exists else 0) + token_balance_count + history_count
                    
                    # Clear all caches
                    clear_wallet_balance_cache(wallet_hash, token_categories=None)
                    clear_wallet_history_cache(wallet_hash, asset_key=None)
                    
                    # Verify caches were cleared
                    bch_balance_exists_after = cache.exists(bch_balance_key)
                    token_balance_keys_after = cache.keys(f'wallet:balance:token:{wallet_hash}:*')
                    history_keys_after = cache.keys(f'wallet:history:{wallet_hash}:*')
                    
                    token_balance_count_after = len(token_balance_keys_after) if token_balance_keys_after else 0
                    history_count_after = len(history_keys_after) if history_keys_after else 0
                    
                    result = {
                        'success': True,
                        'message': f'Successfully cleared all caches for wallet: {wallet_hash}',
                        'wallet_hash': wallet_hash,
                        'bch_balance_cleared': bch_balance_exists,
                        'token_balance_count': token_balance_count,
                        'history_count': history_count,
                        'total_cleared': total_cache_count,
                        'bch_balance_remaining': bch_balance_exists_after,
                        'token_balance_remaining': token_balance_count_after,
                        'history_remaining': history_count_after,
                    }
                    
                except Exception as e:
                    error = str(e)
                    messages.error(request, f"Error clearing wallet caches: {error}")

        context = {
            'title': 'Clear Wallet Caches',
            'form': form,
            'result': result,
            'error': error,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        return render(request, 'admin/main/clear_wallet_caches.html', context)

    def view_wallet_balance_history_view(self, request):
        form = ViewWalletBalanceHistoryForm()
        wallet_data = None
        error = None

        if request.method == 'POST':
            form = ViewWalletBalanceHistoryForm(request.POST)
            if form.is_valid():
                wallet_hash = form.cleaned_data['wallet_hash'].strip()
                history_limit = form.cleaned_data['history_limit']
                
                try:
                    from django.db.models import Q, Sum, F
                    from django.db.models.functions import Coalesce
                    from main.utils.tx_fee import get_tx_fee_sats, bch_to_satoshi, satoshi_to_bch
                    from django.conf import settings
                    import json
                    
                    # Get wallet
                    try:
                        wallet = Wallet.objects.get(wallet_hash=wallet_hash)
                    except Wallet.DoesNotExist:
                        error = f'Wallet not found: {wallet_hash}'
                        wallet_data = None
                    else:
                        wallet_data = {
                            'wallet_hash': wallet.wallet_hash,
                            'wallet_type': wallet.wallet_type,
                            'project': str(wallet.project) if wallet.project else None,
                            'date_created': wallet.date_created,
                            'last_balance_check': wallet.last_balance_check,
                            'last_utxo_scan_succeeded': wallet.last_utxo_scan_succeeded,
                        }
                        
                        # Get BCH balance
                        if wallet.wallet_type == 'bch':
                            query = Q(wallet=wallet) & Q(spent=False)
                            qs_balance = Transaction.objects.filter(query).aggregate(
                                balance=Coalesce(Sum('value'), 0)
                            )
                            bch_balance = (qs_balance['balance'] or 0) / (10 ** 8)
                            qs_count = Transaction.objects.filter(query).count()
                            
                            spendable = int(bch_to_satoshi(bch_balance)) - get_tx_fee_sats(p2pkh_input_count=qs_count)
                            spendable = satoshi_to_bch(spendable)
                            spendable = max(spendable, 0)
                            
                            wallet_data['bch_balance'] = round(bch_balance, 8)
                            wallet_data['bch_spendable'] = round(spendable, 8)
                            wallet_data['bch_utxo_count'] = qs_count
                            
                            # Get token balances
                            token_balances = []
                            token_query = Q(wallet=wallet) & Q(spent=False) & Q(cashtoken_ft__isnull=False)
                            token_transactions = Transaction.objects.filter(token_query).select_related('cashtoken_ft', 'cashtoken_ft__info')
                            
                            # Group by category
                            from collections import defaultdict
                            token_groups = defaultdict(lambda: {'amount': 0, 'info': None})
                            
                            for tx in token_transactions:
                                if tx.cashtoken_ft:
                                    category = tx.cashtoken_ft.category
                                    token_groups[category]['amount'] += tx.amount
                                    if not token_groups[category]['info'] and tx.cashtoken_ft.info:
                                        token_groups[category]['info'] = {
                                            'name': tx.cashtoken_ft.info.name,
                                            'symbol': tx.cashtoken_ft.info.symbol,
                                            'decimals': tx.cashtoken_ft.info.decimals,
                                        }
                            
                            for category, data in token_groups.items():
                                decimals = data['info']['decimals'] if data['info'] else 0
                                balance = round(data['amount'], decimals)
                                token_balances.append({
                                    'category': category,
                                    'balance': balance,
                                    'name': data['info']['name'] if data['info'] else 'Unknown',
                                    'symbol': data['info']['symbol'] if data['info'] else 'N/A',
                                    'decimals': decimals,
                                })
                            
                            wallet_data['token_balances'] = token_balances
                        
                        # Get wallet history
                        history = WalletHistory.objects.filter(wallet=wallet).exclude(amount=0).order_by(
                            '-tx_timestamp', '-date_created'
                        )[:history_limit].select_related('token', 'cashtoken_ft', 'cashtoken_nft')
                        
                        history_list = []
                        for record in history:
                            history_list.append({
                                'id': record.id,
                                'txid': record.txid,
                                'record_type': record.record_type,
                                'amount': record.amount,
                                'tx_fee': record.tx_fee,
                                'tx_timestamp': record.tx_timestamp,
                                'date_created': record.date_created,
                                'token_name': record.token.name if record.token else None,
                                'cashtoken_category': record.cashtoken_ft.category if record.cashtoken_ft else None,
                                'usd_price': float(record.usd_price) if record.usd_price else None,
                            })
                        
                        wallet_data['history'] = history_list
                        wallet_data['history_count'] = len(history_list)
                        wallet_data['total_history_count'] = WalletHistory.objects.filter(wallet=wallet).exclude(amount=0).count()
                        wallet_data['has_usd_prices'] = any(record.get('usd_price') for record in history_list)
                        
                except Exception as e:
                    error = str(e)
                    messages.error(request, f"Error viewing wallet: {error}")

        context = {
            'title': 'View Wallet Balance & History',
            'form': form,
            'wallet_data': wallet_data,
            'error': error,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        return render(request, 'admin/main/view_wallet_balance_history.html', context)

    def rescan_utxos(self, request, queryset):
        for wallet in queryset:
            addresses = wallet.addresses.all()
            for address in addresses:
                if wallet.wallet_type == 'bch':
                    get_bch_utxos(address.address)
                elif wallet.wallet_type == 'slp':
                    get_slp_utxos(address.address)


class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'date_created',
        'wallets',
        'addresses',
        'transactions',
        'publicize_wallets',
    ]

    def wallets(self, obj):
        return obj.wallets_count

    def addresses(self, obj):
        return obj.addresses_count

    def transactions(self, obj):
        return obj.transactions_count


class ContractHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'txid',
        'address',
        'record_type',
        'amount',
        'token',
        'date_created'
    ]
    
    search_fields = [
        'txid',
        'address',
    ]

    list_filter = [
        'record_type',
    ]
    

class WalletHistoryAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'txid',
        'wallet',
        'record_type',
        'amount',
        'token',
        'cashtoken',
        'capability',
        'has_fiat_amounts',
        'date_created'
    ]

    dynamic_raw_id_fields = [
        'wallet',
        'token',
        'cashtoken_ft',
        'cashtoken_nft',
        'price_log'
    ]

    search_fields = [
        'wallet__wallet_hash',
        'txid'
    ]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('clear-market-prices/', self.clear_market_prices_view, name='main_wallethistory_clear_market_prices'),
        ]
        return custom_urls + urls

    def clear_market_prices_view(self, request):
        form = ClearMarketPricesForm()
        result = None
        error = None

        if request.method == 'POST':
            form = ClearMarketPricesForm(request.POST)
            if form.is_valid():
                category = form.cleaned_data['category'].strip()
                dry_run = form.cleaned_data['dry_run']
                
                try:
                    from django.db import transaction as db_transaction
                    
                    # Query WalletHistory records with the specified cashtoken category
                    queryset = WalletHistory.objects.filter(
                        cashtoken_ft__category=category
                    ).select_related('cashtoken_ft')
                    
                    count = queryset.count()
                    
                    if count == 0:
                        result = {
                            'success': False,
                            'message': f'No WalletHistory records found for cashtoken category: {category}',
                            'count': 0,
                            'records_with_prices_count': 0,
                            'dry_run': dry_run
                        }
                    else:
                        # Show records that will be updated
                        records_with_prices = queryset.exclude(market_prices__isnull=True).exclude(market_prices={})
                        records_with_prices_count = records_with_prices.count()
                        
                        if dry_run:
                            # Show preview of records that would be updated
                            preview_records = []
                            for record in records_with_prices[:10]:  # Show first 10
                                preview_records.append({
                                    'id': record.id,
                                    'txid': record.txid,
                                    'market_prices': record.market_prices
                                })
                            
                            result = {
                                'success': True,
                                'message': 'DRY RUN - No changes were made',
                                'count': count,
                                'records_with_prices_count': records_with_prices_count,
                                'records_without_prices_count': count - records_with_prices_count,
                                'dry_run': True,
                                'preview_records': preview_records,
                                'more_records': max(0, records_with_prices_count - 10)
                            }
                        else:
                            # Actually clear market_prices
                            if records_with_prices_count > 0:
                                with db_transaction.atomic():
                                    updated = queryset.update(market_prices=None)
                                
                                result = {
                                    'success': True,
                                    'message': f'Successfully cleared market_prices for {updated} WalletHistory record(s)',
                                    'count': count,
                                    'records_with_prices_count': records_with_prices_count,
                                    'records_without_prices_count': count - records_with_prices_count,
                                    'updated_count': updated,
                                    'dry_run': False
                                }
                            else:
                                result = {
                                    'success': True,
                                    'message': 'No records with market_prices to clear',
                                    'count': count,
                                    'records_with_prices_count': 0,
                                    'records_without_prices_count': count,
                                    'dry_run': False
                                }
                    
                    result['category'] = category
                    
                except Exception as e:
                    error = str(e)
                    messages.error(request, f"Error clearing market prices: {error}")

        context = {
            'title': 'Clear Market Prices',
            'form': form,
            'result': result,
            'error': error,
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        return render(request, 'admin/main/clear_market_prices.html', context)

    def cashtoken(self, obj):
        return obj.cashtoken_ft or obj.cashtoken_nft or None

    def capability(self, obj):
        if obj.cashtoken_nft:
            return obj.cashtoken_nft.capability
        return None
    
    def has_fiat_amounts(self, obj):
        return bool(obj.fiat_amounts)
    has_fiat_amounts.boolean = True
    has_fiat_amounts.short_description = 'Has Fiat Amt'


class WalletNftTokenAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'token',
        'wallet',
        'date_acquired',
        'date_dispensed'
    ]

    dynamic_raw_id_fields = [
        'wallet',
        'token',
        'acquisition_transaction',
        'dispensation_transaction'
    ]

    search_fields = [
        'wallet__wallet_hash'
    ]


class CashTokenInfoAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'symbol',
        'decimals',
    ]


class CashFungibleTokenAdmin(admin.ModelAdmin):
    list_display = [
        'category',
        'name',
        'symbol',
        'decimals',
    ]

    actions = ['refetch_metadata']

    def name(self, obj):
        if obj.info:
            return obj.info.name
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['name']

    def symbol(self, obj):
        if obj.info:
            return obj.info.symbol
        return settings.DEFAULT_TOKEN_DETAILS['fungible']['symbol']

    def decimals(self, obj):
        if obj.info:
            return obj.info.decimals
        return 0

    def refetch_metadata(self, request, queryset):
        """Refetch token metadata from BCMR indexer for selected tokens"""
        updated_count = 0
        error_count = 0
        skipped_count = 0

        for token in queryset:
            try:
                # Force refresh metadata
                token.fetch_metadata(force_refresh=True)
                updated_count += 1
            except Exception as e:
                error_count += 1
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Error refetching metadata for token {token.category}: {str(e)}')

        if updated_count > 0:
            self.message_user(
                request,
                f'Successfully refetched metadata for {updated_count} token(s).',
                messages.SUCCESS
            )

        if error_count > 0:
            self.message_user(
                request,
                f'Failed to refetch metadata for {error_count} token(s). Check logs for details.',
                messages.WARNING
            )

    refetch_metadata.short_description = "Refetch metadata from BCMR"


class CashNonFungibleTokenAdmin(admin.ModelAdmin):
    list_display = [
        'category',
        'commitment',
        'capability',
        'name',
        'symbol',
        'decimals',
        'nft_details',
    ]

    def name(self, obj):
        if obj.info:
            return obj.info.name
        return settings.DEFAULT_TOKEN_DETAILS['nft']['name']
    
    def symbol(self, obj):
        if obj.info:
            return obj.info.symbol
        return settings.DEFAULT_TOKEN_DETAILS['nft']['symbol']

    def decimals(self, obj):
        if obj.info:
            return obj.info.decimals
        return 0

    def nft_details(self, obj):
        if obj.info:
            return obj.info.nft_details
        return None
    

class TransactionBroadcastAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'txid',
        'num_retries',
        'date_received',
        'date_succeeded',
        'price_log',
        'has_fiat_amounts'
    ]

    dynamic_raw_id_fields = [
        'price_log'
    ]
    
    def has_fiat_amounts(self, obj):
        return bool(obj.output_fiat_amounts)
    has_fiat_amounts.boolean = True
    has_fiat_amounts.short_description = 'Has Fiat Amounts'


class AssetPriceLogAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'id',
        'currency',
        'relative_currency',
        'price_value',
        'timestamp',
        'source',
        'calculation',
        'has_source_logs'
    ]

    list_filter = [
        'currency',
        'relative_currency',
        'source'
    ]

    search_fields = [
        'currency',
        'relative_currency',
        'source',
        'calculation'
    ]

    dynamic_raw_id_fields = [
        'currency_ft_token',
        'relative_currency_ft_token'
    ]

    ordering = ['-timestamp']
    
    def has_source_logs(self, obj):
        return bool(obj.source_price_logs)
    has_source_logs.boolean = True
    has_source_logs.short_description = 'Has Sources'


admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(CashTokenInfo, CashTokenInfoAdmin)
admin.site.register(CashFungibleToken, CashFungibleTokenAdmin)
admin.site.register(CashNonFungibleToken, CashNonFungibleTokenAdmin)

admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(Recipient, RecipientAdmin)
admin.site.register(Address, AddressAdmin)
admin.site.register(Wallet, WalletAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(ContractHistory, ContractHistoryAdmin)
admin.site.register(WalletHistory, WalletHistoryAdmin)
admin.site.register(WalletNftToken, WalletNftTokenAdmin)
admin.site.register(TransactionBroadcast, TransactionBroadcastAdmin)
admin.site.register(AssetPriceLog, AssetPriceLogAdmin)

class AppVersionAdmin(admin.ModelAdmin):
    list_display = ('latest_version', 'min_required_version', 'platform', 'release_date')
    fields = ('platform', 'latest_version', 'min_required_version', 'release_date', 'notes')

admin.site.register(AppVersion, AppVersionAdmin)

class AppControlAdmin(admin.ModelAdmin):
    list_display = ['feature_name', 'is_enabled', 'enabled_countries']
    actions = ['enable', 'disable']

    def enable(self, request, queryset):
        for app in queryset:
            app.is_enabled = True
            app.save()

    enable.short_description = "Enable selected apps"

    def disable(self, request, queryset):
        for app in queryset:
            app.is_enabled = False
            app.save()

    disable.short_description = "Disable selected apps"

admin.site.register(AppControl, AppControlAdmin)

class AssetSettingAdmin (admin.ModelAdmin):
    list_display = [
        'wallet_hash'        
    ]
admin.site.register(AssetSetting, AssetSettingAdmin)