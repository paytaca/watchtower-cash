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
from main.tasks import first_blockheight_scanner, client_acknowledgement, checktransaction
admin.site.site_header = 'WatchTower.Cash Admin'

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
    actions = ['rescan_selected_blockheights']
    ordering = ('-number',)

    list_display = [
        'number',
        'processed',
        'created_datetime',
        'updated_datetime',
        'transactions_count',
        '_actions'
    ]

    


    def rescan_selected_blockheights(modeladmin, request, queryset):
        for trans in queryset:
            first_blockheight_scanner.delay(trans.id)
            BlockHeight.objects.filter(id=trans.id).update(processed=False)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


    def _actions(self, obj):
        if obj.processed:
            return format_html(
                    f"""<a class="button"
                    href="/main/blockheight?rescan={obj.id}"
                    style="background-color: transparent;padding:0px;"><img src='/static/admin/img/search.svg'></img></a>"""
                )
        else:
            return format_html('<span style="color:blue"> Scanning...</span>')
    
    def changelist_view(self, request, extra_context=None):
        self.param = request.GET.get('rescan', None)
        if self.param:
            first_blockheight_scanner.delay(self.param)
            BlockHeight.objects.filter(id=self.param).update(processed=False)
        return super(BlockHeightAdmin,self).changelist_view(request, extra_context=extra_context)


class TransactionAdmin(admin.ModelAdmin):
    search_fields = ['token__name', 'source', 'txid']

    actions = ['resend_unacknowledged_transactions']

    list_display = [
        'id',
        '_txid',
        'spentIndex',
        'address',
        'amount',
        'source',
        'blockheight_number',
        'token',
        'acknowledged',
        'subscribed',
        'created_datetime',
        '_actions'
    ]

    def _actions(self, obj):
        if not obj.scanning:
            return format_html(
                f"""<a class="button"
                href="/main/transaction?rescan={obj.txid}"
                style="background-color: transparent;padding:0px;"><img src='/static/admin/img/search.svg'></img></a>"""
            )
        else:
            return format_html('<span style="color:blue"> Scanning...</span>')
    
    def changelist_view(self, request, extra_context=None):
        self.param = request.GET.get('rescan', None)
        if self.param:
            checktransaction.delay(self.param)
            Transaction.objects.filter(txid=self.param).update(scanning=True)
        return super(TransactionAdmin,self).changelist_view(request, extra_context=extra_context)


    def _txid(self, obj):
        url = f'https://explorer.bitcoin.com/bch/tx/{obj.txid}'
        return format_html(
            f"""<a class="button"
            target="_blank" 
            href="{url}"
            style="background-color:transparent;
            padding:0px;
            color:#447e9b;
            text-decoration:None;
            font-weight:bold;">{obj.txid}</a>"""
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
        
    def blockheight_number(self, obj):
        if obj.blockheight is not None:
            return obj.blockheight.number
        return f'----'

    def resend_unacknowledged_transactions(modeladmin, request, queryset):
        for tr in queryset:
            client_acknowledgement(tr.token.tokenid, tr.id)
            


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
    exclude = ('subscription',)

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