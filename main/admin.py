from django.contrib import admin
from main.models import (
    Token,
    Address,
    Transaction,
    BlockHeight,
    Subscription,
    Recipient,
    Project,
    Wallet
)
from django.contrib.auth.models import User, Group
from main.tasks import client_acknowledgement, send_telegram_message
from dynamic_raw_id.admin import DynamicRawIDMixin
from django.utils.html import format_html
from django.conf import settings
import json


admin.site.site_header = 'WatchTower.Cash Admin'
REDIS_STORAGE = settings.REDISKV

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'tokenid',
        'name',
        'token_ticker',
        'token_type'
    ]

    def get_query(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TokenAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        return qs.filter(subscriber__user=request.user)

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
    search_fields = ['token__name', 'source', 'txid']
    
    dynamic_raw_id_fields = [
        'blockheight',
        'token',
        'spend_block_height'
    ]

    actions = ['resend_unacknowledged_transactions']

    list_display = [
        'id',
        'txid',
        'index',
        'address',
        'amount',
        'source',
        'blockheight',
        'token',
        'acknowledged',
        'created_datetime',
        'spent',
        'spend_block_height'
    ]

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


class RecipientAdmin(admin.ModelAdmin):
    list_display = [
        'web_url',
        'telegram_id',
        'valid'
    ]

class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'recipient',
        'slp',        
        'bch',
        'websocket'
    ]


class AddressAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'address',
        'wallet',
        'wallet_index',
        'project'
    ]

    dynamic_raw_id_fields = [
        'wallet',
        'project'
    ]


class WalletAdmin(DynamicRawIDMixin, admin.ModelAdmin):
    list_display = [
        'wallet_hash',
        'wallet_type',
        'project'
    ]

    dynamic_raw_id_fields = [
        'project'
    ]



class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'date_created'
    ]

    
admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(Recipient, RecipientAdmin)
admin.site.register(Address, AddressAdmin)
admin.site.register(Wallet, WalletAdmin)
admin.site.register(Project, ProjectAdmin)
