from django.contrib import admin
from main.models import (
    Token,
    Transaction,
    SlpAddress,
    BchAddress,
    BlockHeight,
    Subscriber,
    Subscription,
    SendTo
)
from django.contrib.auth.models import User, Group
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

class BlockHeightAdmin(admin.ModelAdmin):
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
            BlockHeight.objects.filter(number=trans.number).update(processed=False)
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
        'blockheight',
        'token',
        'acknowledged',
        'created_datetime',
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
        

    def resend_unacknowledged_transactions(modeladmin, request, queryset):
        for tr in queryset:
            client_acknowledgement(tr.token.tokenid, r.id)
            

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

class SendToAdmin(admin.ModelAdmin):
    list_display = [
        'address',
    ]

class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'token'
    ]


class SubscriberAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'confirmed'
    ]
    exclude = ('subscriptions',)

    # [{"token_id": 0,"target_addresses":[],"confirmation":0}]
    
# admin.site.register(User)
# admin.site.register(Group)
admin.site.register(Token, TokenAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(SlpAddress, SlpAddressAdmin)
admin.site.register(BchAddress, BchAddressAdmin)
admin.site.register(BlockHeight, BlockHeightAdmin)
admin.site.register(Subscriber, SubscriberAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(SendTo, SendToAdmin)