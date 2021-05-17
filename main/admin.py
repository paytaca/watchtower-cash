from django.contrib import admin
from main.models import (
    Token,
    Transaction,
    SlpAddress,
    BchAddress,
    Block,
    Subscription,
    Recipient
)
from django.contrib.auth.models import User, Group
from main.tasks import client_acknowledgement, send_telegram_message
from django.utils.html import format_html
from django.conf import settings
import json
admin.site.site_header = 'WatchTower.Cash Admin'
REDIS_STORAGE = settings.REDISKV

class TokenAdmin(admin.ModelAdmin):
    list_display = [
        'tokenid',
        'name'
    ]

    def get_query(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TokenAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        return qs.filter(subscriber__user=request.user)

class BlockAdmin(admin.ModelAdmin):
    actions = ['process']
    ordering = ('-number',)

    list_display = [
        'number',
        'processed',
        'created_datetime',
        'updated_datetime',
        'transactions_count',
        
    ]

    
    def process(modeladmin, request, queryset):
        for trans in queryset:
            pending_blocks = json.loads(REDIS_STORAGE.get('PENDING-BLOCKS'))
            pending_blocks.append(trans.number)
            pending_blocks = list(set(pending_blocks))
            Block.objects.filter(number=trans.number).update(processed=False)
            REDIS_STORAGE.set('PENDING-BLOCKS', json.dumps(pending_blocks))

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions



class TransactionAdmin(admin.ModelAdmin):
    search_fields = ['token__name', 'source', 'txid']

    actions = ['resend_unacknowledged_transactions']

    list_display = [
        'id',
        'txid',
        'index',
        'address',
        'amount',
        'source',
        'block',
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
        

    def resend_unacknowledged_transactions(modeladmin, request, queryset):
        for tr in queryset:
            third_parties = client_acknowledgement(tr.id)
            for platform in third_parties:
                if 'telegram' in platform:
                    message = platform[1]
                    chat_id = platform[2]
                    send_telegram_message(message, chat_id)
            

    def get_queryset(self, request): 
        # For Django < 1.6, override queryset instead of get_queryset
        qs = super(TransactionAdmin, self).get_queryset(request) 
        if request.user.is_superuser:
            return qs
        subscriber = Subscriber.objects.filter(user=request.user)
        if subscriber.exists():
            obj = subscriber.first()
            token_ids = obj.token.values_list('id',flat=True).distinct()
            return Transaction.objects.filter(token__id__in=token_ids)
        else:
            return qs.filter(id=0)

class SlpAddressAdmin(admin.ModelAdmin):
    list_display = [
        'address',
    ]

    exclude = [
        'transactions',
    ]
    
class BchAddressAdmin(admin.ModelAdmin):
    list_display = [
        'address',
    ]

    exclude = [
        'transactions',
    ]

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



    
admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)
admin.site.register(BchAddress, BchAddressAdmin)
admin.site.register(Block, BlockAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(Recipient, RecipientAdmin)