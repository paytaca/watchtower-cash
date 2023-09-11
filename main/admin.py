from django.contrib.auth.models import User, Group
from django.contrib import admin

from main.models import *
from main.tasks import (
    client_acknowledgement,
    send_telegram_message,
    get_token_meta_data,
    get_bch_utxos,
    get_slp_utxos,
    parse_tx_wallet_histories
)

from dynamic_raw_id.admin import DynamicRawIDMixin
from django.utils.html import format_html
from django.conf import settings

import json


admin.site.site_header = 'WatchTower.Cash Admin'
REDIS_STORAGE = settings.REDISKV

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
            parse_tx_wallet_histories(tr.txid)


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


class WalletAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'wallet_hash',
        'wallet_type',
        'version',
        'project'
    ]
    actions = [ 'rescan_utxos' ]

    dynamic_raw_id_fields = [
        'project'
    ]

    search_fields = [
        'wallet_hash'
    ]

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
        'transactions'
    ]

    def wallets(self, obj):
        return obj.wallets_count

    def addresses(self, obj):
        return obj.addresses_count

    def transactions(self, obj):
        return obj.transactions_count


class WalletHistoryAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'txid',
        'wallet',
        'record_type',
        'amount',
        'token',
        'cashtoken',
        'capability',
        'date_created'
    ]

    dynamic_raw_id_fields = [
        'wallet',
        'token'
    ]

    search_fields = [
        'wallet__wallet_hash'
    ]

    def cashtoken(self, obj):
        return obj.cashtoken_ft or obj.cashtoken_nft or None

    def capability(self, obj):
        if obj.cashtoken_nft:
            return obj.cashtoken_nft.capability
        return None


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
admin.site.register(WalletHistory, WalletHistoryAdmin)
admin.site.register(WalletNftToken, WalletNftTokenAdmin)
